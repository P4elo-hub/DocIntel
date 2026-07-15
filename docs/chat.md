# Chat module (M4.1)

Модуль `app/chat/` хранит историю диалогов на стороне сервера. Контракт `/chats/{id}/messages` стабилен на весь курс: M4Б2 (Telegram-бот), M5 (RAG), M6 (tools для агентов).

## Архитектура

```mermaid
flowchart LR
    Client["Клиент (web / telegram / cli)"]
    Routes["routes.py\n/chats endpoints"]
    Service["ChatService\n+ context strategy"]
    Repo["ChatRepository"]
    Json["JsonChatRepository\nvar/chats/"]
    Pg["PostgresChatRepository"]
    DB[(PostgreSQL)]
    LLM["AsyncOpenAI\nllm_client"]

    Client --> Routes
    Routes --> Service
    Service --> Repo
    Service --> LLM
    Repo --> Json
    Repo --> Pg
    Pg --> DB
    LLM --> OpenAI["OpenAI API"]
```

## Стратегия контекста: Sliding Window

Выбрана **sliding window** — последние `CHAT_CONTEXT_WINDOW` сообщений плюс `system_prompt` чата.

**Обоснование:** дипломный проект — SaaS-ассистент для методологии фич и DocIntel. Типичные сценарии — короткие FAQ-диалоги, уточнение требований к секции документа, быстрые вопросы по шаблону. Длинная «память» через summary (hybrid) здесь избыточна: контекст ограничен текущей задачей, а полная история остаётся в хранилище и доступна через `GET /chats/{id}/messages`. Sliding window проще, предсказуемее и дешевле по токенам.

Token budget: `fit_to_budget()` обрезает historic-часть, если `count_tokens()` превышает `CHAT_MODEL_CONTEXT_WINDOW - CHAT_RESPONSE_TOKENS - CHAT_SAFETY_MARGIN`. System-сообщения сохраняются.

## Endpoints

### Создать чат

```bash
curl -s -X POST http://localhost:8000/chats \
  -H 'Content-Type: application/json' \
  -d '{
    "owner_external_id": "tg-123456789",
    "interface": "telegram",
    "system_prompt": "Ты помощник по методологии фич."
  }'
```

Ответ: `{"chat_id":"<uuid>"}`

### Отправить сообщение (SSE)

```bash
CHAT_ID="<uuid из предыдущего шага>"

curl -N -X POST "http://localhost:8000/chats/${CHAT_ID}/messages" \
  -H 'Content-Type: application/json' \
  -d '{"content": "Как оформить NFR для платёжного шлюза?"}'
```

Формат SSE: `data: <токен>\n\n` … `data: [DONE]\n\n`

### История сообщений

```bash
curl -s "http://localhost:8000/chats/${CHAT_ID}/messages?limit=50"
```

### Метаданные чата

```bash
curl -s "http://localhost:8000/chats/${CHAT_ID}"
```

### Очистить историю (soft delete)

```bash
curl -s -X DELETE "http://localhost:8000/chats/${CHAT_ID}/messages"
```

Ответ: `{"status":"ok"}`

## Переключение хранилища

| Режим | Переменная | Описание |
|-------|------------|----------|
| JSON (по умолчанию) | `CHAT_REPOSITORY=json` | Файлы в `CHAT_STORAGE_DIR/chats/<id>/` |
| PostgreSQL | `CHAT_REPOSITORY=postgres` | Требует `DATABASE_URL` и миграции |

### JSON (локальная разработка)

```bash
CHAT_REPOSITORY=json
CHAT_STORAGE_DIR=./var/chats
uv run uvicorn app.main:app --reload
```

### PostgreSQL

```bash
docker compose -f docker-compose.test.yml up -d
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/llm_service
export CHAT_REPOSITORY=postgres
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Структура на диске (JSON):

```
var/chats/
└── chats/
    └── <chat_id>/
        ├── chat.json
        └── messages.jsonl
```

## Миграции

```bash
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "описание"
```

## Тесты

```bash
# Только JSON (быстро)
uv run pytest tests/chat/test_repository_contract.py -k json

# Полный контракт (JSON + Postgres через testcontainers)
uv run pytest tests/chat/

# API routes
uv run pytest tests/chat/test_routes.py
```

Для Postgres без testcontainers:

```bash
docker compose -f docker-compose.test.yml up -d
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/llm_service \
  uv run pytest tests/chat/test_repository_contract.py -k postgres
```
