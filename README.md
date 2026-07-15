# llm-service

FastAPI-сервис для курса «ИИ-разработчик»: generic LLM-чат (`/chat`), DocIntel с tool calling (`/features/*`), **серверная история чатов и Telegram-бот** (M4.1 / M4Б2), observability (structlog + Phoenix), защитный слой (Б3.8) и eval/garak.

Swagger UI — http://localhost:8000/docs

## Быстрый старт с Telegram-ботом

### 1. Токен бота

Получите токен у [@BotFather](https://t.me/BotFather) (`/newbot`) и вставьте в **`.env`** в корне проекта:

```env
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-...
BOT_ADMIN_IDS=123456789
INTERNAL_TOKEN=<openssl rand -hex 32>
ADMIN_TOKEN=<openssl rand -hex 32>
```

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| **`BOT_TOKEN`** | да | Токен от BotFather — без него бот не подключится к Telegram |
| `OPENAI_API_KEY` | да | Ответы LLM и (опционально) OpenAI Moderation |
| `BOT_ADMIN_IDS` | для `/stats`, `/broadcast` | Ваш Telegram user id (через запятую) |
| `INTERNAL_TOKEN` | для `/notify` | Общий секрет backend ↔ bot |
| `ADMIN_TOKEN` | для admin API | То же значение использует бот для `/stats` |

```bash
cp .env.example .env
# отредактируйте .env — минимум BOT_TOKEN и OPENAI_API_KEY
docker compose up --build
```

Напишите боту в Telegram: `/start` → текстовое сообщение. Подробная инструкция по Docker, логам, Redis, Postgres и Adminer — **[docs/docker.md](docs/docker.md)**.

### Команды бота

| Команда | Описание |
|---------|----------|
| `/start`, `/help` | Старт и справка |
| `/ask` | Вопрос с выбором темы (FSM) |
| `/clear` | Очистить историю в backend |
| `/cancel` | Отменить сценарий |
| `/operator` | Запрос оператора |
| `/stats`, `/broadcast` | Только для ID из `BOT_ADMIN_IDS` |

---

## Что делает система

| Слой | Назначение |
|------|------------|
| **Generic chat** | `POST /chat` — прямой вызов OpenAI, кеш Redis при `temperature=0`, retry, streaming/batch |
| **Chat history + bot** | `POST /chats/*` — история в Postgres, multipart/SSE, модерация, rate-limit; **`bot/`** — Telegram-клиент |
| **DocIntel** | `POST /features/chat` — tool calling; `POST /features/generate` — sectioned-документация |
| **Security** | Валидация входа, canary, фильтр выхода, PII в логах, rate limit — на `/chat` и `/features/chat` |
| **Observability** | structlog (JSON), OpenTelemetry → Phoenix, `X-Request-ID`, `X-LLM-Cost-USD` |
| **Eval / Garak** | G-Eval + quality gates; сканирование prompt-injection |

Swagger UI — http://localhost:8000/docs

## Структура репозитория

```
app/
├── main.py                    # lifespan, middleware, routers
├── chat/                      # /chats — история, SSE, модерация, media
├── admin/                     # /chats/admin/* — stats, broadcast, handoff
├── moderation/, ratelimit/    # каскад модерации, лимит сообщений (Postgres)
├── routers/                   # /chat, /features/*, health, models
├── services/                  # llm, docintel, security, notifier, …
└── observability/             # structlog, PII, tracing → Phoenix

bot/                           # Telegram: long polling + /notify :9000
├── __main__.py                # python -m bot
├── handlers/                  # text, media, commands, fsm, feedback, admin
└── services/backend_client.py # HTTP-клиент к /chats

alembic/                       # миграции Postgres (чаты + production-таблицы)
docs/docker.md                 # Docker, бот, логи, Redis, Adminer
```

## Запуск локально

Нужен `uv` и Python ≥ 3.12.

```bash
uv sync
cp .env.example .env          # BOT_TOKEN, OPENAI_API_KEY — обязательны для бота

# Терминал 1 — API
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Терминал 2 — бот (в .env: BACKEND_URL=http://localhost:8000)
uv run python -m bot
```

Redis опционален для API: без Redis сервис стартует без кеша, `/ready` → `degraded`.

## Docker Compose

```bash
cp .env.example .env          # BOT_TOKEN + OPENAI_API_KEY
docker compose up --build
```

| Сервис | Порт | Роль |
|--------|------|------|
| `app` | 8000 | FastAPI |
| **`bot`** | 9000 (внутри сети) | Telegram long polling + `/notify` |
| `postgres` | 5432 | История чатов, feedback, rate-limit |
| `migrate` | — | `alembic upgrade head` |
| `redis` | — | Кеш `/chat` + HTTP rate limit |
| `phoenix` | 6006 | Трейсы LLM |
| `adminer` | 8080 | Веб-UI Postgres |

**Полная инструкция:** [docs/docker.md](docs/docker.md) — токен бота, логи, Redis, Adminer, SQL, troubleshooting.

Переменные в `compose.yaml` (можно переопределить в `.env`):

| Переменная | Default в compose | Назначение |
|------------|-------------------|------------|
| `CHAT_REPOSITORY` | `postgres` | Хранилище чатов: `postgres` или `json` |
| `DATABASE_URL` | `...@postgres:5432/llm_service` | Postgres в Docker-сети |
| `BOT_URL` | `http://bot:9000` | Backend → bot `/notify` |
| `SECURITY_ENABLED` | `true` | Защитный слой на `/chat`, `/features/chat` |
| `RATE_LIMIT_PER_MIN` | `30` | HTTP rate limit (Redis) |
| `RATE_LIMIT_MESSAGES_PER_MIN` | из `.env` (15) | Лимит сообщений Telegram на user (Postgres) |
| `REDIS_URL` | `redis://redis:6379/0` | Кеш и HTTP rate limit |

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
| `BOT_TOKEN` | — | Telegram BotFather (см. быстрый старт выше) |
| `BOT_ADMIN_IDS` | — | Telegram user id админов бота |
| `INTERNAL_TOKEN` / `ADMIN_TOKEN` | — | Секреты backend ↔ bot и admin API |
| `MODERATION_USE_OPENAI` | `true` | OpenAI Moderation для `/chats/.../messages` |
| `DOCINTEL__MAX_TOOL_ROUNDS` | `8` | Лимит раундов tool calling |
| `DOCINTEL__FALLBACK_BACKEND` | `ollama` | Fallback при ошибке primary |

Вложенные секции — через `__` (например `LLM__OPENAI_API_KEY`, `DOCINTEL__DOCS_DIR`).
