"""DocIntel на LangGraph: два агента + оркестратор.

Архитектура (то, что нужно для диплома / Telegram):

    START → intent_router
              ├─ search  → search_agent → (если вопрос) END
              └─ write   → search_agent → write_agent → END

- ``search_agent`` — отдельный агент, tool только ``search_kb``
  (сбор контекста из документации).
- ``write_agent`` — отдельный агент, tool только ``write_feature_doc``
  (написание документации фичи по собранному контексту).
- Родительский ``docintel_graph`` вызывает их по рёбрам графа.

Для ДЗ Б6.3 ниже оставлены также ReAct-варианты (один агент с обоими tools):
``react_custom_graph`` / ``prebuilt_react_graph`` — для бенчмарка и отчёта.
"""

from __future__ import annotations

import operator
import re
from functools import lru_cache
from typing import Annotated, Any, Literal, TypedDict

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

MAX_ITERATIONS = 6

# ---------------------------------------------------------------------------
# Handlers / tools (боевые DocIntel)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _handlers() -> ToolHandlers:
    docintel = get_settings().docintel
    return ToolHandlers(
        knowledge_base_path=docintel.knowledge_base_path,
        docs_dir=docintel.docs_dir,
        methodology_dir=docintel.methodology_dir,
        shablon_path=docintel.shablon_path,
    )


@tool("search_kb")
def search_kb(query: str) -> str:
    """Поиск по существующей проектной документации DocIntel."""
    return _handlers().search_kb(query)


search_kb.description = load_tool_description("search_kb").replace(
    "{{ service_name }}", get_settings().docintel.service_name
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
    "Ты агент поиска DocIntel. Твоя единственная задача — собрать релевантный "
    "контекст из проектной документации через tool `search_kb`.\n"
    "Правила:\n"
    "- Всегда вызывай `search_kb` (можно 1–2 раза с разными query).\n"
    "- В финальном ответе верни сжатую выжимку найденного контекста на русском "
    "(факты, требования, API, ограничения). Без воды и без выдумок.\n"
    "- Не пиши документацию фичи и не вызывай другие tools — их у тебя нет."
)

WRITE_AGENT_PROMPT = (
    "Ты агент написания документации DocIntel. Tool — только `write_feature_doc`.\n"
    "Тебе передадут: (1) исходный запрос пользователя, (2) контекст от агента поиска.\n"
    "Правила:\n"
    "- Опирайся на контекст поиска, не противоречь ему.\n"
    "- Вызови `write_feature_doc` (для коротких задач бери section_id=1.1, "
    "если пользователь не просил полный документ).\n"
    "- В финальном ответе верни готовый Markdown пользователю на русском, "
    "без служебных строк «пакет методологии» / kit banners."
)


def build_search_agent():
    """Отдельный агент поиска (только search_kb)."""
    return create_agent(
        build_model(),
        tools=[search_kb],
        system_prompt=SEARCH_AGENT_PROMPT,
        name="search_agent",
    )


def build_write_agent():
    """Отдельный агент написания (только write_feature_doc)."""
    return create_agent(
        build_model(),
        tools=[write_feature_doc],
        system_prompt=WRITE_AGENT_PROMPT,
        name="write_agent",
    )


search_agent = build_search_agent()
write_agent = build_write_agent()


# ---------------------------------------------------------------------------
# Родительский граф: search_agent → write_agent
# ---------------------------------------------------------------------------


class DocIntelState(TypedDict):
    """State оркестратора. Только сериализуемые поля (задел под checkpointer)."""

    user_request: str
    intent: Literal["search", "write", "chat"]
    search_context: str
    final_answer: str
    # для отчёта / трейсинга
    agents_called: Annotated[list[str], operator.add]


_WRITE_HINTS = re.compile(
    r"("
    r"задокументир|"
    r"сделай\s+(мне\s+)?документац|"
    r"напиши\s+(мне\s+)?(документац|фич|раздел|ручку|endpoint|api|изменен)|"
    r"опиши\s+(фич|интеграц|ручку|endpoint)|"
    r"новая\s+(фича|ручка|интеграц)|"
    r"write_feature|"
    r"section_id|"
    r"документац\w*\s+(фич|для|по)|"
    r"сгенерируй\s+(документ|раздел|spec|документац)|"
    r"ручку\s+интеграц|"
    r"переимен|"
    r"измени\s+(название|параметр|поле|ручку)"
    r")",
    re.IGNORECASE,
)

