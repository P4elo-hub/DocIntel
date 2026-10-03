# Docker: полный стек (API, Telegram-бот, Postgres, Redis, Qdrant, Phoenix)

Одна команда поднимает FastAPI, Telegram-бот, Postgres, Redis, **Qdrant** (векторное хранилище RAG), Phoenix, Adminer и одноразовый `migrate`.

## Быстрый старт

### 1. Создайте `.env`

```bash
cp .env.example .env
```

### 2. Обязательно заполните

| Переменная | Где взять | Зачем |
|------------|-----------|-------|
| **`BOT_TOKEN`** | [@BotFather](https://t.me/BotFather) → `/newbot` → скопировать токен | Бот подключается к Telegram **только** через эту переменную |
| **`OPENAI_API_KEY`** | platform.openai.com | Ответы LLM в backend и модерация |
| **`INTERNAL_TOKEN`** | `openssl rand -hex 32` | Секрет backend ↔ bot (`/notify`) |
| **`ADMIN_TOKEN`** | `openssl rand -hex 32` | Admin API `/chats/admin/*` и команды бота `/stats`, `/broadcast` |

Пример фрагмента `.env`:

```env
OPENAI_API_KEY=sk-...
BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BOT_ADMIN_IDS=123456789
INTERNAL_TOKEN=a1b2c3...
ADMIN_TOKEN=d4e5f6...
ADMIN_CHAT_ID=-1001234567890
```

> **Куда подставить токен бота:** в файл **`.env` в корне проекта** (рядом с `compose.yaml`), строка `BOT_TOKEN=...`.  
> Docker и локальный запуск читают один и тот же `.env`. После изменения перезапустите сервис `bot`.

### 3. Запуск

```bash
docker compose up --build
```

Порядок старта: `postgres` + `qdrant` (healthcheck) → `migrate` (Alembic) → `app` (healthcheck) → `bot`.

### 4. Проверка в Telegram

1. Найдите бота по username из BotFather.
2. Отправьте `/start` — в логах `app` должно быть `POST /chats 200`.
3. Напишите текст — ответ приходит стримом (черновик → финальное сообщение).

---

## Сервисы и порты

| Сервис | Контейнер | URL / порт | Роль |
|--------|-----------|------------|------|
| **API + Swagger** | `llm-service` | http://localhost:8000/docs | FastAPI, `/chat`, `/features/*`, `/chats/*` |
| **Telegram-бот** | `chat-bot` | порт **9000** только внутри Docker | Long polling + `/notify` для push от backend |
| **Postgres** | `llm-postgres` | `localhost:5432` | История чатов, feedback, rate-limit, alerts |
| **Adminer** | `llm-adminer` | http://localhost:8080 | Веб-UI для Postgres |
| **Redis** | `llm-redis` | внутри сети `redis:6379` | Кеш `/chat`, HTTP rate limit (Б3.8) |
| **Qdrant Dashboard** | `llm-qdrant` | http://localhost:6333/dashboard | Веб-UI: коллекции, точки, поиск |
| **Qdrant REST** | `llm-qdrant` | http://localhost:6333 (JSON API), `6334` (gRPC) | Корневой `/` отдаёт JSON версии — это не UI |
| **Phoenix** | `llm-phoenix` | http://localhost:6006 | Трейсы LLM (OpenTelemetry) |
| **migrate** | `llm-migrate` | — | `alembic upgrade head`, завершается и выходит |

Volumes (данные сохраняются между `docker compose down`):

| Volume | Что хранит |
|--------|------------|
| `postgres_data` | БД Postgres (чаты, сообщения, feedback) |
| `redis_data` | Redis AOF/RDB |
| `qdrant_storage` | Коллекции Qdrant (векторы RAG + payload) |
| `phoenix-data` | Данные Phoenix |
| `chat_data` | JSON-чаты, если `CHAT_REPOSITORY=json` |

---

## Telegram-бот

### Переменные (`.env`)

| Переменная | Docker (compose) | Локально (`python -m bot`) |
|------------|------------------|----------------------------|
| `BOT_TOKEN` | из `.env` | из `.env` |
| `BACKEND_URL` | `http://app:8000` (в `compose.yaml`) | `http://localhost:8000` |
| `BOT_ADMIN_IDS` | из `.env`, через запятую | то же |
| `ADMIN_TOKEN` | из `.env` | то же |
| `INTERNAL_TOKEN` | из `.env` | то же |
| `ADMIN_CHAT_ID` | опционально, для алертов в админ-чат | то же |
| `BOT_API_PORT` | `9000` (по умолчанию) | `9000` |

### Команды бота

| Команда | Кому | Действие |
|---------|------|----------|
| `/start` | все | Создаёт чат в backend, приветствие |
| `/help` | все | Список команд |
| `/ask` | все | FSM: выбор темы → вопрос → ответ LLM |
| `/clear` | все | Очищает историю в Postgres |
| `/cancel` | все | Сброс FSM-сценария |
| `/operator` | все | Запрос живого оператора (handoff) |
| `/stats` | только `BOT_ADMIN_IDS` | Статистика за 24ч |
| `/broadcast <текст>` | только `BOT_ADMIN_IDS` | Рассылка всем telegram-пользователям |

Медиа: фото, голос, PDF, DOCX — бот шлёт multipart в backend, обработка на стороне API.

### Логи бота

```bash
docker compose logs -f bot
```

Успешный старт: `Bot starting (backend=http://app:8000, notify-port=9000, ...)`.

### Push из backend в Telegram (`/notify`)

Для отладки с хоста добавьте в `compose.yaml` у сервиса `bot`:

```yaml
ports:
  - "9000:9000"
```

```bash
curl -X POST http://localhost:9000/notify \
  -H "X-Internal-Token: <INTERNAL_TOKEN из .env>" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": <ваш Telegram chat_id>, "text": "Тест из backend"}'
```

`chat_id` — числовой ID вашего личного чата с ботом (можно узнать у [@userinfobot](https://t.me/userinfobot)).

---

## Postgres и Adminer

### Adminer — как зайти

1. http://localhost:8080
2. Форма:
   - **Система:** PostgreSQL
   - **Сервер:** `postgres` ← **не** `localhost`
   - **Пользователь:** `postgres`
   - **Пароль:** `postgres`
   - **База:** `llm_service`

Быстрая ссылка: http://localhost:8080/?pgsql=postgres&username=postgres&db=llm_service

### Таблицы (после миграций M4.1 + bot)

| Таблица | Назначение |
|---------|------------|
| `chats` | Диалоги (`owner_external_id` = Telegram chat id для `interface=telegram`) |
| `chat_messages` | Сообщения user/assistant, `media_refs`, soft delete |
| `message_feedback` | 👍/👎 (`owner_external_id`, `message_id`) |
| `rate_limits` | Счётчики rate-limit по минутам |
| `alerts` | Очередь алертов (модерация, handoff) |
| `system_prompts` | A/B системные промпты |

### Полезные SQL

```sql
-- Чаты Telegram
SELECT id, owner_external_id, interface, handoff_status, created_at
FROM chats WHERE interface = 'telegram' ORDER BY created_at DESC;

-- Последние сообщения
SELECT m.role, left(m.content, 80) AS preview, m.created_at
FROM chat_messages m
WHERE m.deleted_at IS NULL
ORDER BY m.created_at DESC LIMIT 20;

-- Feedback
SELECT * FROM message_feedback ORDER BY created_at DESC;
```

### psql из терминала

```bash
docker exec -it llm-postgres psql -U postgres -d llm_service
```

---

## Redis

Используется сервисом `app`:

- кеш ответов `/chat` при `temperature=0`;
- HTTP rate limit (`RATE_LIMIT_PER_MIN`) на `/chat` и `/features/chat`.

Rate limit **Telegram-диалогов** (`RATE_LIMIT_MESSAGES_PER_MIN`) — отдельно, в Postgres (`rate_limits`), не в Redis.

```bash
# Ping
docker exec -it llm-redis redis-cli ping

# Ключи (осторожно на prod)
docker exec -it llm-redis redis-cli KEYS '*'
```

Логи Redis обычно не нужны; при проблемах с кешем смотрите логи `app`.

---

## Qdrant (векторное хранилище RAG)

Qdrant хранит эмбеддинги корпуса и метаданные для RAG. Сервис `app` ходит в него
по `QDRANT_URL` (в Docker-сети — `http://qdrant:6333`), стартует только когда
Qdrant `healthy` (`depends_on`). Данные лежат в volume `qdrant_storage` и
переживают `docker compose down` (но не `down -v`).

| Параметр | Значение |
|----------|----------|
| Образ | `qdrant/qdrant:v1.14.0` |
| **Dashboard (UI)** | **http://localhost:6333/dashboard** |
| REST API (JSON) | http://localhost:6333 — корень отвечает `{"title":"qdrant..."}`, это нормально |
| gRPC | `localhost:6334` |
| Volume | `qdrant_storage:/qdrant/storage` |
| В сети для `app` | `QDRANT_URL=http://qdrant:6333` |

**Открывать UI только так:** [http://localhost:6333/dashboard](http://localhost:6333/dashboard)  
(не `http://localhost:6333` — там просто JSON API, не интерфейс).

```bash
# Список коллекций
curl -s http://localhost:6333/collections | jq

# Инфо по коллекции RAG (число точек, конфиг вектора)
curl -s http://localhost:6333/collections/rag_block_03 | jq '.result.points_count, .result.config.params'

# Здоровье
curl -s http://localhost:6333/healthz
```

### Индексация корпуса

Корпус (каталог из `RAG_DATA_DIR`) индексируется в Qdrant при старте, если
коллекция пуста. Управление руками — через backend:

```bash
# Полная переиндексация (снести коллекцию + docstore и построить заново)
curl -s -X POST http://localhost:8000/documents/reindex \
  -H 'Content-Type: application/json' -d '{"mode":"full"}'

# Инкрементально (только новые/изменённые документы по хешам)
curl -s -X POST http://localhost:8000/documents/reindex \
  -H 'Content-Type: application/json' -d '{"mode":"incremental"}'
```

Прогресс — в логах `app` (`ingestion: ...`), готовность RAG — событие `rag_ready`.
Проверить поиск отдельно от генерации: `POST /rag/query` (см. **[rag.md](rag.md)**).

> Смена `RAG_CHUNK_SIZE`, `RAG_CHUNK_BY_HEADINGS`, `RAG_SKIP_DEPRECATED` или
> включение hybrid требует **полного** reindex (`{"mode":"full"}`) — иначе старые
> чанки в коллекции останутся нетронутыми.

### Ключевые переменные RAG (`.env`)

| Переменная | Default | Назначение |
|------------|---------|------------|
| `QDRANT_URL` | `http://qdrant:6333` | Адрес Qdrant в Docker-сети |
| `CHAT_RAG_ENABLED` | `true` | Встроить RAG в чат/бота (Вариант C) |
| `RAG_DATA_DIR` | `data/rag-block-03` | Каталог корпуса (личная база — `data/my-kb`) |
| `RAG_COLLECTION` | `rag_block_03` | Имя коллекции Qdrant |
| `RAG_RETRIEVE_TOP_K` / `RAG_RERANK_TOP_N` | `25` / `10` | Ширина поиска / в контекст LLM |
| `RAG_SCORE_THRESHOLD` | `0.3` | Ниже → «в базе не нашёл» |

Полный список и тюнинг качества — **[rag.md](rag.md)**.

---

## Логи и отладка

```bash
# Все сервисы
docker compose logs -f

# Только API
docker compose logs -f app

# Только бот
docker compose logs -f bot

# Миграции (один раз при старте)
docker compose logs migrate

# Postgres / Redis / Qdrant
docker compose logs -f postgres redis qdrant
```

**Что искать:**

| Событие | Где смотреть |
|---------|--------------|
| `POST /chats 200` после `/start` | `docker compose logs app` |
| `POST /chats/.../messages` (SSE) | `app` |
| `403 moderation_blocked` | `app` — модерация сработала |
| `429 rate_limit` | `app` — лимит сообщений в минуту |
| Ошибки polling / Telegram | `bot` |
| Трейсы LLM | http://localhost:6006 (Phoenix) |

Dev-режим (`compose.override.yaml`): hot-reload `app/`, `LOG_LEVEL=DEBUG`, `RATE_LIMIT_PER_MIN=0`.

---

## Admin API (backend)

Защита: заголовок `X-Admin-Token` = значение `ADMIN_TOKEN` из `.env`.

| Endpoint | Назначение |
|----------|------------|
| `GET /chats/admin/stats` | Сообщения, DAU, feedback ratio |
| `GET /chats/admin/export` | Экспорт с маскированием PII |
| `POST /chats/admin/broadcast` | Рассылка через bot `/notify` |
| `POST /chats/admin/handoff` | Пауза чата для оператора |
| `GET /chats/admin/alerts` | Pending-алерты |

Пример:

```bash
curl -s http://localhost:8000/chats/admin/stats \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

---

## Переменные в Docker

В `compose.yaml` для `app` задано:

```env
CHAT_REPOSITORY=postgres
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/llm_service
BOT_URL=http://bot:9000
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
```

Переключить хранилище чатов на JSON:

```bash
CHAT_REPOSITORY=json docker compose up --build
```

Файлы: `./var/chats/chats/<chat_id>/` (volume в dev через `compose.override.yaml`).

---

## Локальный запуск без Docker

```bash
uv sync
cp .env.example .env   # BOT_TOKEN, OPENAI_API_KEY, токены

# Терминал 1 — Postgres локально или только CHAT_REPOSITORY=json
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Терминал 2 — в .env: BACKEND_URL=http://localhost:8000
uv run python -m bot
```

---

## Полезные команды

```bash
# Пересобрать и поднять
docker compose up --build -d

# Статус
docker compose ps

# Повторить миграции
docker compose run --rm migrate python -m alembic upgrade head

# Остановить (данные Postgres в volume сохранятся)
docker compose down

# Удалить контейнеры и volumes (⚠️ потеря данных БД)
docker compose down -v
```

---

## Проверка API чата (curl)

```bash
# Создать чат
curl -s -X POST http://localhost:8000/chats \
  -H 'Content-Type: application/json' \
  -d '{"owner_external_id":"docker-test","interface":"cli"}'

# Сообщение (multipart + SSE — как бот)
CHAT_ID=<uuid из ответа>
curl -N -X POST "http://localhost:8000/chats/${CHAT_ID}/messages" \
  -F 'content=Привет из Docker'
```

После этого обновите `chat_messages` в Adminer.

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| Бот не отвечает | Проверьте `BOT_TOKEN` в `.env`, `docker compose logs bot`, что `app` healthy |
| `401 Unauthorized` Telegram | Неверный или протухший `BOT_TOKEN` |
| Пустые ответы LLM | `OPENAI_API_KEY` в `.env`, логи `app` |
| Adminer «Connection refused» | Сервер = `postgres`, не `localhost` |
| `503 feedback requires postgres` | `CHAT_REPOSITORY=postgres`, миграции применены |
| Бот не видит backend | В Docker `BACKEND_URL=http://app:8000`; локально `http://localhost:8000` |
| RAG отвечает «в базе не нашёл» / `503` на `/rag/query` | Qdrant `healthy` (`docker compose ps`), коллекция не пуста (`/collections/<name>`), при необходимости reindex `{"mode":"full"}` |
| Пустая коллекция после `down -v` | Volume `qdrant_storage` удалён — переиндексируйте (`/documents/reindex`) |
| `app` не стартует, ждёт Qdrant | Qдрант не `healthy` — смотрите `docker compose logs qdrant`, порт `6333` |
