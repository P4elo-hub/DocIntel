## Что внутри

```
app/
├── main.py              # FastAPI app + lifespan + middleware + exception handlers
├── core/
│   ├── config.py        # Settings: LLMSettings + DocIntelSettings (nested __)
│   └── exceptions.py    # LLMError + 4 подкласса
├── deps/
│   └── providers.py     # get_llm, get_cache, get_llm_service, get_docintel_service
├── tools/               # kit-tools, search_kb, write_feature_doc
├── prompts/             # Jinja2 system prompts + tool descriptions
├── data/                # демо-документы для search_kb
├── routers/
│   ├── chat.py          # /chat, /chat/stream (SSE), /chat/batch
│   ├── features.py      # DocIntel: /features/generate, /features/chat, …
│   ├── models.py        # /models — каталог с ценами
│   └── health.py        # /health, /ready
├── services/
│   ├── llm.py           # LLMService: generic /chat (кеш, retry)
│   └── docintel/        # DocIntel: ToolCallClient, orchestrator, HTTP service
│       ├── client.py
│       ├── orchestrator.py
│       ├── providers.py
│       ├── service.py   # DocIntelService для routers/features
│       └── text_tool_calls.py
└── schemas/
    ├── chat.py          # Message, ChatRequest, ChatResponse, Usage, ChatDelta
    ├── features.py      # FeatureGenerateRequest/Response
    └── models.py        # ModelInfo
feature-methodology-project/   # shablon.md + standard kits (DocIntel)
tests/                           # unit + integration + cassets (см. tests/README.md)
```

## Примеры (examples/)

Запуск из корня проекта (`cd m3_b4`):

```bash
# --- CLI: напрямую через ToolCallClient (нужен ключ в .env) ---
python examples/run_tool_call.py --backend deepseek   # sectioned (DeepSeek, рекомендуется)
python examples/run_tool_call.py                      # sectioned (OpenAI primary)
python examples/run_tool_call_agent.py --backend deepseek
python examples/run_tool_call_deepseek.py             # то же, что --backend deepseek
python examples/run_tool_call_fallback.py             # sectioned через Ollama

# --- HTTP: через FastAPI (сначала uvicorn app.main:app --port 8000) ---
python examples/run_api_health.py
python examples/run_api_chat.py
python examples/run_api_features_chat.py
python examples/run_api_features_generate.py  # 3–8 минут
python examples/run_api_stream.py
```

Ответы сохраняются в `examples/answers/`.

## Запуск

Нужен `uv` (`brew install uv` или `pip install uv`) и Python 3.12 (uv подтянет сам).

```bash
uv sync
cp .env.example .env       # подставить LLM__OPENAI_API_KEY для боевых вызовов

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI — http://localhost:8000/docs
- ReDoc      — http://localhost:8000/redoc
- OpenAPI    — http://localhost:8000/openapi.json

Redis опционален: если на `REDIS_URL` никто не отвечает, lifespan ловит ошибку
и поднимается без кеша. `/ready` в этом случае отдаёт `{"status":"degraded"}`.

## Тесты

```bash
uv run pytest -v
```

Все тесты используют моки, сеть не нужна. Ожидаемый вывод: **45 passed**.

## Примеры HTTP-вызовов

### Синхронный чат (generic LLM)

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "Ты лаконичный ассистент."},
      {"role": "user",   "content": "Скажи привет одним словом."}
    ],
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "max_tokens": 50
  }'
```

### DocIntel: sectioned-генерация документации фичи

```bash
curl -s -X POST http://localhost:8000/features/generate \
  -H "Content-Type: application/json" \
  -d '{
    "feature_brief": "Перевести уведомления о переводах на Kafka...",
    "feature_name": "Асинхронные уведомления по переводам",
    "protocol": "Async"
  }'
```

### DocIntel: chat с tool calling

```bash
curl -s -X POST http://localhost:8000/features/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Найди документ про Confluence"}]}'
```

### DocIntel: SSE streaming

```bash
curl -N -X POST http://localhost:8000/features/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Что такое event loop?"}]}'
```

### Generic streaming / batch / health

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"считай до 5"}]}'

curl -s http://localhost:8000/models
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
```

## Конфиг

Переменные окружения (см. `.env.example`). Префиксы вложенных секций — через `__`:

| Переменная | Значение по умолчанию |
|------------|----------------------|
| `APP_NAME` | `llm-service` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `LLM__OPENAI_API_KEY` или `OPENAI_API_KEY` | — (обязательны для старта) |
| `LLM__DEFAULT_MODEL` | `gpt-4o-mini` |
| `DOCINTEL__SERVICE_NAME` | `DocIntel` |
| `DOCINTEL__REQUEST_TIMEOUT_SECONDS` | `180` |
| `DOCINTEL__MAX_TOOL_ROUNDS` | `8` |
| `DOCINTEL__FALLBACK_BACKEND` | `ollama` |
| `DOCINTEL__METHODOLOGY_DIR` | `feature-methodology-project` |

Полный список — в `.env.example`.
