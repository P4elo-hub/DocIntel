import re
from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from fastapi import UploadFile

from app.chat.context import build_sliding_context
from app.chat.domain import Chat, ChatMessage
from app.chat.media import VOICE_UNAVAILABLE_MESSAGE, extract_rag_query, media_to_part
from app.core.exceptions import VoiceUnavailableError
from app.chat.prompt_selection import choose_by_split
from app.chat.repository import ChatRepository, SystemPromptRepository
from app.chat.tokens import count_tokens, fit_to_budget
from app.moderation.domain import ModerationResult
from app.moderation.service import ModerationService

logger = structlog.get_logger("chat-service")


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

    async def _retrieve_rag(self, question: str) -> dict:
        """Вариант C: ищет контекст в базе знаний. Сбой/незрелый индекс —
        не роняет чат: возвращаем пустой результат, отвечаем без цитат."""
        if not self.rag_enabled or self.rag_service is None or not question.strip():
            return {"context_str": "", "sources": []}
        try:
            result = await self.rag_service.retrieve_context(question)
        except Exception as exc:
            logger.warning("rag_retrieve_failed", error=str(exc))
            return {"context_str": "", "sources": []}
        if not result.get("confident"):
            return {"context_str": "", "sources": []}
        return {
            "context_str": result.get("context_str", ""),
            "sources": result.get("sources", []),
        }

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
                "4. Если ответа в источниках нет или они не относятся к вопросу — "
                "честно напиши: «В базе знаний я не нашёл ответа на этот вопрос», "
                "и не придумывай цитат.\n"
                "5. Термины и аббревиатуры (например, DCA, БПХ, BC) понимай в "
                "контексте продукта «История операций» по этим источникам. Если "
                "твои предыдущие ответы в этом диалоге противоречат источникам — "
                "источники приоритетны, игнорируй прежние ответы и не повторяй их.\n\n"
                "---------------------\n"
                f"{context_str}\n"
                "---------------------"
            ),
        }

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

        user_message = ChatMessage(
            chat_id=chat_id,
            role="user",
            content=user_content,
            media_refs=media_refs,
            prompt_id=prompt_id,
        )
        await self.repository.append_message(chat_id, user_message)

        messages = await build_sliding_context(
            self.repository,
            chat,
            chat_id,
            context_window=self.context_window,
            system_prompt_body=prompt_body,
        )

        # Вариант C: подмешиваем найденные в базе знаний чанки как system-контекст.
        # fit_to_budget сохраняет system-сообщения, поэтому контекст не обрежется.
        rag = await self._retrieve_rag(extract_rag_query(user_content, media_refs))
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