_CHITCHAT = re.compile(
    r"^(привет|здравств|добрый\s+(день|вечер|утро)|как дела|спасибо|благодар|пока|hey|hello)\b",
    re.IGNORECASE,
)


def detect_intent(user_request: str) -> Literal["search", "write", "chat"]:
    """Эвристика intent для оркестратора / Telegram.

    - write — написать/задокументировать фичу → search_agent → write_agent
    - search — вопрос по документации → только search_agent
    - chat — светская беседа → без агентов (обычный LLM)
    """
    text = user_request.strip()
    if not text or _CHITCHAT.search(text):
        return "chat"
    if _WRITE_HINTS.search(text):
        return "write"
    return "search"


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


async def intent_node(state: DocIntelState) -> dict[str, Any]:
    intent = detect_intent(state["user_request"])
    out: dict[str, Any] = {"intent": intent, "agents_called": ["intent_router"]}
    if intent == "chat":
        out["final_answer"] = (
            "Привет! Я DocIntel. Спроси про документацию "
            "(например, «как работает импорт из Confluence») "
            "или попроси задокументировать фичу "
            "(«сделай документацию для новой ручки webhook»)."
        )
    return out


async def search_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Узел графа = вызов отдельного search_agent."""
    request = state["user_request"]
    prompt = (
        "Собери контекст по запросу пользователя. "
        f"Запрос:\n{request}"
    )
    result = await search_agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    messages = list(result.get("messages") or [])
    tool_ctx = _tool_texts(messages)
    summary = _last_ai_text(messages)
    search_context = tool_ctx if tool_ctx else summary
    # Если intent=search — итоговый ответ = выжимка поиска.
    out: dict[str, Any] = {
        "search_context": search_context,
        "agents_called": ["search_agent"],
    }
    if state.get("intent") == "search":
        out["final_answer"] = summary or search_context
    return out


async def write_agent_node(state: DocIntelState) -> dict[str, Any]:
    """Узел графа = вызов отдельного write_agent (после поиска)."""
    prompt = (
        "Исходный запрос пользователя:\n"
        f"{state['user_request']}\n\n"
        "Контекст, собранный агентом поиска:\n"
        f"{state.get('search_context') or '(пусто)'}\n\n"
        "Напиши документацию фичи. Если section_id не указан пользователем — используй 1.1."
    )
    result = await write_agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    messages = list(result.get("messages") or [])
    answer = _last_ai_text(messages)
    return {
        "final_answer": answer,
        "agents_called": ["write_agent"],
    }


def route_after_intent(state: DocIntelState) -> Literal["search_agent", "__end__"]:
    """Светская беседа → END; иначе сначала search_agent."""
    if state.get("intent") == "chat":
        return "__end__"
    return "search_agent"


def route_after_search(state: DocIntelState) -> Literal["write_agent", "__end__"]:
    """После поиска: write-задача → write_agent, иначе END."""
    if state.get("intent") == "write":
        return "write_agent"
    return "__end__"


def build_docintel_graph():
    """Оркестратор: intent → search_agent → (write_agent?) → END."""
    builder = StateGraph(DocIntelState)
    builder.add_node("intent_router", intent_node)
    builder.add_node("search_agent", search_agent_node)
    builder.add_node("write_agent", write_agent_node)

    builder.add_edge(START, "intent_router")
    builder.add_conditional_edges(
        "intent_router",
        route_after_intent,
        {"search_agent": "search_agent", "__end__": END},
    )
    builder.add_conditional_edges(
        "search_agent",
        route_after_search,
        {"write_agent": "write_agent", "__end__": END},
    )
    builder.add_edge("write_agent", END)
    return builder.compile()


docintel_graph = build_docintel_graph()


async def run_docintel_pipeline(
    user_request: str,
    *,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Точка входа для API / Telegram: два агента на графе.

    Returns:
        intent, search_context, final_answer, agents_called
    """
    config: dict[str, Any] | None = None
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}

    result = await docintel_graph.ainvoke(
        {
            "user_request": user_request,
            "intent": "search",
            "search_context": "",
            "final_answer": "",
            "agents_called": [],
        },
        config=config,
    )
    return {
        "intent": result.get("intent"),
        "search_context": result.get("search_context") or "",
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
    "build_write_agent",
    "custom_graph",
    "detect_intent",
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
    "write_agent",
    "write_feature_doc",
]
