"""Экспорт схем агентов DocIntel (два агента + ReAct для Б6.3).

Запуск:
    uv run python scripts/visualize_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.agent_graph import (  # noqa: E402
    custom_graph,
    docintel_graph,
    prebuilt_graph,
)

DOCS = ROOT / "docs"

DOCINTEL_MERMAID = """\
flowchart TD
    START([START]) --> intent_router[intent_router]
    intent_router -->|привет| FINISH([END])
    intent_router -->|вопрос или напиши фичу| search_agent[search_agent<br/>tool: search_kb]
    search_agent -->|просто вопрос| FINISH
    search_agent -->|сделай документацию| write_agent[write_agent<br/>tool: write_feature_doc]
    write_agent --> FINISH
"""

CUSTOM_REACT_MERMAID = """\
flowchart TD
    START([START]) --> call_model[call_model]
    call_model -->|tool_calls| execute_tool[execute_tool]
    call_model -->|done or max_iter| force_finish[force_finish]
    execute_tool --> call_model
    force_finish --> FINISH([END])
"""

PREBUILT_MERMAID = """\
flowchart TD
    START([START]) --> model[model]
    model -->|tool_calls| tools[tools]
    model -->|final answer| FINISH([END])
    tools --> model
"""


def _save(path: Path, text: str) -> None:
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    print(f"saved {path.relative_to(ROOT)}")


def _try_png(path: Path) -> None:
    try:
        png_bytes = docintel_graph.get_graph().draw_mermaid_png(
            max_retries=5, retry_delay=2.0
        )
    except Exception as exc:  # noqa: BLE001
        print(f"png skipped: {exc}")
        return
    path.write_bytes(png_bytes)
    print(f"saved {path.relative_to(ROOT)} ({len(png_bytes)} bytes)")


def main() -> int:
    assert docintel_graph is not None
    assert custom_graph is not None
    assert prebuilt_graph is not None

    DOCS.mkdir(parents=True, exist_ok=True)
    _save(DOCS / "agent-graph-custom.mmd", DOCINTEL_MERMAID)
    _save(DOCS / "agent-graph-prebuilt.mmd", PREBUILT_MERMAID)
    _save(DOCS / "agent-graph-react.mmd", CUSTOM_REACT_MERMAID)

    preview = f"""# Схемы агентов DocIntel

## Главная: два агента в Telegram/web

Путь: Telegram → backend `/chats` → `ChatService` → `docintel_graph`.

```mermaid
{DOCINTEL_MERMAID.strip()}
```

![docintel graph](agent-graph.png)

| Сообщение в Telegram | Что вызывается |
|----------------------|----------------|
| «Как работает импорт из Confluence?» | `search_agent` |
| «Сделай документацию для новой ручки webhook» | `search_agent` → `write_agent` |
| «Привет» | короткий ответ без агентов |

## ReAct (ДЗ Б6.3)

```mermaid
{CUSTOM_REACT_MERMAID.strip()}
```

## Prebuilt create_agent

```mermaid
{PREBUILT_MERMAID.strip()}
```
"""
    _save(DOCS / "agent-graph-diagrams.md", preview)
    _try_png(DOCS / "agent-graph.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
