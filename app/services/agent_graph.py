"""DocIntel на LangGraph: classify_agent + три рабочих сценария.

Архитектура (диплом / Telegram):

    START → classify_agent
              ├─ search  → retrieve_rag (Qdrant) → END
              ├─ write   → retrieve_rag → write_agent → validate_agent → END
              └─ answer  → retrieve_rag → answer_agent → validate_agent → END

Три сценария:
1. **search** — только векторный поиск в Qdrant (чанки).
2. **write** — документация фичи: Qdrant → kit-написнание → валидация по Qdrant.
3. **answer** — ответ на вопрос: Qdrant → формулировка → валидация по Qdrant.

Retrieval всегда через ``RAGService`` / Qdrant, не через lexical ``search_kb``.

Агенты **независимы** (нет общей LLM-сессии / shared message history).

Для ДЗ Б6.3 ниже оставлены также ReAct-варианты (один агент с обоими tools):
``react_custom_graph`` / ``prebuilt_react_graph`` — для бенчмарка и отчёта.
"""

from __future__ import annotations

import logging
import operator
import re
from functools import lru_cache
from typing import Annotated, Any, Literal, TypedDict

log = logging.getLogger(__name__)

from langchain.agents import create_agent
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import get_settings
from app.prompts.loader import build_system_prompt, load_tool_description
from app.tools.registry import ToolHandlers
from app.tools.search_kb import SearchKbHandler

MAX_ITERATIONS = 6

# ---------------------------------------------------------------------------
# Handlers / tools (боевые DocIntel)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _handlers() -> ToolHandlers:
    """Handlers для write_feature_doc (methodology/shablon) + мелкий DocIntel KB."""
    docintel = get_settings().docintel
    return ToolHandlers(
        knowledge_base_path=docintel.knowledge_base_path,
        docs_dir=docintel.docs_dir,
        methodology_dir=docintel.methodology_dir,
        shablon_path=docintel.shablon_path,
    )


@lru_cache(maxsize=1)
def _rag_kb_handler() -> SearchKbHandler:
    """Поиск по корпусу RAG (data/my-kb и т.п.) — основная база диплома."""
    settings = get_settings()
    return SearchKbHandler(
        knowledge_base_path=None,
        docs_dir=settings.rag_data_dir,
    )


def _reset_kb_handlers() -> None:
    """Сброс кэша handlers после обновления индекса/кода поиска."""
    _rag_kb_handler.cache_clear()
    _handlers.cache_clear()


@tool("search_kb")
def search_kb(query: str) -> str:
    """Поиск по проектной документации: корпус RAG (my-kb) + DocIntel docs/KB.

    Для имён обменов/API в запросе — приоритет файла по имени и секций
    «запрос/ответ», а не посторонний token-overlap.
    """
    rag_hit = _rag_kb_handler().search_kb(query)
    docintel_hit = _handlers().search_kb(query)

    parts: list[str] = []
    if rag_hit and "Ничего не найдено" not in rag_hit:
        parts.append(f"### Корпус RAG (`{get_settings().rag_data_dir}`)\n{rag_hit}")
    if docintel_hit and "Ничего не найдено" not in docintel_hit:
        parts.append(f"### DocIntel docs\n{docintel_hit}")

    if parts:
        return "\n\n".join(parts)
    return rag_hit or docintel_hit


search_kb.description = (
    load_tool_description("search_kb").replace(
        "{{ service_name }}", get_settings().docintel.service_name
    )
    + "\n\nИщет и в корпусе RAG (`RAG_DATA_DIR`, напр. data/my-kb), и в app/data/docs."
)


@tool("write_feature_doc")
def write_feature_doc(
    feature_brief: str,
    section_id: str | None = None,
    protocol: str | None = None,
    feature_name: str | None = None,
) -> str:
    """Написание документации новой фичи по shablon.md и standard kits."""
    return _handlers().write_feature_doc(
        feature_brief=feature_brief,
        section_id=section_id,
        protocol=protocol,
        feature_name=feature_name,
    )


write_feature_doc.description = load_tool_description("write_feature_doc")

