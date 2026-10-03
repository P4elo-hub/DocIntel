"""DocIntel на LangGraph: classify_agent + три рабочих сценария.

Архитектура (диплом / Telegram):

    START → classify_agent
              ├─ search  → search_agent → END
              ├─ write   → search_agent → write_agent → validate_agent → END
              └─ answer  → search_agent → answer_agent → validate_agent → END

Три сценария:
1. **search** — только поиск по KB (факты/чанки).
2. **write** — документация фичи: поиск → kit-написнание → валидация.
3. **answer** — ответ на вопрос (пример/контракт/пояснение): поиск → формулировка → валидация.

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


search_agent = build_search_agent()


# ---------------------------------------------------------------------------
# Родительский граф: search_agent → write_agent
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
    draft_answer: str
    final_answer: str
    # для отчёта / трейсинга
    agents_called: Annotated[list[str], operator.add]


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
    r"требования|сценари\w*|импорт|confluence"
    r")",
    re.IGNORECASE,
)

# Ответ по KB (пример/контракт/пояснение) → сценарий answer, не write.
_ANSWER_HINTS = re.compile(
    r"("
    r"(приведи|покажи|дай|какой|каков\w*|как выглядит|есть ли|объясни|расскажи)\w*"
    r".{0,40}(пример|request|response|запрос|ответ|контракт|параметр|"
    r"поле|schema|payload|обмен|endpoint|api|интеграц)|"
    r"пример\s+(запроса|ответа|request|response)|"
    r"пример\s+ответа\s+для|"
    r"какие\s+(поля|параметры|коды)|"
    r"как\s+работает\s+.{0,40}(обмен|api|endpoint|интеграц|импорт|ручку)|"
    r"что\s+такое\s+.{0,40}(обмен|api|endpoint|интеграц|фич|контракт)"
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
    "Ты classify_agent DocIntel — агент анализа запроса пользователя.\n"
    "Верни РОВНО две метки через пробел: <intent> <history_mode>\n"
    "\n"
    "intent (один из):\n"
    "search — найти фрагменты в KB без развёрнутого ответа.\n"
    "write — сгенерировать документацию фичи (бриф → разделы), "
    "ИЛИ повторить/переделать такую генерацию («ещё раз», «выполни задачу», "
    "«переделай документ»), если в диалоге была задача на документацию.\n"
    "answer — ответить по существующей документации "
    "(пример request/response, контракт, пояснение по обмену/API).\n"
    "chat — короткое приветствие / благодарность без рабочей задачи.\n"
    "reject — запрос НЕ про документацию продукта DocIntel. "
    "Если сомневаешься — reject.\n"
    "\n"
    "history_mode (один из):\n"
    "history — текущая реплика ПРОДОЛЖАЕТ или УТОЧНЯЕТ предыдущий диалог "
    "(ссылки на прошлое, «ещё раз», «эту задачу», «в тот формат»). "
    "Тогда downstream получит историю чата.\n"
    "fresh — НОВАЯ самостоятельная тема. Историю НЕ использовать.\n"
    "\n"
    "Правила:\n"
    "- Если блока «Контекст диалога» нет — history_mode=fresh.\n"
    "- «Выполни задачу ещё раз» при брифе на документацию в истории → write history.\n"
    "- chat и reject → fresh.\n"
    "\n"
    "Пример ответа: write history\n"
    "Пример ответа: answer fresh\n"
    "Без пояснений и пунктуации."
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
            r"use\s*case|get_linked|send_operations|добав(ить|ление).{0,40}параметр)",
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
    from app.chat.rag_query import _DIALOG_REFERENCE_RE, needs_context_expansion

    text = (user_request or "").strip()
    history = (chat_history or "").strip()
    if not text or not history:
        return False
    if _CHITCHAT.search(text):
        return False
    # Явная ссылка на прошлые реплики — история нужна.
    if _DIALOG_REFERENCE_RE.search(text):
        return True
    # Самодостаточный бриф / длинный вопрос с доменом — новая тема.
    if _WRITE_HINTS.search(text) and len(text) > 120:
        return False
    if len(text) >= 100 and _DOC_DOMAIN_HINTS.search(text):
        return False
    return needs_context_expansion(text)


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
    """Свернуть follow-up в самостоятельный запрос (когда use_history=True)."""
    from app.chat.rag_query import CONDENSE_SYSTEM_PROMPT, needs_context_expansion

    text = (current or "").strip()
    history = (chat_history or "").strip()
    if not text or not history or not needs_context_expansion(text):
        return text
    try:
        model = build_model(temperature=0.0).bind(max_tokens=120)
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
    """classify_agent: (intent, use_history)."""
    text = user_request.strip()
    history = (chat_history or "").strip()
    if not text:
        return "chat", False

    # Документный «приведи пример…» без write — answer; history только если follow-up.
    if (
        _ANSWER_HINTS.search(text)
        and not _WRITE_HINTS.search(text)
        and _DOC_DOMAIN_HINTS.search(text)
        and not history
    ):
        log.info("intent_override label=answer fresh query=%r", text[:120])
        return "answer", False

    classify_input = f"Текущая реплика пользователя:\n{text[:1500]}"
    if history:
        classify_input = (
            f"Контекст диалога (есть предыдущие сообщения; реши, нужны ли они):\n"
            f"{history[:2500]}\n\n"
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
            from app.chat.rag_query import _DIALOG_REFERENCE_RE

            heur_hist = detect_use_history_heuristic(text, chat_history=history)
            if use_hist is None:
                use_hist = heur_hist
            if not history:
                use_hist = False
            # Явная отсылка к диалогу важнее «самодостаточной длины».
            if history and _DIALOG_REFERENCE_RE.search(text):
                use_hist = True
            # Модель часто ставит history «на всякий случай»; самодостаточный
            # вопрос (heuristic=False) не должен тащить чужую тему из чата.
            elif use_hist and not heur_hist:
                log.info(
                    "classify_agent history→fresh (self-contained) query=%r",
                    text[:120],
                )
                use_hist = False
            # Follow-up по документации не должен улетать в reject.
            if (
                label == "reject"
                and history
                and _DOC_DOMAIN_HINTS.search(history)
                and (use_hist or _DIALOG_REFERENCE_RE.search(text) or _DOC_DOMAIN_HINTS.search(text))
            ):
                log.info(
                    "classify_agent reject→answer (doc follow-up) query=%r",
                    text[:120],
                )
                label = "answer"
                use_hist = True
            log.info(
                "classify_agent label=%s use_history=%s query=%r",
                label,
                use_hist,
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
    history = (state.get("chat_history") or "").strip()
    if not history:
        return ""
    return (
        "\n\nКонтекст диалога (если там уже были полные JSON/таблицы обменов — "
        "это источник истины для контрактов, не сокращай):\n"
        f"{history[:24_000]}\n"
    )


def _merge_chat_contracts_into_kb(search_context: str, chat_history: str) -> str:
    """Подмешивает контракты из прошлых ответов чата в KB для write/answer."""
    kb = (search_context or "").strip()
    history = (chat_history or "").strip()
    if not history:
        return kb
    block = (
        "### Контракты / примеры из предыдущих ответов в этом чате\n"
        "Если ниже есть полные request/response — копируй поля отсюда целиком "
        "(в т.ч. SEND_OPERATIONS, GET_OPERATIONS_WITH_DETAILS, GetLinkedEvents). "
        "Не заменяй их коротким stub вроде `{operations:[...]}`.\n\n"
        f"{history[:20_000]}"
    )
    if not kb:
        return block
    return f"{block}\n\n---\n\n### Результат search_kb\n{kb}"


async def classify_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Анализ запроса: intent + нужно ли пробрасывать историю чата дальше."""
    original = (
        (state.get("original_user_message") or state.get("user_request") or "")
    ).strip()
    available_history = (state.get("chat_history") or "").strip()

    intent, use_history = await classify_request(
        original,
        chat_history=available_history,
    )
    if not available_history:
        use_history = False

    # «Выполни задачу ещё раз» при write-брифе в истории — это write, не answer.
    if (
        available_history
        and _REDO_TASK_RE.search(original)
        and _history_looks_like_write(available_history)
    ):
        if intent != "write":
            log.info(
                "classify_agent redo→write (was %s) query=%r",
                intent,
                original[:120],
            )
        intent = "write"
        use_history = True

    out: dict[str, Any] = {
        "intent": intent,
        "use_history": use_history,
        "agents_called": ["classify_agent"],
    }

    if use_history:
        condensed = await _condense_with_history(original, available_history)
        out["user_request"] = condensed
        out["chat_history"] = available_history
        # Intent ставили по короткой реплике; после condense мог вскрыться write-бриф.
        if intent == "answer" and _looks_like_write_brief(condensed):
            intent = "write"
            out["intent"] = "write"
            log.info(
                "classify_agent condensed→write query=%r",
                condensed[:120],
            )
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


