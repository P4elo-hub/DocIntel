#### Метрики — Переводы между счетами

### Технические метрики

| Название метрики (Prometheus) | Тип | Описание | Labels |
|-------------------------------|-----|----------|--------|
| `transfer_requests_total` | Counter | Общее количество запросов на перевод | method, endpoint, status |
| `transfer_request_duration_seconds` | Histogram | Время обработки запроса на перевод | method, endpoint |
| `transfer_active_requests` | Gauge | Текущие активные запросы на перевод | method |
| `transfer_saga_step_duration_seconds` | Histogram | Время выполнения шага Saga | step_name, status |
| `transfer_db_connections` | Gauge | Число активных соединений с БД для операций перевода | db_name, pool, stand |

### Метрики ошибок

| Название метрики (Prometheus) | Тип | Описание |
|-------------------------------|-----|----------|
| `transfer_failures_total` | Counter | Общее количество неуспешных переводов |
| `transfer_compensation_total` | Counter | Количество запущенных компенсаций (rollback) |
| `transfer_compensation_failures_total` | Counter | Количество неуспешных компенсаций |
| `aml_check_failures_total` | Counter | Количество сбоев AML-проверки |
| `aml_circuit_breaker_open_total` | Counter | Количество срабатываний Circuit Breaker для Compliance |
| `cache_transfer_failures_total` | Counter | Количество сбоев при записи в Redis |
| `transfer_timeout_total` | Counter | Количество переводов, превысивших Global Timeout |

### Бизнес-метрики

| Название метрики (Prometheus) | Тип | Описание | Формула расчёта |
|-------------------------------|-----|----------|-----------------|
| `transfer_success_rate` | Gauge | Конверсия переводов | `successful_transfers / total_transfers * 100%` |
| `transfer_amount_total` | Counter | Суммарный объём переводов (₽) | `sum(transfer.amount)` |
| `transfer_avg_amount` | Gauge | Средний чек перевода | `transfer_amount_total / successful_transfers` |
| `transfer_2fa_rate` | Gauge | Доля переводов с 2FA-подтверждением | `transfers_with_2fa / total_transfers * 100%` |

### Фронтовые метрики

| № | Название события | Параметры | Описание события |
|---|-----------------|-----------|-----------------|
| 1 | Transfer CreateScreen Click | TypeOperation · Тип перевода · Из поля `transfer.type` | Клик на кнопку «Перевести» на экране создания перевода |
| 2 | Transfer ConfirmScreen Complete | TypeOperation · Тип перевода · Из поля `transfer.type` | Экран подтверждения: перевод отправлен |
|   |   | Event_duration · Время от нажатия «Подтвердить» до результата. Интервалы: `"0-100"`, ..., `">5000"` (мс) · Таймер UI | |
| 3 | Transfer ResultScreen Error Show | TypeOperation · Тип перевода · Из поля `transfer.type` | Показ ошибки на экране результата |
|   |   | ErrorType · Код ошибки: `1` — 400, `2` — 401, `3` — 403, `6` — 500, `7` — 503, `100` — timeout, `101` — нет сети, `Other` — прочее · HTTP status / системная ошибка | |
