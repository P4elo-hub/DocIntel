# Observability — Phoenix traces

## Скриншот трейса

![Phoenix trace](phoenix-trace-screenshot.png)

> **Как получить скриншот:** поднимите стек `docker compose up --build`, выполните несколько запросов к `POST /chat`, откройте [http://localhost:6006](http://localhost:6006) и сохраните скрин одного трейса как `phoenix-trace-screenshot.png` в эту папку.

## Что видно в UI Phoenix

После запроса к `/chat`, `/features/chat` или CLI `examples/run_tool_call*.py` (DeepSeek/Ollama/OpenAI) в проекте **diploma-fastapi** появляются span'ы вызовов Chat Completions. Collector endpoint: `http://phoenix:6006/v1/traces` (HTTP) или `http://phoenix:4317` (gRPC).

Для CLI с хоста: `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces`.  
Для `docker compose run app ...`: `http://phoenix:6006/v1/traces` (уже в `compose.yaml`).

| Поле | Значение |
|------|----------|
| `gen_ai.request.model` | модель из запроса, напр. `gpt-4o-mini` |
| `gen_ai.usage.input_tokens` | prompt tokens из ответа провайдера |
| `gen_ai.usage.output_tokens` | completion tokens |
| `input.value` | JSON сообщений (user/system) — без сырого промпта в application-логах |
| `output.value` | текст ответа модели |
| Latency | длительность span в миллисекундах |

Связка с JSON-логами сервиса — поле `request_id` в structlog и заголовок `X-Request-ID` в HTTP-ответе.

## JSON-лог `llm_request_completed`

Пример строки (без PII):

```json
{
  "event": "llm_request_completed",
  "request_id": "a1b2c3d4e5f6",
  "model": "gpt-4o-mini",
  "input_tokens": 10,
  "output_tokens": 5,
  "latency_ms": 842.15,
  "finish_reason": "stop",
  "prompt_hash": "3f2a1b9c8d7e6f5a",
  "prompt_preview": "Мой email [EMAIL], тел [PHONE_RU], карта [CARD]"
}
```

Сырой промпт в логи не попадает — только `prompt_hash` и маскированный `prompt_preview` (до 120 символов).

## Presidio (опционально)

Для промптов длиннее 500 символов Presidio запускается в фоне (`asyncio.create_task` + `asyncio.to_thread`). В лог пишется событие `presidio_redact_completed` с полем `presidio_latency_ms` — по нему можно оценить накладные расходы.

Установка в Docker (Python 3.13):

```bash
pip install presidio-analyzer presidio-anonymizer
python -m spacy download ru_core_news_md
```