async def search_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Узел графа = вызов отдельного search_agent → search_context."""
    request = state["user_request"]
    intent = state.get("intent")
    history = _history_block(state)
    if intent == "write":
        prompt = (
            "Собери KB-контекст для последующего независимого write-агента.\n"
            "Вызови search_kb ОТДЕЛЬНО по каждому обмену/API из брифа и "
            "из контекста диалога (например GetLinkedEvents, "
            "GET_OPERATIONS_WITH_DETAILS, SEND_OPERATIONS) + "
            "«запрос/ответ», «параметры», «пример».\n"
            "Нужны ПОЛНЫЕ таблицы полей и JSON-примеры — не краткое резюме.\n"
            "Если в диалоге уже есть полный контракт — всё равно подтверди "
            "поиском по KB, но не теряй поля из диалога.\n"
            f"{history}\n"
            f"Бриф:\n{request}"
        )
    elif intent == "answer":
        prompt = (
            "Собери KB-контекст для answer-агента.\n"
            "Вызови search_kb по имени обмена/API из вопроса и по "
            "«пример запроса/ответа», «параметры». "
            "Если в диалоге уже есть пример операции — ищи целевой формат "
            "(например SEND OPERATIONS) и правила трансформации.\n"
            "Нужны полные JSON/таблицы из документов — не краткое резюме.\n"
            f"{history}\n"
            f"Вопрос:\n{request}"
        )
    else:
        prompt = (
            "Собери контекст по запросу пользователя. "
            f"{history}\n"
            f"Запрос:\n{request}"
        )
    result = await search_agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    messages = list(result.get("messages") or [])
    tool_ctx = _tool_texts(messages)
    summary = _last_ai_text(messages)
    # write/answer получают сырой tool output + контракты из чата.
    if intent in {"write", "answer"}:
        search_context = tool_ctx or summary
        search_context = _merge_chat_contracts_into_kb(
            search_context, state.get("chat_history") or ""
        )
    else:
        search_context = tool_ctx if tool_ctx else summary
    out: dict[str, Any] = {
        "search_context": search_context,
        "agents_called": ["search_agent"],
    }
    if intent == "search":
        out["final_answer"] = summary or search_context
    return out


async def write_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Сценарий write: kit-subagents → draft документа фичи."""
    from app.services.docintel.orchestrator import SectionOrchestrator
    from app.tools.feature_sections import build_execution_plan

    brief = state["user_request"]
    history = (state.get("chat_history") or "").strip()
    if history:
        brief = (
            f"{brief}\n\n"
            "Контекст диалога (если перечислены несколько обменов — "
            "в integration опиши КАЖДЫЙ отдельным подразделом 4.1.x с полным "
            "request/response из KB/диалога):\n"
            f"{history[:16_000]}"
        )
    kb = state.get("search_context") or ""
    kb = _merge_chat_contracts_into_kb(kb, history)
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
    draft = await write_answer_from_kb(
        _section_writer_client(),
        user_request=user_request,
        search_context=state.get("search_context") or "",
        chat_history=state.get("chat_history") or "",
    )
    return {
        "draft_answer": draft,
        "final_answer": draft,
        "agents_called": ["answer_agent"],
    }


