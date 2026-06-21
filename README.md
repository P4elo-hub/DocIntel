# llm-service

FastAPI-сервис для курса «ИИ-разработчик»: generic LLM-чат (`/chat`), DocIntel с tool calling и sectioned-генерацией (`/features/*`), observability (structlog + Phoenix), защитный слой (Б3.8) и eval/garak для проверки качества и безопасности.

## Что делает система

| Слой | Назначение |
|------|------------|
| **Generic chat** | `POST /chat` — прямой вызов OpenAI, кеш Redis при `temperature=0`, retry, streaming/batch |
| **DocIntel** | `POST /features/chat` — tool calling (search_kb, write_feature_doc, kit-tools); `POST /features/generate` — sectioned-документация по shablon.md |
| **Security** | Валидация входа, canary, фильтр выхода, маскирование PII в логах, rate limit — на `/chat` и `/features/chat` |
| **Observability** | structlog (JSON), OpenTelemetry → Phoenix, `X-Request-ID`, `X-LLM-Cost-USD` |
| **Eval** | G-Eval + quality gates для `/features/chat` и `/features/generate` |
| **Garak** | Сканирование prompt-injection/jailbreak через REST-таргет (baseline / after) |

Swagger UI — http://localhost:8000/docs

## Структура репозитория

```
app/
├── main.py                    # lifespan, middleware, exception handlers
├── core/                      # Settings, доменные исключения
├── deps/providers.py          # DI: LLM, cache, DocIntel
├── routers/
│   ├── chat.py                # /chat, /chat/stream, /chat/batch
│   ├── features.py            # /features/generate, /features/chat, …
│   ├── models.py              # /models
│   └── health.py              # /health, /ready
├── services/
│   ├── llm.py                 # LLMService (generic chat)
│   ├── security/              # Б3.8: input_validator, output_filter, rate_limit, guards
│   └── docintel/              # ToolCallClient, orchestrator, DocIntelService
├── observability/             # structlog, PII-маскирование, tracing → Phoenix
├── tools/                     # kit-tools, search_kb, write_feature_doc
├── prompts/                   # Jinja2 system prompts
└── schemas/

eval/                          # G-Eval прогоны + garak REST-конфиги (см. eval/README.md)
docs/
├── security/                  # garak baseline/after отчёты, reports/
└── observability/

tests/                         # unit + integration + cassets (см. tests/README.md)
scripts/load_test.py           # синтетика rate limit (31-й запрос → 429)
feature-methodology-project/   # shablon.md + standard kits (DocIntel)
```

## Запуск локально

Нужен `uv` и Python ≥ 3.12.

```bash
uv sync
cp .env.example .env          # OPENAI_API_KEY / LLM__OPENAI_API_KEY — обязателен

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Redis опционален: без Redis сервис стартует без кеша, `/ready` → `{"status":"degraded","redis":"down"}`.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

| Сервис | Порт | Роль |
|--------|------|------|
| `app` | 8000 | FastAPI (образ `llm-service:v1`, multi-stage Dockerfile) |
| `redis` | — | Кеш чата + rate limit |
| `phoenix` | 6006 | UI трассировок OpenTelemetry |

Переменные в `compose.yaml` (можно переопределить в `.env`):

| Переменная | Default в compose | Назначение |
|------------|-------------------|------------|
| `SECURITY_ENABLED` | `true` | Защитный слой на `/chat` и `/features/chat` |
| `RATE_LIMIT_PER_MIN` | `30` | Лимит запросов/мин на IP или `X-User-ID` (0 = выкл.) |
| `REDIS_URL` | `redis://redis:6379/0` | Кеш и счётчики rate limit |

`compose.override.yaml` (dev): hot-reload, `LOG_LEVEL=DEBUG`, `RATE_LIMIT_PER_MIN=0`.

Garak и eval в образ **не входят** — это dev/host-инструменты; в контейнер копируется только `app/` и `feature-methodology-project/`.

## Защитный слой (Б3.8)

Включён на **`POST /chat`**, **`POST /features/chat`** и их stream-вариантах (не на `/features/generate`).

```
Запрос → rate_limit → validate_input → LLM (+ canary в system) → filter_output → ответ
              ↓              ↓                                        ↓
            429            400                                   502 / маскирование PII
         (нет content)  (нет content — garak считает атаку закрытой)
```

| Модуль | Что делает |
|--------|------------|
| `input_validator.py` | Длина ≤ 4000, injection-regex, encoding/base64-эвристика |
| `output_filter.py` | Блок утечки canary и system prompt, маскирование email/телефона/паспорта |
| `pii.py` | `redact_pii` на preview входов **и** исходящих ответов в structlog |
| `rate_limit.py` | Redis-счётчик, middleware на chat-эндпоинтах |

При старте генерируется `app.state.canary` (`CANARY_<hex>`) и добавляется в system prompt.

**Baseline garak** — отключить защиту без правки кода:

```bash
SECURITY_ENABLED=false uv run uvicorn app.main:app --port 8000
```

## Garak (NVIDIA)

Установка (на хосте, не в Docker-образе):

```bash
pip install garak
garak --version
garak --list_probes
```

