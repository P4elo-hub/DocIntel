import json
import re
from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from fastapi import UploadFile

from app.chat.context import build_sliding_context
from app.chat.domain import Chat, ChatMessage
from app.chat.media import VOICE_UNAVAILABLE_MESSAGE, extract_rag_query, media_to_part
from app.chat.rag_query import (
    build_condense_messages,
    build_rag_queries,
    is_follow_up_clarification,
    needs_context_expansion,
    sanitize_condensed,
)
from app.core.exceptions import VoiceUnavailableError
from app.chat.prompt_selection import choose_by_split
from app.chat.repository import ChatRepository, SystemPromptRepository
from app.chat.tokens import count_tokens, fit_to_budget
from app.moderation.domain import ModerationResult
from app.moderation.service import ModerationService
from app.services.cache import agent_query_cache_key

logger = structlog.get_logger("chat-service")

# Максимум запросов для follow-up мульти-поиска. Каждый запрос — отдельный ретрив
# + reranker на CPU, поэтому веер ограничен, иначе latency растёт кратно.
_MAX_FOLLOWUP_RAG_QUERIES = 3


def _filter_used_sources(answer: str, sources: list) -> list:
    """Оставляет только те источники, чьи номера [n] встретились в ответе LLM.

    Модель могла использовать не все переданные чанки; показываем в футере
    «Источники» лишь реально процитированные, чтобы не вводить в заблуждение.
    """
    if not sources:
        return []
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    if not cited:
        return []
    return [s for s in sources if s.get("id") in cited]


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        llm_client,
        *,
        default_model: str = "gpt-4o-mini",
        context_window: int = 10,
        model_context_window: int = 128_000,
        response_tokens: int = 1024,
        safety_margin: int = 256,
        moderation: ModerationService | None = None,
        prompt_repo: SystemPromptRepository | None = None,
        rag_service=None,
        rag_enabled: bool = False,
        agent_enabled: bool = False,
        cache=None,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.repository = repository
        self.llm = llm_client
        self.default_model = default_model
        self.context_window = context_window
        self.model_context_window = model_context_window
        self.response_tokens = response_tokens
        self.safety_margin = safety_margin
        self.moderation = moderation
        self.prompt_repo = prompt_repo
        self.rag_service = rag_service
        self.rag_enabled = rag_enabled
        # True → Telegram/web идут через LangGraph (Qdrant → answer/write).
        self.agent_enabled = agent_enabled
        self.cache = cache
        self.cache_ttl_seconds = cache_ttl_seconds

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        return await self.repository.create_chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        return await self.repository.get_or_create_chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        return await self.repository.get_chat(chat_id)

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]:
        return await self.repository.list_messages(chat_id, limit=limit)

    async def clear_history(self, chat_id: UUID) -> None:
        await self.repository.soft_delete_messages(chat_id)

    async def check_input(
        self, content: str, owner_external_id: str | None = None
    ) -> ModerationResult:
        if self.moderation is None:
            return ModerationResult(allowed=True, layer="passed")
        return await self.moderation.check_input(content, owner_external_id=owner_external_id)

    async def _pick_prompt(self, owner_external_id: str):
        if self.prompt_repo is None:
            return None, None
        active = await self.prompt_repo.list_active()
        chosen = choose_by_split(owner_external_id, active)
        if chosen is None:
            return None, None
        return chosen.id, chosen.body

    async def _retrieve_rag(
        self, questions: str | list[str], *, prioritize_first: bool = False
    ) -> dict:
        """Вариант C: ищет контекст в базе знаний. Сбой/незрелый индекс —
        не роняет чат: возвращаем пустой результат, отвечаем без цитат.

        prioritize_first резервирует слоты под первый запрос (свежую реплику):
        нужно при явной правке, чтобы condensed-переформулировка не увела поиск.
        """
        if isinstance(questions, str):
            query_list = [questions] if questions.strip() else []
        else:
            query_list = [q.strip() for q in questions if q.strip()]
        if not self.rag_enabled or self.rag_service is None or not query_list:
            return {"context_str": "", "sources": []}
        try:
            if len(query_list) == 1:
                result = await self.rag_service.retrieve_context(query_list[0])
            else:
                result = await self.rag_service.retrieve_context_multi(
                    query_list, prioritize_first=prioritize_first
                )
        except Exception as exc:
            logger.warning("rag_retrieve_failed", error=str(exc))
            return {"context_str": "", "sources": []}
        if not result.get("confident"):
            return {"context_str": "", "sources": []}
        return {
            "context_str": result.get("context_str", ""),
            "sources": result.get("sources", []),
        }

    async def _condense_query(self, current: str, history: list) -> str:
        """Свернуть follow-up в самостоятельный поисковый запрос через дешёвую LLM.

        «приведи пример» + история про комиссии БПХ → «пример JSON ответа с
        комиссиями от БПХ». При сбое/пустом ответе возвращаем исходную реплику,
        чтобы retrieval не остался без запроса.
        """
        messages = build_condense_messages(current, history)
        if messages is None:
            return current
        try:
            resp = await self.llm.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=0,
                max_tokens=120,
            )
            raw = resp.choices[0].message.content if resp.choices else ""
        except Exception as exc:
            logger.warning("rag_condense_failed", error=str(exc))
            return current
        condensed = sanitize_condensed(raw or "", fallback=current)
        if condensed != current:
            logger.info("rag_query_condensed", original=current[:120], condensed=condensed[:120])
        return condensed

    @staticmethod
    def _rag_context_message(context_str: str) -> dict:
        return {
            "role": "system",
            "content": (
                "Ниже — пронумерованные источники из корпоративной базы знаний "
                "по продукту «История операций».\n\n"
                "Правила ответа:\n"
                "1. Отвечай ТОЛЬКО на основе этих источников. Не добавляй факты "
                "из собственных знаний и ничего не выдумывай.\n"
                "2. После каждого факта ставь номер источника в квадратных "
                "скобках, например [1] или [2].\n"
                "3. Если в источниках описаны и старое состояние (AS IS), и новое "
                "(TO BE) — отвечай по TO BE как по актуальному; AS IS упоминай "
                "только если об этом прямо спрашивают. При противоречии между "
                "источниками предпочитай более новый (TO BE, свежая версия релиза, "
                "не помеченный как устаревший).\n"
                "4. Собирай ответ из всех релевантных источников, даже если каждый "
                "фрагмент неполный. Отказывайся («В базе знаний я не нашёл ответа») "
                "только если ни один источник не содержит информации по сути вопроса.\n"
                "5. Различай слои интеграции: (а) BPH/BC → HO, (б) HO → Composite "
                "(gRPC GET_DETAILS / SEND_DETAILS, proto-поля операции), (в) Composite "
                "→ МП (screenData, sections). На уточнения («это не то», «нужен формат "
                "HO→Composite») отвечай по правильному слою из источников.\n"
                "6. Термины и аббревиатуры (например, DCA, БПХ, BC) понимай в "
                "контексте продукта «История операций» по этим источникам. Если "
                "твои предыдущие ответы в этом диалоге противоречат источникам — "
                "источники приоритетны: исправь ошибку и ответь по источникам, "
                "не повторяй неверный формат.\n\n"
                "---------------------\n"
                f"{context_str}\n"
                "---------------------"
            ),
        }

    async def _send_via_agents(
        self,
        *,
        chat_id: UUID,
        query: str,
        prompt_id,
        prior_history: list | None = None,
    ) -> AsyncIterator[dict]:
        """Ответ через LangGraph.

        Историю чата передаём в classify_agent как кандидата; он сам решает
        ``history`` (пробросить + condense) или ``fresh`` (обнулить).
        Кэш exact-match — только для fresh-запросов без prior (иначе follow-up
        зависит от истории).
        """
        from app.chat.rag_query import recent_dialog_summary_for_agents
        from app.services.agent_graph import run_docintel_pipeline

        prior = list(prior_history or [])
        # Полные JSON/таблицы из прошлых answer — иначе write_integration их не видит.
        chat_history = recent_dialog_summary_for_agents(prior) if prior else ""

        # При наличии истории не читаем кэш: ответ зависит от use_history.
        cache_key = agent_query_cache_key(query)
        cached_hit = False
        assistant_text = ""
        agents: list = []
        intent = None
        rag_sources: list = []

        if self.cache is not None and not prior:
            try:
                blob = await self.cache.get(cache_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("agent_cache_get_failed", error=str(exc))
                blob = None
            if blob:
                try:
                    payload = json.loads(blob)
                    assistant_text = (payload.get("answer") or "").strip()
                    agents = payload.get("agents") or ["cache"]
                    intent = payload.get("intent")
                    rag_sources = list(payload.get("sources") or [])
                    # Не отдаём из кэша ответ «RAG ещё не готов» — иначе вечный miss.
                    if "Qdrant) ещё не готова" in assistant_text:
                        cached_hit = False
                        assistant_text = ""
                    else:
                        cached_hit = bool(assistant_text)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning("agent_cache_corrupt", error=str(exc))
                    cached_hit = False

        if cached_hit:
            logger.info(
                "chat_agent_pipeline_cache_hit",
                chat_id=str(chat_id),
                intent=intent,
                agents=agents,
                chars=len(assistant_text),
                query=query[:160],
            )
        else:
            logger.info(
                "chat_agent_pipeline_start",
                chat_id=str(chat_id),
                query=query[:160],
                history_candidate_chars=len(chat_history),
            )
            try:
                result = await run_docintel_pipeline(
                    query,
                    chat_history=chat_history,
                    original_user_message=query,
                    thread_id=f"chat-{chat_id}",
                    rag_service=self.rag_service,
                )
            except Exception as exc:
                logger.exception("chat_agent_pipeline_failed", chat_id=str(chat_id))
                yield {
                    "type": "error",
                    "code": "agent_pipeline_failed",
                    "message": f"Агенты DocIntel не ответили: {exc}",
                }
                return

            assistant_text = (result.get("answer") or "").strip()
            agents = result.get("agents_called") or []
            intent = result.get("intent")
            rag_sources = list(result.get("sources") or [])
            use_history = bool(result.get("use_history"))
            effective = (result.get("user_request") or query).strip()
            logger.info(
                "chat_agent_pipeline_done",
                chat_id=str(chat_id),
                intent=intent,
                use_history=use_history,
                agents=agents,
                sources=len(rag_sources),
                chars=len(assistant_text),
                cached=False,
            )
            # Кэшируем только самостоятельные (fresh) успешные ответы.
            # Не кэшируем «RAG не готов» и пустой retrieve без источников.
            cacheable = (
                bool(assistant_text)
                and self.cache is not None
                and not use_history
                and "Qdrant) ещё не готова" not in assistant_text
                and not (
                    intent in {"answer", "write", "search"} and not rag_sources
                )
            )
            if cacheable:
                try:
                    await self.cache.setex(
                        agent_query_cache_key(effective),
                        self.cache_ttl_seconds,
                        json.dumps(
                            {
                                "answer": assistant_text,
                                "intent": intent,
                                "agents": agents,
                                "sources": rag_sources,
                            },
                            ensure_ascii=False,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("agent_cache_set_failed", error=str(exc))

        if not assistant_text:
            yield {
                "type": "error",
                "code": "agent_empty_answer",
                "message": "Агенты не вернули текст ответа.",
            }
            return

        # SSE/бот ждут token-стрим — отдаём ответ чанками.
        chunk_size = 48
        for i in range(0, len(assistant_text), chunk_size):
            yield {"type": "token", "delta": assistant_text[i : i + chunk_size]}

        # reject/chat — без источников; search/answer/write — список из Qdrant.
        emit_sources = (
            intent not in {"reject", "chat"} and bool(rag_sources)
        )
        assistant_message = ChatMessage(
            chat_id=chat_id,
            role="assistant",
            content=assistant_text,
            sources=rag_sources if emit_sources else None,
            tokens=count_tokens([{"role": "assistant", "content": assistant_text}]),
            prompt_id=prompt_id,
        )
        saved = await self.repository.append_message(chat_id, assistant_message)
        yield {"type": "message_saved", "message_id": str(saved.id)}
        if emit_sources:
            yield {"type": "sources", "sources": rag_sources}

    async def send_message(
        self,
        chat_id: UUID,
        user_content: str,
        media: UploadFile | None = None,
    ) -> AsyncIterator[dict]:
        media_refs: dict | None = None
        if media is not None:
            mime = media.content_type or ""
            filename = media.filename
            size = getattr(media, "size", None)
            try:
                part = await media_to_part(media, self.llm)
            except VoiceUnavailableError:
                yield {
                    "type": "error",
                    "code": "voice_unavailable",
                    "message": VOICE_UNAVAILABLE_MESSAGE,
                }
                return
            media_refs = {
                "mime": mime,
                "size": size,
                "filename": filename,
                "part": part,
            }

        chat = await self.repository.get_chat(chat_id)
        if chat is None:
            raise ValueError(f"Chat {chat_id} not found")

        prompt_id, prompt_body = await self._pick_prompt(chat.owner_external_id)

        # Голос/файл: транскрипт кладём в content, иначе в БД пустая строка и
        # follow-up/история ломаются, если media_refs не прочитали.
        current_query = extract_rag_query(user_content, media_refs)
        stored_content = (user_content or "").strip() or current_query

        user_message = ChatMessage(
            chat_id=chat_id,
            role="user",
            content=stored_content,
            media_refs=media_refs,
            prompt_id=prompt_id,
        )
        await self.repository.append_message(chat_id, user_message)

        history = await self.repository.list_messages(chat_id, limit=self.context_window)
        # Текущее user-сообщение уже в history — в prior для агентов не включаем.
        prior_history = history[:-1]

        # LangGraph DocIntel: classify_agent → search | write→validate | answer→validate
        # с chat_history / condense (как в pre-agent RAG), иначе follow-up ломается.
        if self.agent_enabled and current_query.strip():
            async for event in self._send_via_agents(
                chat_id=chat_id,
                query=current_query,
                prompt_id=prompt_id,
                prior_history=prior_history,
            ):
                yield event
            return

        messages = await build_sliding_context(
            self.repository,
            chat,
            chat_id,
            context_window=self.context_window,
            system_prompt_body=prompt_body,
        )

        # Вариант C: подмешиваем найденные в базе знаний чанки как system-контекст.
        # fit_to_budget сохраняет system-сообщения, поэтому контекст не обрежется.
        prior_history = history[:-1]
        # Follow-up («приведи пример», «это не то», короткая реплика) теряет тему при
        # поиске только по себе — тогда сворачиваем его в самостоятельный запрос и
        # добавляем контекстные запросы. Самостоятельный развёрнутый вопрос ищем одним
        # запросом: без лишнего LLM-condense и мульти-поиска (меньше шума и latency).
        prioritize_raw = False
        if prior_history and needs_context_expansion(current_query):
            condensed_query = await self._condense_query(current_query, prior_history)
            # Сырую реплику ставим ПЕРВОЙ: при явной правке («нет, не X, а Y»)
            # именно она несёт новый термин, а condensed может утащить старый
            # (напр. «ОГЭ» из отравленной истории). prioritize_raw резервирует
            # ей слоты в выдаче, чтобы шумная свёртка её не вытеснила.
            candidates = [
                current_query,
                condensed_query,
                *build_rag_queries(current_query, history=prior_history),
            ]
            rag_queries: list[str] = []
            for q in candidates:
                if q and q not in rag_queries:
                    rag_queries.append(q)
            # Каждый запрос = отдельный ретрив + reranker на CPU (дорого). Ограничиваем
            # веер до 3: сырая реплика + condensed + один контекстный/слоевой запрос.
            rag_queries = rag_queries[:_MAX_FOLLOWUP_RAG_QUERIES]
            prioritize_raw = is_follow_up_clarification(current_query)
        else:
            rag_queries = [current_query] if current_query else []
        rag = await self._retrieve_rag(
            rag_queries or current_query, prioritize_first=prioritize_raw
        )
        rag_sources = rag["sources"]
        rag_msg = None
        if rag["context_str"]:
            rag_msg = self._rag_context_message(rag["context_str"])
            messages.append(rag_msg)

        budget = self.model_context_window - self.response_tokens - self.safety_margin
        messages = fit_to_budget(messages, budget)

        # fit_to_budget поднимает все system-сообщения в начало. Для RAG это плохо:
        # блок источников оказывается далеко от вопроса, а свежие реплики диалога
        # перевешивают. Ставим источники вплотную перед последним вопросом.
        if rag_msg is not None and rag_msg in messages:
            messages.remove(rag_msg)
            messages.insert(max(len(messages) - 1, 0), rag_msg)

        stream = await self.llm.chat.completions.create(
            model=self.default_model,
            messages=messages,
            stream=True,
            max_tokens=self.response_tokens,
            stream_options={"include_usage": True},
        )

        parts: list[str] = []
        interrupted = False
        try:
            async for chunk in stream:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    parts.append(text)
                    yield {"type": "token", "delta": text}
        except Exception as exc:
            interrupted = True
            logger.warning("chat_stream_interrupted", chat_id=str(chat_id), error=str(exc))

        assistant_text = "".join(parts)
        if assistant_text:
            # Оставляем в тексте только цитаты, реально использованные моделью:
            # источник без [n] в ответе не показываем, чтобы футер не врал.
            used_sources = _filter_used_sources(assistant_text, rag_sources)
            assistant_message = ChatMessage(
                chat_id=chat_id,
                role="assistant",
                content=assistant_text,
                sources=used_sources or None,
                tokens=count_tokens([{"role": "assistant", "content": assistant_text}]),
                prompt_id=prompt_id,
            )
            saved = await self.repository.append_message(chat_id, assistant_message)
            yield {"type": "message_saved", "message_id": str(saved.id)}
            if used_sources:
                yield {"type": "sources", "sources": used_sources}
            if interrupted:
                logger.info(
                    "chat_partial_response_saved",
                    chat_id=str(chat_id),
                    chars=len(assistant_text),
                )

    async def send_message_text(self, chat_id: UUID, user_content: str) -> AsyncIterator[str]:
        """Legacy SSE для JSON API (/chats/{id}/messages с JSON body)."""
        async for event in self.send_message(chat_id, user_content):
            if event.get("type") == "token":
                yield event["delta"]
