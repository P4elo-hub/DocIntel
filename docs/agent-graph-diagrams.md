# Схемы агентов DocIntel

## Главная: classify_agent + три сценария

Путь: Telegram → backend `/chats` → `ChatService` → `docintel_graph`.

```mermaid
flowchart TD
    START([START]) --> classify_agent[classify_agent]
    classify_agent -->|привет| FINISH([END])
    classify_agent -->|search / write / answer| search_agent[search_agent<br/>tool: search_kb]
    search_agent -->|search| FINISH
    search_agent -->|write| write_agent[write_agent<br/>kit-subagents]
    search_agent -->|answer| answer_agent[answer_agent<br/>ответ по KB]
    write_agent --> validate_agent[validate_agent]
    answer_agent --> validate_agent
    validate_agent --> FINISH
```

![docintel graph](agent-graph.png)

| Сообщение в Telegram | Сценарий | Что вызывается |
|----------------------|----------|----------------|
| «Найди документ GetLinkedEvents» | search | `search_agent` |
| «Приведи пример ответа для SEND OPERATIONS» | answer | `search_agent` → `answer_agent` → `validate_agent` |
| «Сделай документацию: yield в GetLinkedEvents» | write | `search_agent` → `write_agent` → `validate_agent` |
| «Привет» | chat | короткий ответ без рабочих агентов |

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
