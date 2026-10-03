"""Бенчмарк Б6.2 naive loop vs custom StateGraph vs prebuilt create_agent.

5 задач × 3 реализации × 3 повтора → docs/agent-graph-report.md

Запуск:
    uv run python scripts/bench_agents.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.agent_graph import (  # noqa: E402
    MAX_ITERATIONS,
    SYSTEM_PROMPT,
    TOOLS,
    run_custom_graph,
    run_naive_b62,
    run_prebuilt_graph,
)

REPEATS = 3
REPORT_PATH = ROOT / "docs" / "agent-graph-report.md"
CUSTOM_MMD = ROOT / "docs" / "agent-graph-custom.mmd"  # теперь схема двух агентов

Runner = Callable[[str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class BenchTask:
    task_id: str
    title: str
    prompt: str
    kind: str  # simple | medium | provocative


TASKS: list[BenchTask] = [
    BenchTask(
        task_id="t1",
        title="Простая: один tool (search_kb)",
        kind="simple",
        prompt=(
            "Что такое импорт из Confluence в DocIntel? "
            "Ответь строго по документации через search_kb."
        ),
    ),
    BenchTask(
        task_id="t2",
        title="Простая: один tool (search_kb, API)",
        kind="simple",
        prompt=(
            "Какие обязательные поля у POST /v1/payments? "
            "Найди ответ через search_kb и перечисли поля."
        ),
    ),
    BenchTask(
        task_id="t3",
        title="Средняя: один tool (write_feature_doc)",
        kind="medium",
        prompt=(
            "Задокументируй фичу: уведомление мерчанта о смене статуса платежа по webhook. "
            "Обязательно вызови write_feature_doc с section_id=1.1, protocol=REST, "
            "feature_name=payment-status-webhook. Верни готовый фрагмент раздела 1.1."
        ),
    ),
    BenchTask(
        task_id="t4",
        title="Средняя: composability search_kb → write_feature_doc",
        kind="medium",
        prompt=(
            "Сначала через search_kb найди, что уже есть про СБП и МИР в платёжном шлюзе. "
            "Затем вызови write_feature_doc для фичи «повторная оплата через СБП при failed», "
            "section_id=1.1, protocol=REST, feature_name=sbp-retry-payment. "
            "В ответе кратко сошлись на найденный контекст и покажи раздел 1.1."
        ),
    ),
    BenchTask(
        task_id="t5",
        title="Провокационная: tools НЕ вызывать",
        kind="provocative",
        prompt=(
            "Привет! Как тебя зовут и чем ты можешь помочь в двух предложениях? "
            "Не вызывай никакие инструменты — это светская беседа."
        ),
    ),
]


@dataclass
class RunMetrics:
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_steps: int
    answer: str = ""
    error: str = ""


@dataclass
class CellAgg:
    samples: list[RunMetrics] = field(default_factory=list)

    @property
    def ok_samples(self) -> list[RunMetrics]:
        return [s for s in self.samples if not s.error]

    def mean_latency(self) -> float:
        vals = [s.latency_ms for s in self.ok_samples]
        return statistics.mean(vals) if vals else float("nan")

    def mean_prompt(self) -> float:
        vals = [s.prompt_tokens for s in self.ok_samples]
        return statistics.mean(vals) if vals else float("nan")

    def mean_completion(self) -> float:
        vals = [s.completion_tokens for s in self.ok_samples]
        return statistics.mean(vals) if vals else float("nan")

    def mean_steps(self) -> float:
        vals = [s.total_steps for s in self.ok_samples]
        return statistics.mean(vals) if vals else float("nan")


async def _timed(runner: Runner, prompt: str, **kwargs: Any) -> RunMetrics:
    started = time.perf_counter()
    try:
        if kwargs:
            result = await runner(prompt, **kwargs)  # type: ignore[call-arg]
        else:
            result = await runner(prompt)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RunMetrics(
            latency_ms=elapsed_ms,
            prompt_tokens=int(result.get("prompt_tokens") or 0),
            completion_tokens=int(result.get("completion_tokens") or 0),
            total_steps=int(result.get("total_steps") or 0),
            answer=str(result.get("answer") or "")[:300],
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        return RunMetrics(
            latency_ms=elapsed_ms,
            prompt_tokens=0,
            completion_tokens=0,
            total_steps=0,
            error=str(exc),
        )


async def _run_custom(prompt: str, *, task_id: str) -> dict[str, Any]:
    # Бонус Б6.3: thread_id в config — без checkpointer это no-op, но интерфейс готов.
    return await run_custom_graph(prompt, thread_id=f"bench-{task_id}")


async def run_benchmark() -> dict[str, dict[str, CellAgg]]:
    """Возвращает table[task_id][impl_name] -> CellAgg."""
    impls: dict[str, Any] = {
        "b62_naive": run_naive_b62,
        "custom_graph": None,  # обёртка с thread_id
        "prebuilt_graph": run_prebuilt_graph,
    }

    table: dict[str, dict[str, CellAgg]] = {
        t.task_id: {name: CellAgg() for name in impls} for t in TASKS
    }

    for task in TASKS:
        print(f"\n=== {task.task_id}: {task.title} ===")
        for impl_name in impls:
            for repeat in range(1, REPEATS + 1):
                if impl_name == "custom_graph":
                    metrics = await _timed(
                        _run_custom, task.prompt, task_id=task.task_id
                    )
                elif impl_name == "b62_naive":
                    metrics = await _timed(run_naive_b62, task.prompt)
                else:
                    metrics = await _timed(run_prebuilt_graph, task.prompt)

                table[task.task_id][impl_name].samples.append(metrics)
                status = "ERR" if metrics.error else "ok"
                print(
                    f"  {impl_name:16} r{repeat}: {status} "
                    f"{metrics.latency_ms:8.0f} ms | "
                    f"tok {metrics.prompt_tokens}+{metrics.completion_tokens} | "
                    f"steps {metrics.total_steps}"
                    + (f" | {metrics.error}" if metrics.error else "")
                )
    return table


def _fmt(n: float, digits: int = 0) -> str:
    if n != n:  # NaN
        return "—"
    if digits == 0:
        return str(int(round(n)))
    return f"{n:.{digits}f}"


def _load_custom_mermaid() -> str:
    if CUSTOM_MMD.is_file():
        return CUSTOM_MMD.read_text(encoding="utf-8").strip()
    return (
        "flowchart TD\n"
        "    START([START]) --> call_model[call_model]\n"
        "    call_model -->|tool_calls| execute_tool[execute_tool]\n"
        "    call_model -->|done or max_iter| force_finish[force_finish]\n"
        "    execute_tool --> call_model\n"
        "    force_finish --> FINISH([END])"
    )


def render_report(table: dict[str, dict[str, CellAgg]]) -> str:
    settings = get_settings()
    model = settings.llm.default_model
    tool_names = ", ".join(t.name for t in TOOLS)
    mermaid = _load_custom_mermaid()

    lines: list[str] = []
    lines.append("# Б6.3 — LangGraph: отчёт")
    lines.append("")
    lines.append("## 1. Конфигурация")
    lines.append("")
    lines.append("| Параметр | Значение |")
    lines.append("|----------|----------|")
    lines.append(f"| Модель | `{model}` |")
    lines.append("| Temperature | `0.0` |")
    lines.append(f"| max_iterations (custom / naive) | `{MAX_ITERATIONS}` |")
    lines.append(f"| Tools | `{tool_names}` |")
    lines.append(f"| Повторов на ячейку | `{REPEATS}` |")
    prompt_preview = " ".join(SYSTEM_PROMPT.split())[:120]
    lines.append(f"| System prompt | {prompt_preview}… |")
    lines.append("")
    lines.append("## 2. State contract")
    lines.append("")
    lines.append("| Поле | Тип / reducer | Зачем |")
    lines.append("|------|---------------|-------|")
    lines.append(
        "| `messages` | `Annotated[list[AnyMessage], add_messages]` | "
        "История диалога; reducer мержит по id, не затирает прошлые сообщения |"
    )
    lines.append(
        "| `iteration_count` | `int` (replace) | Счётчик вызовов модели для stop-крана |"
    )
    lines.append(
        "| `tool_results` | `Annotated[list[dict], operator.add]` | "
        "Накопление результатов tools для отчёта и трейсинга |"
    )
    lines.append("")
    lines.append(
        "В state **нет** SDK-клиентов, http-сессий и API-ключей — только сериализуемые "
        "данные. Модель создаётся внутри узла `call_model` / `force_finish` через "
        "`build_model()`."
    )
    lines.append("")
    lines.append("## 3. Router и stop conditions")
    lines.append("")
    lines.append("`route_after_model(state) -> Literal[\"execute_tool\", \"force_finish\"]`:")
    lines.append("")
    lines.append("1. если `iteration_count >= 6` → `force_finish` (явный stop-кран);")
    lines.append("2. иначе если у последнего сообщения есть `tool_calls` → `execute_tool`;")
    lines.append("3. иначе → `force_finish` (финальный ответ уже получен).")
    lines.append("")
    lines.append(
        "Узел `force_finish` при срабатывании лимита дописывает финальный AI-ответ "
        "**без** `bind_tools`, чтобы граф не уходил «молча» в END и не зацикливался."
    )
    lines.append("")
    lines.append("## 4. Схема кастомного графа")
    lines.append("")
    lines.append("Картинка (открывается в любом preview):")
    lines.append("")
    lines.append("![custom StateGraph](agent-graph.png)")
    lines.append("")
    lines.append(
        "Тот же граф в Mermaid (если preview не рисует диаграммы — открой "
        "[docs/agent-graph-diagrams.md](agent-graph-diagrams.md) или вставь блок в https://mermaid.live):"
    )
    lines.append("")
    lines.append("```mermaid")
    lines.append(mermaid)
    lines.append("```")
    lines.append("")
    lines.append("## 5. Таблица бенчмарка")
    lines.append("")
    lines.append(
        "Усреднение по 3 прогонам. Latency — wall-clock (`time.perf_counter`), "
        "токены — сумма `usage_metadata` по AI-сообщениям."
    )
    lines.append("")
    lines.append(
        "| Задача | Реализация | latency_ms | prompt_tokens | "
        "completion_tokens | total_steps |"
    )
    lines.append(
        "|--------|------------|------------|---------------|"
        "--------------------|-------------|"
    )

    impl_labels = {
        "b62_naive": "Б6.2 naive loop",
        "custom_graph": "custom StateGraph",
        "prebuilt_graph": "prebuilt create_agent",
    }
    for task in TASKS:
        for impl_name, label in impl_labels.items():
            cell = table[task.task_id][impl_name]
            lines.append(
                f"| {task.task_id}: {task.title} | {label} | "
                f"{_fmt(cell.mean_latency())} | {_fmt(cell.mean_prompt())} | "
                f"{_fmt(cell.mean_completion())} | {_fmt(cell.mean_steps(), 1)} |"
            )

    lines.append("")
    lines.append("### Примеры ответов (последний успешный прогон)")
    lines.append("")
    for task in TASKS:
        lines.append(f"**{task.task_id}** — {task.title}")
        for impl_name, label in impl_labels.items():
            ok = table[task.task_id][impl_name].ok_samples
            snippet = (ok[-1].answer if ok else "—").replace("\n", " ")
            lines.append(f"- {label}: {snippet[:200]}")
        lines.append("")

    # Агрегаты для раздела 6
    def _avg_latency(impl: str) -> float:
        vals = [
            table[t.task_id][impl].mean_latency()
            for t in TASKS
            if table[t.task_id][impl].ok_samples
        ]
        return statistics.mean(vals) if vals else float("nan")

    def _avg_tokens(impl: str) -> float:
        vals = []
        for t in TASKS:
            cell = table[t.task_id][impl]
            if cell.ok_samples:
                vals.append(cell.mean_prompt() + cell.mean_completion())
        return statistics.mean(vals) if vals else float("nan")

    custom_lat = _avg_latency("custom_graph")
    prebuilt_lat = _avg_latency("prebuilt_graph")
    naive_lat = _avg_latency("b62_naive")
    custom_tok = _avg_tokens("custom_graph")
    prebuilt_tok = _avg_tokens("prebuilt_graph")
    naive_tok = _avg_tokens("b62_naive")

    lines.append("## 6. Сравнение custom vs prebuilt")
    lines.append("")
    lines.append("| | custom StateGraph | prebuilt `create_agent` | Б6.2 naive |")
    lines.append("|-|--------------------|-------------------------|------------|")
    lines.append(
        f"| Средний latency_ms | {_fmt(custom_lat)} | {_fmt(prebuilt_lat)} | {_fmt(naive_lat)} |"
    )
    lines.append(
        f"| Средний total tokens | {_fmt(custom_tok)} | {_fmt(prebuilt_tok)} | {_fmt(naive_tok)} |"
    )
    lines.append(
        "| Что писали руками | State, 3 узла, router, "
        "`force_finish`, reducers | model + tools + system_prompt | for-loop + tool dispatch |"
    )
    lines.append(
        "| Stop-кран | явный `iteration_count >= 6` | "
        "`recursion_limit` графа (по умолчанию) | `max_iterations` в цикле |"
    )
    lines.append(
        "| `tool_results` в state | да (`operator.add`) | нет (собираем из ToolMessage) | да (локальный list) |"
    )
    lines.append("")
    lines.append(
        "**Вывод:** prebuilt быстрее в разработке и достаточен, пока хватает стандартного "
        "ReAct-цикла. Custom StateGraph предпочтительнее, когда нужны свой stop-кран, "
        "поля state под отчётность (`tool_results`), и задел на checkpointing / HITL / "
        "встраивание графа как subgraph супервизора. По числам этого прогона "
        f"custom ≈ {_fmt(custom_lat)} ms / {_fmt(custom_tok)} tok, "
        f"prebuilt ≈ {_fmt(prebuilt_lat)} ms / {_fmt(prebuilt_tok)} tok, "
        f"naive ≈ {_fmt(naive_lat)} ms / {_fmt(naive_tok)} tok "
        "(разница в основном в оверхеде каркаса и числе шагов модели, не в «магии» оркестратора)."
    )
    lines.append("")
    lines.append("## 7. Баг, найденный при отладке")
    lines.append("")
    lines.append(
        "При первой сборке router уводил в `force_finish` при `iteration_count >= 6`, "
        "но узел `force_finish` просто возвращал `{}`. Если лимит срабатывал на AI-сообщении "
        "**с** `tool_calls` (модель продолжала звать tool), граф завершался «молча»: "
        "в истории оставался незакрытый tool_call без `ToolMessage`, а пользователь видел "
        "пустой/битый финальный ответ. Фикс: в `force_finish` при достижении лимита "
        "делаем дополнительный `ainvoke` **без** `bind_tools` и явно просим итоговый ответ."
    )
    lines.append("")
    lines.append("Дополнительно поймали классику reducers: без `add_messages` поле "
                "`messages` перезаписывалось последним return узла, и tool-результаты "
                "пропадали из контекста модели на следующем шаге.")
    lines.append("")
    lines.append("## 8. Что блокирует переход к персистентности / checkpointing")
    lines.append("")
    lines.append(
        "В `scripts/bench_agents.py` для custom-графа уже передаётся "
        '`config={"configurable": {"thread_id": f"bench-{task_id}"}}`. '
        "Без checkpointer это **no-op**: состояние между вызовами не сохраняется. "
        "Чтобы включить персистентность, нужно:"
    )
    lines.append("")
    lines.append("1. подключить `AsyncSqliteSaver` / `AsyncPostgresSaver` в `builder.compile(checkpointer=...)`;")
    lines.append("2. стабильно передавать один и тот же `thread_id` для диалога;")
    lines.append(
        "3. решить, какие поля state должны переживать рестарт (сейчас все три поля "
        "сериализуемы — это как раз задел);"
    )
    lines.append(
        "4. для human-in-the-loop добавить `interrupt` / `interrupt_before` на узел tools "
        "или отдельный review-узел — в текущем графе точек останова ещё нет."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Сгенерировано `scripts/bench_agents.py`. Задачи: "
        f"{', '.join(t.task_id for t in TASKS)}.*"
    )
    lines.append("")
    return "\n".join(lines)


async def main() -> int:
    print("Running benchmark: 5 tasks × 3 impls × 3 repeats")
    table = await run_benchmark()
    report = render_report(table)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