TOOLS: list[BaseTool] = [search_kb, write_feature_doc]
TOOLS_BY_NAME: dict[str, BaseTool] = {t.name: t for t in TOOLS}


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def build_model(*, temperature: float = 0.0) -> ChatOpenAI:
    settings = get_settings()
    timeout = max(settings.llm.request_timeout, settings.docintel.request_timeout_seconds)
    return ChatOpenAI(
        model=settings.llm.default_model,
        temperature=temperature,
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Два отдельных агента
# ---------------------------------------------------------------------------

SEARCH_AGENT_PROMPT = (
    "Ты агент поиска DocIntel. Задача — собрать документ контекста из KB "
    "через tool `search_kb` (1–4 вызова).\n"
    "Правила (для любого обмена/системы из брифа):\n"
    "- Если в брифе есть имя обмена/API/системы — ищи по нему отдельными query, "
    "не только по новым словам доработки.\n"
    "- Для написания документации дополнительно ищи: "
    "«описание запроса/ответа», «параметры запроса», «параметры ответа», «пример».\n"
    "- В tool-результатах должны остаться таблицы полей и примеры из KB; "
    "не заменяй их выдуманным контрактом.\n"
    "- Для intent=search в финале дай выжимку фактов. "
    "Для write сырой tool-output важнее пересказа.\n"
    "- Не пиши документ фичи — других tools нет."
)

def build_search_agent():
    """Отдельный агент поиска (только search_kb)."""
    return create_agent(
        build_model(),
        tools=[search_kb],
        system_prompt=SEARCH_AGENT_PROMPT,
        name="search_agent",
    )


@lru_cache(maxsize=1)
def _section_writer_client():
    """Клиент DocIntel для sectioned kit-pipeline (write_agent)."""
    from app.services.docintel import ToolCallClient

    return ToolCallClient(settings=get_settings())


search_agent = build_search_agent()  # только для ReAct/бенчмарка Б6.3, не DocIntel pipeline


# ---------------------------------------------------------------------------
# Qdrant RAG (боевой контур DocIntel)
# ---------------------------------------------------------------------------

_rag_service: Any | None = None


def set_rag_service(rag: Any | None) -> None:
    """Инжект RAGService из lifespan / ChatService."""
    global _rag_service
    _rag_service = rag


def get_rag_service() -> Any | None:
    """Текущий RAGService (Qdrant) или None, если ещё не готов."""
    return _rag_service


# ---------------------------------------------------------------------------
# Родительский граф: retrieve_rag → write/answer → validate
# ---------------------------------------------------------------------------


IntentLabel = Literal["search", "write", "answer", "chat", "reject"]


class DocIntelState(TypedDict):
    """State оркестратора. Только сериализуемые поля (задел под checkpointer)."""

    user_request: str
    # Исходная реплика пользователя (до condense); для answer/validate.
    original_user_message: str
    # История диалога: classify решает, оставить или обнулить (use_history).
    chat_history: str
    use_history: bool
    intent: IntentLabel
    search_context: str
    # Чистый контекст Qdrant (без подмешивания истории чата).
    rag_context: str
    # Цитаты Qdrant из retrieve_rag: [{id, file_name, page, score, snippet}, ...]
    rag_sources: list
    draft_answer: str
    final_answer: str
    # для отчёта / трейсинга
    agents_called: Annotated[list[str], operator.add]


def format_sources_section(sources: list | None) -> str:
    """Markdown-блок «Источники» по цитатам Qdrant."""
    if not sources:
        return ""
    lines = ["## Источники"]
    for s in sources:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        name = s.get("file_name") or "unknown"
        page = s.get("page")
        suffix = f", стр. {page}" if page not in (None, "") else ""
        if sid is not None:
            lines.append(f"[{sid}] {name}{suffix}")
        else:
            lines.append(f"- {name}{suffix}")
    return "\n".join(lines) if len(lines) > 1 else ""


def append_sources_section(answer: str, sources: list | None) -> str:
    """Добавляет раздел источников в конец ответа, если его ещё нет."""
    text = (answer or "").rstrip()
    if not text or not sources:
        return text
    if re.search(r"(?m)^#{1,3}\s*Источники\b", text):
        return text
    section = format_sources_section(sources)
    if not section:
        return text
    return f"{text}\n\n{section}"


_REJECT_MESSAGE = (
    "Я DocIntel — ассистент только по проектной документации "
    "(поиск, ответы по KB и генерация разделов фичи).\n\n"
    "Вопросы вне документации продукта обработать не могу. "
    "Сформулируй запрос про документ, обмен/API, контракт или бриф на раздел."
)

# Признаки, что запрос вообще про нашу документацию/продукт (не предметные примеры).
_DOC_DOMAIN_HINTS = re.compile(
    r"("
    r"документац|документ\w*|docintel|баз\w*\s+знан|knowledge\s*base|\bkb\b|"
    r"интеграц|обмен|endpoint|\bapi\b|контракт|use\s*case|usecase|"
    r"фич[аиеу]|раздел\w*|методолог|shablon|шаблон|"
    r"параметр\w*|поле|запрос|ответ|request|response|payload|schema|"
    r"спецификац|бриф|nfr|observab|webhook|\brest\b|grpc|kafka|soap|"
    r"требования|сценари\w*|импорт|confluence|"
    r"композит|composite|history\s*ops|истори[яи]\s*операц|"
    r"налог|tax|бph|bph|\bog\b|order\s*gateway|"
    r"вариацион\w*|varmargin|вар\.?\s*марж|"
    r"деталка|лент[аеуы]|screen\s*data|"
    # SEND OPERATIONS / GET_DETAILS / get_operations — с пробелами и без
    r"get[\s_]*operations|send[\s_]*operations|get[\s_]*details|"
    r"send[\s_]*details|get[\s_]*linked|linked[\s_]*events|"
    r"screen[\s_]*api|send[\s_]*operations[\s_]*feed"
    r")",
    re.IGNORECASE,
)

# Ответ по KB (пример/контракт/пояснение) → сценарий answer, не write.
_ANSWER_HINTS = re.compile(
    r"("
    r"(приведи|покажи|дай|какой|каков\w*|как выглядит|есть ли|объясни|расскажи)\w*"
    r".{0,40}(пример|request|response|запрос|ответ|контракт|параметр|"
    r"поле|schema|payload|обмен|endpoint|api|интеграц|операц|налог|json)|"
    r"пример\s+(запроса|ответа|request|response|операц)|"
    r"пример\s+ответа\s+для|"
    r"какие\s+(поля|параметры|коды)|"
    r"как\s+работает\s+.{0,40}(обмен|api|endpoint|интеграц|импорт|ручку)|"
    r"что\s+такое\s+.{0,40}(обмен|api|endpoint|интеграц|фич|контракт)|"
    r"(операци\w*|пример).{0,40}(налог|tax|композит|composite)|"
    r"(налог|tax).{0,40}(композит|composite|операц|пример)"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# «Просто найди / покажи куски» без формулировки ответа.
_SEARCH_ONLY_HINTS = re.compile(
    r"^(найди|поищи|search|покажи\s+источник|в\s+какой\s+файл)",
    re.IGNORECASE,
)

_WRITE_HINTS = re.compile(
    r"("
    r"задокументир|"
    r"(сделай|напиши|написать|подготовь|составь|сгенерируй|нужн\w*|требуется)\w*"
    r".{0,40}документац|"
    r"(сделай|напиши|написать|подготовь|составь)\s+(мне\s+)?"
    r"(фич|раздел|ручку|endpoint|api|изменен|spec|документ)|"
    r"опиши\s+(фич|интеграц|ручку|endpoint)|"
    r"новая\s+(фича|ручка|интеграц)|"
    r"контекст\s+для\s+фич|"
    r"задача\s*\(?\s*бриф|"
    r"##\s*задача|"
    r"(добавить|новый)\s+.{0,20}параметр|"
    r"пробросить|"
    r"write_feature|"
    r"section_id|"
    r"документац\w*\s*[:\-–]|"
    r"документац\w*\s+(фич|для|по|новый|параметр)|"
    r"сгенерируй\s+(документ|раздел|spec|документац)|"
    r"ручку\s+интеграц|"
    r"переимен|"
    r"измени\s+(название|параметр|поле|ручку)"
    r")",
    re.IGNORECASE | re.DOTALL,
)

_CHITCHAT = re.compile(
    r"^(привет|здравств|добрый\s+(день|вечер|утро)|как дела|спасибо|благодар|пока|hey|hello)\b",
    re.IGNORECASE,
)

# «Сделай ещё раз / выполни задачу» — не answer, а повтор предыдущего сценария.
_REDO_TASK_RE = re.compile(
    r"("
    r"ещ[её]\s+раз|заново|повтор|"
    r"переделай|перепиши|перегенера|"
    r"выполни\s+(эту\s+)?задач|"
    r"сделай\s+(эту\s+)?задач|"
    r"а\s+ну[- ]ка"
    r")",
    re.IGNORECASE,
)

_INTENT_LABELS = frozenset({"search", "write", "answer", "chat", "reject"})
_HISTORY_LABELS = frozenset({"history", "fresh"})

_CLASSIFY_AGENT_PROMPT = (
    "Ты classify_agent DocIntel. Реши две вещи по смыслу (как человек в диалоге), "
    "не по спискам ключевых слов.\n"
    "Верни РОВНО две метки через пробел: <intent> <history_mode>\n"
    "Без пояснений, без пунктуации, без кавычек.\n"
    "\n"
    "## intent\n"
    "answer — пользователь хочет ОТВЕТ по документации/контракту/примеру "
    "(JSON, поля, маппинг, «как выглядит», «пришли пример», «переложи в формат X», "
    "уточнение «это не то / не тот слой / на фронт»). "
    "Даже если он злится или говорит «ещё раз» — если цель получить ответ/пример, "
    "это answer, НЕ write.\n"
    "write — пользователь хочет НАПИСАТЬ или ПЕРЕПИСАТЬ документ фичи "
    "(бриф, разделы спеки, «задокументируй», «сделай документацию», "
    "«переделай документ»). Повтор «ещё раз» → write только если в диалоге "
    "реально была задача на документ, а не просьба снова прислать JSON.\n"
    "search — явно просит только найти/показать куски KB без ответа.\n"
    "chat — привет / спасибо без задачи.\n"
    "reject — ТОЛЬКО темы вне продукта DocIntel/Истории операций "
    "(погода, шутки, рецепты, общий код без KB). "
    "НЕ reject: имя операции/термин продукта («Вариационная маржа», «налог»), "
    "обмен/формат («SEND OPERATIONS»), «деталка», «лента», «композит», "
    "короткое уточнение после диалога про KB — это answer.\n"
    "\n"
    "## history_mode\n"
    "Спроси себя: чтобы правильно выполнить ТЕКУЩУЮ реплику, нужно ли видеть "
    "предыдущие сообщения (прошлый JSON, прошлый неверный ответ, ту же операцию)?\n"
    "history — да: уточнение, исправление, «не то», «на фронт», «в тот формат», "
    "короткий целевой формат/имя операции после примера или отказа, "
    "ссылка на прошлый ответ, продолжение той же задачи.\n"
    "fresh — нет: новый самодостаточный вопрос, который понятен без диалога; "
    "или смена темы на другой обмен/фичу без отсылки к прошлому.\n"
    "\n"
    "## Жёсткие правила\n"
    "1) Нет блока «Контекст диалога» или он пуст → только fresh.\n"
    "2) chat → всегда fresh. reject → всегда fresh, и только для тем вне продукта.\n"
    "3) Не путай write и answer: просьба примера/JSON/формата = answer.\n"
    "4) Не ставь fresh, если без прошлого ответа/примера текущую реплику "
    "нельзя корректно выполнить.\n"
    "5) Не ставь history «на всякий случай», если вопрос полный сам по себе "
    "и не опирается на диалог.\n"
    "6) Короткое имя операции/термина после диалога про документацию = "
    "answer history, никогда reject.\n"
    "\n"
    "Примеры (формат ответа):\n"
    "answer history\n"
    "answer fresh\n"
    "write history\n"
    "reject fresh"
)


def _history_looks_like_write(chat_history: str) -> bool:
    h = (chat_history or "").lower()
    if not h:
        return False
    if _WRITE_HINTS.search(chat_history):
        return True
    return bool(
        re.search(
            r"(документац|задокументир|##\s*задача|бриф|write_|раздел\s*4\.|"
            r"use\s*case|добав(ить|ление).{0,40}параметр)",
            h,
            re.IGNORECASE,
        )
    )


def _looks_like_write_brief(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _WRITE_HINTS.search(t):
        return True
    return bool(
        re.search(
            r"(документац|задокументир|##\s*задача|бриф|"
            r"добав(ить|ление).{0,40}параметр|"
            r"доработка.{0,40}(обмен|интеграц))",
            t,
            re.IGNORECASE,
        )
    )


def detect_use_history_heuristic(
    user_request: str,
    *,
    chat_history: str = "",
) -> bool:
    """Fallback: нужна ли история чата для текущей реплики."""
    from app.chat.rag_query import (
        _DIALOG_REFERENCE_RE,
        is_follow_up_clarification,
        needs_context_expansion,
    )

    text = (user_request or "").strip()
    history = (chat_history or "").strip()
    if not text or not history:
        return False
    if _CHITCHAT.search(text):
        return False
    # Fallback only (если LLM classify не распарсился).
    if is_follow_up_clarification(text) or _DIALOG_REFERENCE_RE.search(text):
        return True
    if needs_context_expansion(text):
        return True
    if _WRITE_HINTS.search(text) and len(text) > 120:
        return False
    if len(text) >= 100 and _DOC_DOMAIN_HINTS.search(text):
        return False
    return False


def detect_intent_heuristic(
    user_request: str,
    *,
    chat_history: str = "",
) -> IntentLabel:
    """Fallback intent (без решения history — см. detect_use_history_heuristic)."""
    text = user_request.strip()
    history = (chat_history or "").strip()
    use_hist = detect_use_history_heuristic(text, chat_history=history)
    in_doc_dialog = bool(history and _DOC_DOMAIN_HINTS.search(history) and use_hist)

    if not text or _CHITCHAT.search(text):
        return "chat"
    if _WRITE_HINTS.search(text):
        return "write"
    if _SEARCH_ONLY_HINTS.search(text) and (
        _DOC_DOMAIN_HINTS.search(text) or in_doc_dialog
    ):
        return "search"
    if _SEARCH_ONLY_HINTS.search(text) and not _DOC_DOMAIN_HINTS.search(text):
        return "reject"
    if _ANSWER_HINTS.search(text) or (
        _DOC_DOMAIN_HINTS.search(text)
        and re.search(r"(как|что|какой|где|покажи|приведи|объясни)", text, re.I)
    ):
        return "answer"
    if in_doc_dialog and re.search(
        r"(данн|текущ|предыдущ|формат|пример|трансформ|операц|полож|как\s+оно)",
        text,
        re.I,
    ):
        return "answer"
    # Короткий продуктный термин без глагола («Вариационная маржа.») — answer, не reject.
    if _DOC_DOMAIN_HINTS.search(text):
        return "answer"
    return "reject"


def _parse_intent_label(raw: str) -> IntentLabel | None:
    token = (raw or "").strip().lower().split()[0] if (raw or "").strip() else ""
    token = token.strip(".,:;!?\"'`")
    if token in _INTENT_LABELS:
        return token  # type: ignore[return-value]
    return None


def _parse_classify_response(raw: str) -> tuple[IntentLabel | None, bool | None]:
    """Парсит «answer history» / «write fresh» → (intent, use_history)."""
    parts = re.split(r"\s+", (raw or "").strip().lower())
    parts = [p.strip(".,:;!?\"'`") for p in parts if p.strip(".,:;!?\"'`")]
    if not parts:
        return None, None
    intent = parts[0] if parts[0] in _INTENT_LABELS else None
    use_history: bool | None = None
    if len(parts) >= 2 and parts[1] in _HISTORY_LABELS:
        use_history = parts[1] == "history"
    elif intent is None:
        # Иногда модель пишет только history/fresh или наоборот порядок.
        for p in parts:
            if p in _INTENT_LABELS:
                intent = p  # type: ignore[assignment]
            if p in _HISTORY_LABELS:
                use_history = p == "history"
    return intent, use_history


async def _condense_with_history(current: str, chat_history: str) -> str:
    """Свернуть follow-up в самостоятельный запрос (когда use_history=True).

    Вызывается только если classify уже выбрал history — всегда сворачиваем,
    иначе длинные правки («ты уверен? … неверно … комиссии») остаются без
    якоря обмена и RAG уезжает не туда.
    """
    from app.chat.rag_query import CONDENSE_SYSTEM_PROMPT

    text = (current or "").strip()
    history = (chat_history or "").strip()
    if not text or not history:
        return text
    try:
        model = build_model(temperature=0.0).bind(max_tokens=200)
        response = await model.ainvoke(
            [
                SystemMessage(content=CONDENSE_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Контекст диалога:\n{history[:4000]}\n\n"
                        f"Последний вопрос пользователя: {text}\n\n"
                        "Самостоятельный поисковый запрос:"
                    )
                ),
            ]
        )
        content = response.content
        raw = (content if isinstance(content, str) else str(content)).strip()
        raw = raw.strip("\"'` ")
        if raw and len(raw) < 500:
            log.info("classify_condense original=%r condensed=%r", text[:100], raw[:100])
            return raw
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_condense_failed: %s", exc)
    return text


async def classify_request(
    user_request: str,
    *,
    chat_history: str = "",
) -> tuple[IntentLabel, bool]:
    """classify_agent: (intent, use_history) — решение модели по промпту.

    Regex/эвристики НЕ перетирают ответ модели. Fallback — только если
    ответ не распарсился или LLM упал.
    """
    text = user_request.strip()
    history = (chat_history or "").strip()
    if not text:
        return "chat", False

    classify_input = f"Текущая реплика пользователя:\n{text[:2000]}"
    if history:
        classify_input = (
            "Контекст диалога (предыдущие сообщения). "
            "Реши по смыслу, нужны ли они для текущей реплики:\n"
            f"{history[:4000]}\n\n"
            f"{classify_input}"
        )
    else:
        classify_input = (
            "Контекст диалога: _(нет предыдущих сообщений — history_mode=fresh)_\n\n"
            + classify_input
        )

    try:
        model = build_model(temperature=0.0).bind(max_tokens=16)
        response = await model.ainvoke(
            [
                SystemMessage(content=_CLASSIFY_AGENT_PROMPT),
                HumanMessage(content=classify_input),
            ]
        )
        content = response.content
        raw = content if isinstance(content, str) else str(content)
        label, use_hist = _parse_classify_response(raw)
        if label is not None:
            if not history:
                use_hist = False
            elif use_hist is None:
                # Модель не вернула history_mode — мягкий fallback только тогда.
                use_hist = detect_use_history_heuristic(text, chat_history=history)
            # Safety: gpt-4o-mini иногда reject'ит продуктные термины («Вариационная маржа»).
            if label == "reject":
                in_doc_hist = bool(history and _DOC_DOMAIN_HINTS.search(history))
                looks_product = bool(_DOC_DOMAIN_HINTS.search(text))
                if looks_product or (in_doc_hist and len(text) <= 160):
                    log.warning(
                        "classify_override reject→answer query=%r hist=%s",
                        text[:120],
                        in_doc_hist,
                    )
                    label = "answer"
                    use_hist = bool(history) and (
                        bool(use_hist)
                        or in_doc_hist
                        or detect_use_history_heuristic(text, chat_history=history)
                    )
            if label in {"chat", "reject"}:
                use_hist = False
            log.info(
                "classify_agent label=%s use_history=%s query=%r",
                label,
                bool(use_hist),
                text[:120],
            )
            return label, bool(use_hist)
        log.warning("classify_agent_unparsed raw=%r — fallback heuristic", raw[:80])
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_agent_failed: %s — fallback heuristic", exc)

    label = detect_intent_heuristic(text, chat_history=history)
    use_hist = detect_use_history_heuristic(text, chat_history=history)
    log.info(
        "intent_heuristic label=%s use_history=%s query=%r",
        label,
        use_hist,
        text[:120],
    )
    return label, use_hist


async def detect_intent(
    user_request: str,
    *,
    chat_history: str = "",
) -> IntentLabel:
    """Совместимость: только intent (без use_history)."""
    intent, _use_history = await classify_request(
        user_request, chat_history=chat_history
    )
    return intent


def _last_ai_text(messages: list[AnyMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", None) or []):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _tool_texts(messages: list[AnyMessage]) -> str:
    chunks = [
        str(m.content)
        for m in messages
        if isinstance(m, ToolMessage) and str(m.content).strip()
    ]
    return "\n\n".join(chunks)


def _history_block(state: DocIntelState) -> str:
    """История уже отфильтрована classify (пустая = fresh)."""
    history = (state.get("chat_history") or "").strip()
    if not history:
        return ""
    return (
        "\n\nКонтекст диалога (classify решил, что он нужен — "
        "бери данные операции/пример отсюда; целевой обмен/API — "
        "из текущего вопроса, не подменяй чужим из истории):\n"
        f"{history[:24_000]}\n"
    )


def _merge_chat_contracts_into_kb(
    search_context: str,
    chat_history: str,
    *,
    user_request: str = "",
) -> str:
    """Больше не подмешивает историю в KB.

    Раньше прошлые JSON-ответы попадали в search_context и validate принимал
    их за «документацию» — отсюда выдуманные/чужие контракты. История идёт
    отдельно в answer/write как диалог, не как источник истины.
    """
    del chat_history, user_request
    return (search_context or "").strip()


async def classify_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Анализ запроса: intent + нужно ли пробрасывать историю чата дальше.

    Решение — только classify_agent (LLM). Downstream доверяет use_history:
    если True — в state кладём историю; если False — обнуляем.
    """
    from app.chat.media import normalize_domain_query

    original = normalize_domain_query(
        (state.get("original_user_message") or state.get("user_request") or "")
    )
    available_history = (state.get("chat_history") or "").strip()

    intent, use_history = await classify_request(
        original,
        chat_history=available_history,
    )
    if not available_history:
        use_history = False

    out: dict[str, Any] = {
        "intent": intent,
        "use_history": use_history,
        "agents_called": ["classify_agent"],
    }

    if use_history:
        # Condense только для поиска; intent уже зафиксирован моделью и не меняем.
        condensed = await _condense_with_history(original, available_history)
        out["user_request"] = condensed
        out["chat_history"] = available_history
        log.info(
            "classify_agent history=ON intent=%s chars=%d query=%r",
            intent,
            len(available_history),
            condensed[:120],
        )
    else:
        out["user_request"] = original
        out["chat_history"] = ""
        log.info("classify_agent history=OFF intent=%s query=%r", intent, original[:120])

    if intent == "chat":
        out["final_answer"] = (
            "Привет! Я DocIntel — только по проектной документации:\n"
            "• поиск по KB;\n"
            "• ответ по документации;\n"
            "• написание документации фичи.\n"
            "Другие темы не обрабатываю."
        )
    elif intent == "reject":
        out["final_answer"] = _REJECT_MESSAGE
    return out


# Обратная совместимость имени узла в старых ссылках/тестах.
intent_node = classify_agent_node


async def retrieve_rag_node(state: DocIntelState) -> dict[str, Any]:
    """Векторный retrieval из Qdrant → search_context (без search_kb / ReAct)."""
    request = (state.get("user_request") or "").strip()
    original = (state.get("original_user_message") or request).strip()
    intent = state.get("intent")
    history = (state.get("chat_history") or "").strip()
    rag = get_rag_service()

    if rag is None:
        log.error("retrieve_rag: RAGService/Qdrant не готов")
        msg = "База знаний (Qdrant) ещё не готова. Попробуй через минуту."
        out: dict[str, Any] = {
            "search_context": "",
            "final_answer": msg,
            "agents_called": ["retrieve_rag"],
        }
        return out

    from app.chat.media import extract_contract_anchors, normalize_domain_query

    queries: list[str] = []
    norm_original = normalize_domain_query(original)
    norm_request = normalize_domain_query(request)
    for q in (original, norm_original, request, norm_request):
        q = (q or "").strip()
        if q and q not in queries:
            queries.append(q)

    # Якоря обмена из текущей реплики + истории (Linked Events ≠ LinkedIn,
    # иначе RAG уезжает в чужой screenData/комиссию композита).
    for anchor in extract_contract_anchors(norm_original, norm_request, history):
        if anchor not in queries:
            queries.append(anchor)
    queries = queries[:5]

    print(
        f"  → retrieve_rag: Qdrant retrieval queries={len(queries)}",
        flush=True,
    )
    try:
        result = await rag.retrieve_context_multi(queries, prioritize_first=True)
    except Exception as exc:  # noqa: BLE001
        log.exception("retrieve_rag_failed")
        out = {
            "search_context": "",
            "final_answer": f"Ошибка поиска в Qdrant: {exc}",
            "agents_called": ["retrieve_rag"],
        }
        return out

    context = (result.get("context_str") or "").strip()
    sources = list(result.get("sources") or [])
    log.info(
        "retrieve_rag intent=%s confident=%s top_score=%s sources=%d chars=%d",
        intent,
        result.get("confident"),
        result.get("top_score"),
        len(sources),
        len(context),
    )

    out = {
        # search_context = только Qdrant (история НЕ подмешивается).
        "search_context": context,
        "rag_context": context,
        "rag_sources": sources,
        "agents_called": ["retrieve_rag"],
    }
    if intent == "search":
        body = context or "Ничего релевантного не найдено в базе знаний (Qdrant)."
        out["final_answer"] = append_sources_section(body, sources)
    return out


# Обратная совместимость имени узла.
search_agent_node = retrieve_rag_node


async def write_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Сценарий write: kit-subagents → draft документа фичи."""
    from app.services.docintel.orchestrator import SectionOrchestrator
    from app.tools.feature_sections import build_execution_plan

    brief = state["user_request"]
    original = (state.get("original_user_message") or brief).strip()
    history = (state.get("chat_history") or "").strip()
    # history уже пустая, если classify сказал fresh.
    if history:
        brief = (
            f"{brief}\n\n"
            "Контекст диалога (classify оставил историю — "
            "в integration опиши обмены из текущего брифа, не подменяй "
            "чужими из истории):\n"
            f"{history[:16_000]}"
        )
    # KB = только Qdrant; история уже в brief как диалог, не как контракт.
    kb = (state.get("rag_context") or state.get("search_context") or "").strip()
    plan = build_execution_plan(brief)
    kit_names = [step.tool_name for step in plan]
    result = await SectionOrchestrator(_section_writer_client()).generate(
        brief,
        search_context=kb,
    )
    answer = (result.text or "").strip()
    agents = ["write_agent", *kit_names]
    return {
        "draft_answer": answer,
        "final_answer": answer,
        "agents_called": agents,
    }


async def answer_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Сценарий answer: формулировка ответа по search_context + история → draft."""
    from app.services.docintel.answer_agent import write_answer_from_kb

    print("  → answer_agent: формулировка ответа по KB", flush=True)
    original = (state.get("original_user_message") or "").strip()
    standalone = (state.get("user_request") or "").strip()
    user_request = standalone
    if original and original != standalone:
        user_request = (
            f"Исходная реплика: {original}\n"
            f"Самостоятельная формулировка (с учётом диалога): {standalone}"
        )
    # history уже пустая при fresh — второй раз не режем regex'ами.
    history = (state.get("chat_history") or "").strip()
    draft = await write_answer_from_kb(
        _section_writer_client(),
        user_request=user_request,
        search_context=state.get("search_context") or "",
        chat_history=history,
    )
    return {
        "draft_answer": draft,
        "final_answer": draft,
        "agents_called": ["answer_agent"],
    }


async def validate_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Независимый review: сверяет draft с чистым Qdrant (не с историей чата)."""
    from app.services.docintel.validator import validate_against_kb

    from app.chat.media import extract_contract_anchors, normalize_domain_query

    draft = (state.get("draft_answer") or state.get("final_answer") or "").strip()
    # Только Qdrant. Не search_context после старых merge и не прошлые ответы.
    kb = (state.get("rag_context") or state.get("search_context") or "").strip()
    original = normalize_domain_query(
        (state.get("original_user_message") or "").strip()
    )
    condensed = normalize_domain_query((state.get("user_request") or "").strip())
    history = (state.get("chat_history") or "").strip()
    brief = original or condensed
    if original and condensed and original != condensed:
        brief = f"{original}\n\n(поисковая формулировка: {condensed})"
    # Якорь обмена из истории (GET_LINKED_EVENTS), иначе follow-up про комиссии
    # уедет в screenData и hard-ground это «окнет».
    anchors = extract_contract_anchors(original, condensed, history)
    if anchors:
        brief = f"{brief}\n\n(целевой обмен/контракт: {'; '.join(anchors)})"
    mode = "answer" if state.get("intent") == "answer" else "document"
    print(
        f"  → validate_agent: независимый RAG-review всего документа (mode={mode})",
        flush=True,
    )
    fixed = await validate_against_kb(
        _section_writer_client(),
        feature_brief=brief,
        search_context=kb,
        draft_answer=draft,
        mode=mode,
    )
    # Источники из retrieve_rag — в конец ответа/документа (reject/chat сюда не доходят).
    fixed = append_sources_section(fixed, state.get("rag_sources") or [])
    return {
        "final_answer": fixed,
        "agents_called": ["validate_agent"],
    }


def route_after_classify(state: DocIntelState) -> Literal["retrieve_rag", "__end__"]:
    """chat/reject → END; search/write/answer → retrieve_rag (Qdrant)."""
    if state.get("intent") in {"chat", "reject"}:
        return "__end__"
    return "retrieve_rag"


def route_after_search(
    state: DocIntelState,
) -> Literal["write_agent", "answer_agent", "__end__"]:
    """После Qdrant: ветвление по сценарию; при сбое RAG — END."""
    intent = state.get("intent")
    # retrieve_rag положил final_answer при недоступном/упавшем Qdrant.
    if intent in {"write", "answer"}:
        if (state.get("final_answer") or "").strip() and not (
            state.get("search_context") or ""
        ).strip():
            return "__end__"
        if intent == "write":
            return "write_agent"
        return "answer_agent"
    return "__end__"


def build_docintel_graph():
    """classify → (Qdrant | Qdrant→write→validate | Qdrant→answer→validate)."""
    builder = StateGraph(DocIntelState)
    builder.add_node("classify_agent", classify_agent_node)
    builder.add_node("retrieve_rag", retrieve_rag_node)
    builder.add_node("write_agent", write_agent_node)
    builder.add_node("answer_agent", answer_agent_node)
    builder.add_node("validate_agent", validate_agent_node)

    builder.add_edge(START, "classify_agent")
    builder.add_conditional_edges(
        "classify_agent",
        route_after_classify,
        {"retrieve_rag": "retrieve_rag", "__end__": END},
    )
    builder.add_conditional_edges(
        "retrieve_rag",
        route_after_search,
        {
            "write_agent": "write_agent",
            "answer_agent": "answer_agent",
            "__end__": END,
        },
    )
    builder.add_edge("write_agent", "validate_agent")
    builder.add_edge("answer_agent", "validate_agent")
    builder.add_edge("validate_agent", END)
    return builder.compile()


docintel_graph = build_docintel_graph()


async def run_docintel_pipeline(
    user_request: str,
    *,
    chat_history: str = "",
    original_user_message: str = "",
    thread_id: str | None = None,
    rag_service: Any | None = None,
) -> dict[str, Any]:
    """Точка входа: classify (intent + use_history) → Qdrant → сценарий.

    ``chat_history`` — кандидат истории из БД чата; classify_agent решает,
    пробросить её дальше (history) или обнулить (fresh).
    ``rag_service`` — опциональный инжект RAGService (иначе берётся из set_rag_service).
    """
    if rag_service is not None:
        set_rag_service(rag_service)

    config: dict[str, Any] | None = None
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}

    original = original_user_message or user_request
    result = await docintel_graph.ainvoke(
        {
            "user_request": user_request,
            "original_user_message": original,
            "chat_history": chat_history or "",
            "use_history": False,
            "intent": "search",
            "search_context": "",
            "rag_context": "",
            "rag_sources": [],
            "draft_answer": "",
            "final_answer": "",
            "agents_called": [],
        },
        config=config,
    )
    sources = list(result.get("rag_sources") or [])
    answer = result.get("final_answer") or ""
    intent = result.get("intent")
    # На случай раннего выхода (ошибка Qdrant) — всё равно допишем источники.
    if intent not in {"reject", "chat"}:
        answer = append_sources_section(answer, sources)
    return {
        "intent": intent,
        "use_history": bool(result.get("use_history")),
        "user_request": result.get("user_request") or user_request,
        "search_context": result.get("search_context") or "",
        "rag_context": result.get("rag_context") or result.get("search_context") or "",
        "draft_answer": result.get("draft_answer") or "",
        "final_answer": answer,
        "agents_called": list(result.get("agents_called") or []),
        "answer": answer,
        "sources": sources,
    }


# ===========================================================================
# Б6.3 ReAct (один агент с обоими tools) — для бенчмарка/отчёта курса
# ===========================================================================


def _react_system_prompt() -> str:
    base = build_system_prompt(get_settings().docintel.service_name)
    return (
        f"{base}\n\n"
        "Ты ReAct-агент. Tools: `search_kb`, `write_feature_doc`. "
        "Если tools не нужны — ответь сразу."
    )


SYSTEM_PROMPT = _react_system_prompt()


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: Annotated[list[dict[str, Any]], operator.add]


async def call_model(state: AgentState) -> dict[str, Any]:
    model = build_model()
    response = await model.bind_tools(TOOLS).ainvoke(state["messages"])
    return {
        "messages": [response],
        "iteration_count": int(state.get("iteration_count", 0)) + 1,
    }


async def execute_tool(state: AgentState) -> dict[str, Any]:
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []
    messages: list[ToolMessage] = []
    results: list[dict[str, Any]] = []
    for call in tool_calls:
        name = call.get("name", "")
        args = call.get("args") or {}
        call_id = call.get("id") or name
        tool_obj = TOOLS_BY_NAME.get(name)
        if tool_obj is None:
            content = f"Ошибка: неизвестный tool `{name}`"
        else:
            try:
                content = str(await tool_obj.ainvoke(args))
            except Exception as exc:  # noqa: BLE001
                content = f"Ошибка tool `{name}`: {exc}"
        messages.append(ToolMessage(content=content, tool_call_id=call_id, name=name))
        results.append({"name": name, "args": args, "result": content})
    return {"messages": messages, "tool_results": results}


async def force_finish(state: AgentState) -> dict[str, Any]:
    messages = state["messages"]
    last = messages[-1] if messages else None
    iteration = int(state.get("iteration_count", 0))
    if iteration >= MAX_ITERATIONS and isinstance(last, AIMessage) and last.tool_calls:
        model = build_model()
        nudge = HumanMessage(
            content="Лимит итераций. Ответь финально без инструментов."
        )
        response = await model.ainvoke([*messages, nudge])
        return {"messages": [response]}
    return {}


def route_after_model(state: AgentState) -> Literal["execute_tool", "force_finish"]:
    if int(state.get("iteration_count", 0)) >= MAX_ITERATIONS:
        return "force_finish"
    last = state["messages"][-1] if state.get("messages") else None
    if getattr(last, "tool_calls", None):
        return "execute_tool"
    return "force_finish"


def build_custom_graph():
    """ReAct StateGraph (Б6.3) — один агент, оба tools."""
    builder = StateGraph(AgentState)
    builder.add_node("call_model", call_model)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("force_finish", force_finish)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        route_after_model,
        {"execute_tool": "execute_tool", "force_finish": "force_finish"},
    )
    builder.add_edge("execute_tool", "call_model")
    builder.add_edge("force_finish", END)
    return builder.compile()


def build_prebuilt_graph():
    return create_agent(
        build_model(),
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


# Имена из ДЗ Б6.3
custom_graph = build_custom_graph()
prebuilt_graph = build_prebuilt_graph()
# Алиасы «по смыслу»
react_custom_graph = custom_graph
prebuilt_react_graph = prebuilt_graph


def _initial_messages(question: str) -> list[AnyMessage]:
    return [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]


def _usage_from_messages(messages: list[AnyMessage]) -> dict[str, int]:
    prompt = completion = 0
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None) or {}
        prompt += int(usage.get("input_tokens") or 0)
        completion += int(usage.get("output_tokens") or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _count_model_steps(messages: list[AnyMessage]) -> int:
    return sum(1 for m in messages if isinstance(m, AIMessage))


async def run_naive_b62(question: str, *, max_iterations: int = MAX_ITERATIONS) -> dict[str, Any]:
    model = build_model()
    model_with_tools = model.bind_tools(TOOLS)
    messages: list[AnyMessage] = _initial_messages(question)
    tool_results: list[dict[str, Any]] = []
    for _ in range(max_iterations):
        response = await model_with_tools.ainvoke(messages)
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            break
        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args") or {}
            call_id = call.get("id") or name
            tool_obj = TOOLS_BY_NAME.get(name)
            if tool_obj is None:
                content = f"Ошибка: неизвестный tool `{name}`"
            else:
                try:
                    content = str(await tool_obj.ainvoke(args))
                except Exception as exc:  # noqa: BLE001
                    content = f"Ошибка tool `{name}`: {exc}"
            messages.append(ToolMessage(content=content, tool_call_id=call_id, name=name))
            tool_results.append({"name": name, "args": args, "result": content})
    else:
        messages.append(HumanMessage(content="Лимит. Ответь без tools."))
        messages.append(await model.ainvoke(messages))
    usage = _usage_from_messages(messages)
    return {
        "messages": messages,
        "tool_results": tool_results,
        "total_steps": _count_model_steps(messages),
        **usage,
        "answer": _last_ai_text(messages),
    }


async def run_custom_graph(
    question: str, *, thread_id: str | None = None
) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    result = await custom_graph.ainvoke(
        {
            "messages": _initial_messages(question),
            "iteration_count": 0,
            "tool_results": [],
        },
        config=config,
    )
    messages = list(result.get("messages") or [])
    usage = _usage_from_messages(messages)
    return {
        "messages": messages,
        "tool_results": list(result.get("tool_results") or []),
        "total_steps": int(result.get("iteration_count") or _count_model_steps(messages)),
        **usage,
        "answer": _last_ai_text(messages),
    }


async def run_prebuilt_graph(question: str) -> dict[str, Any]:
    result = await prebuilt_graph.ainvoke({"messages": [HumanMessage(content=question)]})
    messages = list(result.get("messages") or [])
    tool_results = [
        {"name": getattr(m, "name", ""), "args": {}, "result": str(m.content)}
        for m in messages
        if isinstance(m, ToolMessage)
    ]
    usage = _usage_from_messages(messages)
    return {
        "messages": messages,
        "tool_results": tool_results,
        "total_steps": _count_model_steps(messages),
        **usage,
        "answer": _last_ai_text(messages),
    }


__all__ = [
    "AgentState",
    "DocIntelState",
    "MAX_ITERATIONS",
    "SYSTEM_PROMPT",
    "TOOLS",
    "build_custom_graph",
    "build_docintel_graph",
    "build_model",
    "build_prebuilt_graph",
    "build_search_agent",
    "custom_graph",
    "detect_intent",
    "detect_intent_heuristic",
    "docintel_graph",
    "prebuilt_graph",
    "react_custom_graph",
    "prebuilt_react_graph",
    "route_after_model",
    "run_custom_graph",
    "run_docintel_pipeline",
    "run_naive_b62",
    "run_prebuilt_graph",
    "search_agent",
    "search_agent_node",
    "search_kb",
    "set_rag_service",
    "get_rag_service",
    "format_sources_section",
    "append_sources_section",
    "retrieve_rag_node",
    "answer_agent_node",
    "classify_agent_node",
    "classify_request",
    "detect_use_history_heuristic",
    "validate_agent_node",
    "write_agent_node",
    "write_feature_doc",
]
