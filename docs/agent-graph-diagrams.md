# Схемы агентов DocIntel

## Главная: два агента в Telegram/web

Путь: Telegram → backend `/chats` → `ChatService` → `docintel_graph`.

```mermaid
flowchart TD
    START([START]) --> intent_router[intent_router]
    intent_router -->|привет| FINISH([END])
    intent_router -->|вопрос или напиши фичу| search_agent[search_agent<br/>tool: search_kb]
    search_agent -->|просто вопрос| FINISH
    search_agent -->|сделай документацию| write_agent[write_agent<br/>tool: write_feature_doc]
    write_agent --> FINISH
```

![docintel graph](agent-graph.png)

| Сообщение в Telegram | Что вызывается |
|----------------------|----------------|
| «Как работает импорт из Confluence?» | `search_agent` |
| «Сделай документацию для новой ручки webhook» | `search_agent` → `write_agent` |
| «Привет» | короткий ответ без агентов |

## ReAct (ДЗ Б6.3)

```mermaid
flowchart TD
    START([START]) --> call_model[call_model]
    call_model -->|tool_calls| execute_tool[execute_tool]
    call_model -->|done or max_iter| force_finish[force_finish]
    execute_tool --> call_model
    force_finish --> FINISH([END])
```

## Prebuilt create_agent

```mermaid
flowchart TD
    START([START]) --> model[model]
    model -->|tool_calls| tools[tools]
    model -->|final answer| FINISH([END])
    tools --> model
```
