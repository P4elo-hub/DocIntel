# Сервисы: ссылки, порты, типовые операции

Короткая шпаргалка «куда кликнуть / что перезапустить».  
Подробный Docker-гайд: [docker.md](docker.md) · RAG: [rag.md](rag.md) · агенты: [agent-graph-diagrams.md](agent-graph-diagrams.md)

```bash
# Поднять всё
docker compose up --build -d

# Статус
docker compose ps
```

---

## Открыть в браузере

| Что | Ссылка | Зачем |
|-----|--------|-------|
| **Swagger API** | http://localhost:8000/docs | Ручки `/chats`, `/rag`, `/documents`, `/features` |
| **Health API** | http://localhost:8000/health | Жив ли backend |
| **Ready** | http://localhost:8000/ready | Postgres / Redis / Qdrant (degraded ok) |
| **Adminer** (Postgres UI) | http://localhost:8080 | Смотреть чаты, сообщения |
| **Adminer (быстрый вход)** | http://localhost:8080/?pgsql=postgres&username=postgres&db=llm_service | Форма уже с сервером `postgres` |
| **Qdrant Dashboard** | http://localhost:6333/dashboard | Коллекции, точки, поиск по векторам |
| **Qdrant REST** | http://localhost:6333 | API (`/collections`, `/healthz`) |
| **Phoenix** (трейсы LLM) | http://localhost:6006 | Трейсы OpenAI / агентов |

### Adminer — логин

| Поле | Значение |
|------|----------|
| Система | PostgreSQL |
| Сервер | `postgres` (**не** `localhost`) |
| Пользователь | `postgres` |
| Пароль | `postgres` |
| База | `llm_service` |

### Порты (с хоста)

| Порт | Сервис |
|------|--------|
| `8000` | FastAPI (`app`) |
| `8080` | Adminer |
| `5432` | Postgres |
| `6333` | Qdrant REST + UI |
| `6334` | Qdrant gRPC |
| `6006` | Phoenix UI |
| `4317` | Phoenix OTLP (gRPC) |
| `9000` | Bot `/notify` — **только внутри Docker**, с хоста не открыт |
| Redis | без publish на хост (`redis:6379` в сети compose) |

---

## Логи

```bash
# Все сервисы
docker compose logs -f

# Backend (API, RAG, агенты)
docker compose logs -f app

# Telegram-бот
docker compose logs -f bot

# Qdrant / Postgres / Phoenix
docker compose logs -f qdrant
docker compose logs -f postgres
docker compose logs -f phoenix

# Хвост без follow
docker compose logs --tail=100 app bot
```

Что искать в логах `app`:

| Событие | Значение |
|---------|----------|
| `rag_ready` | RAG-индекс собран |
| `chat_agent_pipeline_start` / `_done` | Сообщение из Telegram пошло через LangGraph-агентов |
| `agents=["intent_router","search_agent"]` | Только поиск |
| `... "write_agent"]` | Поиск → написание документации |
| `POST /chats 200` | Бот достучался до backend |

---

## Qdrant: посмотреть и переиндексировать

### Посмотреть коллекции

```bash
curl -s http://localhost:6333/collections | jq
curl -s http://localhost:6333/healthz

# Имя коллекции — из .env (RAG_COLLECTION), у тебя часто rag_my_diploma
curl -s http://localhost:6333/collections/rag_my_diploma | jq '.result.points_count'
```

Или UI: http://localhost:6333/dashboard

### Переиндексация корпуса

Корпус = каталог `RAG_DATA_DIR` (в Docker смонтирован `./data` → `/app/data`).

```bash
# Полный rebuild (после смены чанкинга / hybrid / корпуса)
curl -s -X POST http://localhost:8000/documents/reindex \
  -H 'Content-Type: application/json' \
  -d '{"mode":"full"}' | jq

# Только новые/изменённые файлы
curl -s -X POST http://localhost:8000/documents/reindex \
  -H 'Content-Type: application/json' \
  -d '{"mode":"incremental"}' | jq

# Залить один файл и проиндексировать
curl -s -X POST http://localhost:8000/documents/upload \
  -F 'file=@./data/my-kb/some-doc.md' | jq
```

Прогресс — в `docker compose logs -f app` (`ingestion: ...`).

Проверить поиск без Telegram:

```bash
curl -s -X POST http://localhost:8000/rag/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"импорт из Confluence"}' | jq '.answer, .top_score, .sources'
```

> Смена `RAG_CHUNK_SIZE`, `RAG_CHUNK_BY_HEADINGS`, `RAG_USE_HYBRID`, `RAG_SKIP_DEPRECATED`  
> или смена корпуса → нужен **`mode: full`**.

---

## Telegram + агенты DocIntel

Флаг в `.env`: `CHAT_AGENT_ENABLED=true`

| Пишешь боту | Что вызывается |
|-------------|----------------|
| «Как работает импорт из Confluence?» | `search_agent` |
| «Сделай документацию для новой ручки webhook» | `search_agent` → `write_agent` |
| «Привет» | короткий ответ без агентов |

После смены кода агентов:

```bash
docker compose up --build -d app bot
docker compose logs -f app bot
```

Схема графа: [agent-graph.png](agent-graph.png) · [agent-graph-diagrams.md](agent-graph-diagrams.md)

---

## Postgres: быстрый взгляд

```bash
docker exec -it llm-postgres psql -U postgres -d llm_service
```

```sql
-- Последние Telegram-чаты
SELECT id, owner_external_id, created_at
FROM chats WHERE interface = 'telegram'
ORDER BY created_at DESC LIMIT 10;

-- Последние сообщения
SELECT role, left(content, 100), created_at
FROM chat_messages
WHERE deleted_at IS NULL
ORDER BY created_at DESC LIMIT 20;
```

Или через Adminer: http://localhost:8080

---

## Redis / Phoenix

```bash
# Redis жив?
docker exec -it llm-redis redis-cli ping

# Phoenix UI
open http://localhost:6006   # или просто открыть в браузере
```

Phoenix собирает трейсы LLM (и при включённом tracing — RAG/агентов).

---

## Частые команды

```bash
# Пересобрать и перезапустить всё
docker compose up --build -d

# Только API + бот
docker compose up --build -d app bot

# Остановить (данные в volumes останутся)
docker compose down

# Остановить И снести volumes (БД / Qdrant / Redis — с нуля)
docker compose down -v

# Docker не отвечает?
# → открой Docker Desktop, дождись Running, затем снова compose up
docker info
```

---

## Карта «что за что отвечает»

```text
Telegram ──► bot (внутри :9000)
               │
               ▼
            app :8000 ──► Postgres :5432      (история чатов)
                   ├──► Redis                 (кеш / rate limit)
                   ├──► Qdrant :6333          (RAG-векторы)
                   ├──► OpenAI                (LLM + embeddings)
                   └──► Phoenix :6006         (трейсы)

Adminer :8080 ──► Postgres
```

При `CHAT_AGENT_ENABLED=true` путь ответа в чате:

```text
сообщение → intent_router → search_agent → [write_agent] → ответ в Telegram
```
