# llm-service

FastAPI-сервис для курса «ИИ-разработчик»: generic LLM-чат (`/chat`), DocIntel с tool calling (`/features/*`), **серверная история чатов и Telegram-бот** (M4.1 / M4Б2), **RAG по базе знаний на LlamaIndex + Qdrant** (Б5, `/rag/query`, встроен в чат-бота), observability (structlog + Phoenix), защитный слой (Б3.8) и eval/garak.

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

Напишите боту в Telegram: `/start` → текстовое сообщение.

- **Шпаргалка портов и операций** (ссылки localhost, Qdrant reindex, логи) — **[docs/services.md](docs/services.md)**
- Подробный Docker-гайд — **[docs/docker.md](docs/docker.md)**

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
| **RAG** | `POST /rag/query` — ответ по базе знаний с цитатами; индексация в Qdrant через LlamaIndex; тот же RAG встроен в Telegram-бота (Вариант C) |
| **Security** | Валидация входа, canary, фильтр выхода, PII в логах, rate limit — на `/chat` и `/features/chat` |
| **Observability** | structlog (JSON), OpenTelemetry → Phoenix, `X-Request-ID`, `X-LLM-Cost-USD` |
| **Eval / Garak** | G-Eval + quality gates; сканирование prompt-injection |

Swagger UI — http://localhost:8000/docs

## Структура репозитория

```
app/
├── main.py                    # lifespan, middleware, routers
├── chat/                      # /chats — история, SSE, модерация, media, RAG-контекст
├── admin/                     # /chats/admin/* — stats, broadcast, handoff
├── moderation/, ratelimit/    # каскад модерации, лимит сообщений (Postgres)
├── routers/                   # /chat, /features/*, /rag, /documents, health, models
├── services/                  # llm, docintel, rag, ingestion, vector_store, embeddings, …
└── observability/             # structlog, PII, tracing → Phoenix

bot/                           # Telegram: long polling + /notify :9000
├── __main__.py                # python -m bot
├── handlers/                  # text, media, commands, fsm, feedback, admin
└── services/backend_client.py # HTTP-клиент к /chats

alembic/                       # миграции Postgres (чаты + production-таблицы)
data/                          # корпуса RAG: rag-block-03 (sample), my-kb (личная, gitignore)
docs/services.md               # Шпаргалка: порты, ссылки, reindex, логи
docs/docker.md                 # Docker, бот, Qdrant, логи, Redis, Adminer
docs/rag.md                    # RAG: LlamaIndex, Qdrant, чанкинг, метаданные, reindex
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
| **`qdrant`** | 6333 / 6334 | Векторное хранилище RAG (эмбеддинги + метаданные) |
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

## RAG (база знаний)

RAG на **LlamaIndex + Qdrant**: корпус markdown-документов индексируется в
векторное хранилище Qdrant, а ответ строится строго по найденному контексту с
цитатами `[n]`. Тот же RAG встроен в Telegram-бота (Вариант C): при
`CHAT_RAG_ENABLED=true` каждый вопрос (в т.ч. голосовой — по транскрипту)
обогащается найденными источниками, и модель отвечает по базе знаний.

**Пайплайн:** `SimpleDirectoryReader → header-aware чанкинг → text-embedding-3-small
→ Qdrant → dense-поиск (top_k) → (опц. reranker) → LLM с цитатами`. Порог
`RAG_SCORE_THRESHOLD` + инструкция «отвечай только по источникам» отсекают выдумки.

| Компонент | Где |
|-----------|-----|
| Ретрив + синтез (LlamaIndex) | `app/services/rag.py` |
| Индексация корпуса, метаданные, дедупликация | `app/services/ingestion.py` |
| Векторное хранилище (Qdrant) | `app/services/vector_store.py`, сервис `qdrant` в Docker |
| Встраивание RAG в чат/бота | `app/chat/service.py` |
| Bare-metal сравнение (без фреймворка) | `app/services/rag_baremetal.py` |

**Корпуса** в `data/`:

- `data/rag-block-03/` — учебный sample-корпус (10 документов), едет в репозиторий;
- `data/my-kb/` — личная база знаний (SIHIST «История операций»), **локальная**,
  в git не коммитится (`.gitignore`). Внутри `_actual/` — курируемые «источники
  правды» (глоссарий, интеграции, лента), имеющие приоритет над отдельными фичами.

### Эндпоинты

```bash
# Поиск/ответ по базе знаний с цитатами
curl -s -X POST http://localhost:8000/rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"со сколькими сервисами интегрируется история операций?"}'

# Загрузить документ в индекс
curl -s -X POST http://localhost:8000/documents/upload -F 'file=@doc.md'

# Переиндексация: full (снести и заново) | incremental (по хешам) | files
curl -s -X POST http://localhost:8000/documents/reindex \
  -H 'Content-Type: application/json' -d '{"mode":"full"}'
```

`/rag/query` показывает `top_score` / `sources` / `snippet` — так видно, где
проблема: в поиске (крутить `RAG_RETRIEVE_TOP_K`, чанкинг) или в генерации (промпт).

### Ключевые переменные (`.env`)

| Переменная | Default | Назначение |
|------------|---------|------------|
| `CHAT_RAG_ENABLED` | `true` | Встроенный RAG в чат/бота (Вариант C) |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant (в Docker-сети; локально `localhost:6333`) |
| `RAG_DATA_DIR` | `data/rag-block-03` | Каталог корпуса (для личной базы — `data/my-kb`) |
| `RAG_COLLECTION` | `rag_block_03` | Коллекция Qdrant (LlamaIndex) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `text-embedding-3-small` / `1536` | Эмбеддинги |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `1024` / `128` | Размер чанка |
| `RAG_CHUNK_BY_HEADINGS` | `true` | Нарезка markdown по заголовкам |
| `RAG_RETRIEVE_TOP_K` / `RAG_RERANK_TOP_N` | `25` / `10` | Ширина поиска / сколько в контекст |
| `RAG_SCORE_THRESHOLD` | `0.3` | Ниже порога → «в базе не нашёл» |
| `RAG_SKIP_DEPRECATED` | `true` | Не индексировать устаревшее (`superseded_by:`, «Старая Лента») |
| `RAG_USE_RERANKER` / `RAG_USE_HYBRID` | `false` | Cross-encoder / dense+BM25 (см. `docs/rag.md`) |

> Смена `chunk_size`, hybrid или `skip_deprecated` требует **полного reindex**
> существующей коллекции (`{"mode":"full"}`).

**Подробно** — [docs/rag.md](docs/rag.md): чанкинг, метаданные, дедупликация,
reranker/hybrid, сравнение LlamaIndex vs bare-metal.

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
| `QDRANT_URL` | `http://localhost:6333` | Векторное хранилище RAG (в Docker — `http://qdrant:6333`) |
| `CHAT_RAG_ENABLED` | `true` | Встроенный RAG в чат/бота (см. раздел RAG и `docs/rag.md`) |
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