async def validate_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Независимый review: сам ищет контракты в RAG и правит draft."""
    from app.services.docintel.validator import validate_against_kb

    draft = (state.get("draft_answer") or state.get("final_answer") or "").strip()
    # search_context от write — только fallback, если fresh RAG пуст.
    kb = state.get("search_context") or ""
    brief = state.get("user_request") or ""
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
    return {
        "final_answer": fixed,
        "agents_called": ["validate_agent"],
    }


def route_after_classify(state: DocIntelState) -> Literal["search_agent", "__end__"]:
    """chat/reject → END; search/write/answer → search_agent."""
    if state.get("intent") in {"chat", "reject"}:
        return "__end__"
    return "search_agent"


def route_after_search(
    state: DocIntelState,
) -> Literal["write_agent", "answer_agent", "__end__"]:
    """После поиска: ветвление по сценарию."""
    intent = state.get("intent")
    if intent == "write":
        return "write_agent"
    if intent == "answer":
        return "answer_agent"
    return "__end__"


def build_docintel_graph():
    """classify → (search | search→write→validate | search→answer→validate)."""
    builder = StateGraph(DocIntelState)
    builder.add_node("classify_agent", classify_agent_node)
    builder.add_node("search_agent", search_agent_node)
    builder.add_node("write_agent", write_agent_node)
    builder.add_node("answer_agent", answer_agent_node)
    builder.add_node("validate_agent", validate_agent_node)

    builder.add_edge(START, "classify_agent")
    builder.add_conditional_edges(
        "classify_agent",
        route_after_classify,
        {"search_agent": "search_agent", "__end__": END},
    )
    builder.add_conditional_edges(
        "search_agent",
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
) -> dict[str, Any]:
    """Точка входа: classify (intent + use_history) → сценарий.

    ``chat_history`` — кандидат истории из БД чата; classify_agent решает,
    пробросить её дальше (history) или обнулить (fresh).
    """
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
            "draft_answer": "",
            "final_answer": "",
            "agents_called": [],
        },
        config=config,
    )
    return {
        "intent": result.get("intent"),
        "use_history": bool(result.get("use_history")),
        "user_request": result.get("user_request") or user_request,
        "search_context": result.get("search_context") or "",
        "draft_answer": result.get("draft_answer") or "",
        "final_answer": result.get("final_answer") or "",
        "agents_called": list(result.get("agents_called") or []),
        "answer": result.get("final_answer") or "",
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
    "search_kb",
    "answer_agent_node",
    "classify_agent_node",
    "classify_request",
    "detect_use_history_heuristic",
    "validate_agent_node",
    "write_agent_node",
    "write_feature_doc",
]