REST-конфиги под форму API:

| Файл | Endpoint |
|------|----------|
| `eval/security/rest_config.json` | `POST /chat` |
| `eval/security/rest_config_features.json` | `POST /features/chat` |

Минимальный прогон (конкретные пробы, не группы):

```bash
# 1. Сервис (baseline — без защиты)
SECURITY_ENABLED=false RATE_LIMIT_PER_MIN=0 \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Baseline
garak --target_type rest -G eval/security/rest_config.json \
  --probes promptinject.HijackHateHumans,encoding.InjectBase64,dan.Ablation_Dan_11_0 \
  --generations 1 --parallel_attempts 2 --report_prefix baseline

# 3. After (перезапуск с SECURITY_ENABLED=true)
garak --target_type rest -G eval/security/rest_config.json \
  --probes promptinject.HijackHateHumans,encoding.InjectBase64,dan.Ablation_Dan_11_0 \
  --generations 1 --parallel_attempts 2 --report_prefix after
```

Отчёты:

- Markdown: `docs/security/garak_baseline_<date>.md`, `garak_after_<date>.md`
- JSONL/HTML: `docs/security/reports/` (сырые прогоны — `~/.local/share/garak/garak_runs/`)
- Рендер: `python3 eval/security/render_garak_report.py <report.jsonl> --title "…" --command "…" --out docs/security/…`

Подробнее — [eval/README.md](eval/README.md).

## Eval (качество ответов)

Два контура G-Eval + quality gates:

| Golden dataset | Endpoint | Кейсов |
|----------------|----------|--------|
| `eval/golden_dataset.json` | `/features/chat` | 22 |
| `eval/golden_dataset_generate.json` | `/features/generate` | 18 |

```bash
# Chat / FAQ
uv run python eval/run_evaluation.py \
  --golden eval/golden_dataset.json --judge gpt-4o-mini \
  --out eval/runs/chat-$(date +%F).json

uv run python eval/check_thresholds.py \
  --run eval/runs/chat-$(date +%F).json --thresholds eval/thresholds.yaml

# Sectioned generate
uv run python eval/run_evaluation_generate.py \
  --golden eval/golden_dataset_generate.json --judge gpt-4o-mini \
  --out eval/runs/generate-$(date +%F).json
```

Артефакты прогонов — `eval/runs/` (в `.gitignore`).

## Тесты

```bash
uv run pytest -v                  # всё (~114 тестов)
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
```

Все тесты — с моками, сеть не нужна.

| Группа | Примеры |
|--------|---------|
| **unit** | schemas, cache, retry, PII, security (validator/filter), gate_checks, tool_calls |
| **integration** | `/chat`, `/features/chat`, stream, cache, health, security (400 на injection) |
| **cassets** | JSON-фикстуры кеша и eval-runs |

Подробнее — [tests/README.md](tests/README.md).

Rate limit (нужен запущенный сервис с Redis и `RATE_LIMIT_PER_MIN=30`):

```bash
uv run python scripts/load_test.py
```

## Примеры (examples/)

```bash
# CLI — ToolCallClient напрямую
python examples/run_tool_call.py --backend deepseek
python examples/run_tool_call_fallback.py

# HTTP — нужен uvicorn на :8000
python examples/run_api_chat.py
python examples/run_api_features_chat.py
python examples/run_api_features_generate.py   # 3–8 мин
python examples/run_api_stream.py
```

Ответы — в `examples/answers/` (gitignore).

## HTTP-примеры

### Generic chat

```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Привет"}],
    "model": "gpt-4o-mini",
    "temperature": 0.7
  }'
```

### DocIntel chat (tool calling)

```bash
curl -s -X POST http://localhost:8000/features/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Найди документ про Confluence"}]}'
```

### Sectioned generate

```bash
curl -s -X POST http://localhost:8000/features/generate \
  -H "Content-Type: application/json" \
  -d '{
    "feature_brief": "Перевести уведомления на Kafka...",
    "feature_name": "Асинхронные уведомления",
    "protocol": "Async"
  }'
```

### Health / models

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
curl -s http://localhost:8000/models
```

## Конфигурация

Полный список — `.env.example`. Ключевые переменные:

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `OPENAI_API_KEY` / `LLM__OPENAI_API_KEY` | — | Ключ OpenAI (обязателен) |
| `LLM__DEFAULT_MODEL` | `gpt-4o-mini` | Модель по умолчанию |
| `REDIS_URL` | `redis://localhost:6379/0` | Кеш + rate limit |
| `SECURITY_ENABLED` | `true` | Защитный слой |
| `RATE_LIMIT_PER_MIN` | `30` | Rate limit (0 = выкл.) |
| `PHOENIX_COLLECTOR_ENDPOINT` | — | OTLP traces → Phoenix |
| `DOCINTEL__MAX_TOOL_ROUNDS` | `8` | Лимит раундов tool calling |
| `DOCINTEL__FALLBACK_BACKEND` | `ollama` | Fallback при ошибке primary |

Вложенные секции — через `__` (например `LLM__OPENAI_API_KEY`, `DOCINTEL__DOCS_DIR`).
