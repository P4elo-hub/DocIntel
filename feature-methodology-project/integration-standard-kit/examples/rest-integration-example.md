#### Пример REST API endpoint (согласно стандартам СТД-ИНТ-01-03, СТД-СИНХ-ПАР-01-09, СТД-ЗАГОЛ-01-02, СТД-REST-01-04)

```
GET /api/v1/accounts/{accountId}/transactions
```

**Общая информация (СТД-ИНТ-01):**
| Параметр | Значение |
|----------|----------|
| Назначение | Получение истории транзакций по счёту |
| Система-источник | Mobile App / Web App (BFF) |
| Система-получатель | Account Transaction Service |
| Тип интеграции | Синхронная |
| Протокол | REST (HTTPS) |
| Направление | Однонаправленная (Request → Response) |
| Версия API | v1 |
| Аутентификация | Bearer Token (JWT) |
| Формат данных | JSON |
| Rate Limit | 100 req/min per client |
| Timeout | 30 секунд |
| Retry Policy | 3 попытки с exponential backoff |

**Request Headers (СТД-ЗАГОЛ-01):**
| Заголовок | Обязат. | Описание | Пример |
|-----------|---------|----------|--------|
| Authorization | Да | Bearer JWT токен | Bearer eyJ... |
| Accept | Да | Ожидаемый формат | application/json |
| X-Request-ID | Да | UUID для трассировки | 550e8400-... |
| X-Client-ID | Да | Идентификатор клиента | mobile-app |

**Path Parameters (СТД-СИНХ-ПАР-01, СТД-СИНХ-ПАР-08):**
| Параметр | Тип | Обязат. | Описание | Валидация | Пример |
|----------|-----|---------|----------|-----------|--------|
| accountId | string | Да | UUID счёта клиента | minLength: 36, maxLength: 36, pattern: `^[0-9a-f]{8}-...$`, format: uuid | 550e8400-e29b-41d4-a716-446655440000 |

**Query Parameters (СТД-СИНХ-ПАР-01, СТД-СИНХ-ПАР-02, СТД-СИНХ-ПАР-08):**
| Параметр | Тип | Обязат. | Описание | Валидация | По умолч. | Пример |
|----------|-----|---------|----------|-----------|-----------|--------|
| dateFrom | string | Да | Начало периода | minLength: 10, maxLength: 10, format: date | — | 2026-01-01 |
| dateTo | string | Да | Конец периода | minLength: 10, maxLength: 10, format: date | — | 2026-01-31 |
| type | string | Нет | Тип транзакции | enum: [DEPOSIT, WITHDRAWAL, ...] | — | DEPOSIT |
| status | string | Нет | Статус | enum: [PENDING, COMPLETED, ...] | — | COMPLETED |
| page | integer | Нет | Номер страницы | minimum: 1, maximum: 1000 | 1 | 1 |
| pageSize | integer | Нет | Размер страницы | minimum: 1, maximum: 100 | 20 | 50 |

**ENUM: type (СТД-СИНХ-ПАР-03):**
| Значение | Описание |
|----------|----------|
| DEPOSIT | Пополнение счёта |
| WITHDRAWAL | Вывод средств |
| TRANSFER_IN | Входящий перевод |
| TRANSFER_OUT | Исходящий перевод |
| FEE | Комиссия |
| REFUND | Возврат средств |

**Response Headers (СТД-ЗАГОЛ-02):**
| Заголовок | Описание | Пример |
|-----------|----------|--------|
| X-Request-ID | Echo request ID | 550e8400-... |
| X-RateLimit-Limit | Лимит запросов | 100 |
| X-RateLimit-Remaining | Осталось запросов | 95 |
| X-Total-Count | Всего записей | 156 |

**Response Body 200 OK (СТД-СИНХ-ПАР-05, СТД-СИНХ-ПАР-04, СТД-СИНХ-ПАР-08):**
| Параметр | Тип | Формат | Nullable | Описание | Валидация | По умолч. | Пример | Маппинг |
|----------|-----|--------|----------|----------|-----------|-----------|--------|---------|
| data | array | — | Нет | Массив транзакций | minItems: 0, maxItems: 100 | — | [] | — |
| ├─ transactionId | string | UUID | Нет | UUID транзакции | minLength: 36, maxLength: 36, format: uuid | — | txn-a1b2c3... | Transaction DB → txn_id |
| ├─ type | string | enum | Нет | Тип транзакции | enum: [DEPOSIT, WITHDRAWAL, ...] | — | DEPOSIT | Transaction DB → txn_type_code |
| ├─ status | string | enum | Нет | Статус | enum: [PENDING, COMPLETED, ...] | — | COMPLETED | Transaction DB → txn_status |
| ├─ amount | number | decimal | Нет | Сумма | minimum: 0 | — | 50000.00 | Transaction DB → amount_cents / 100 |
| ├─ currency | string | ISO 4217 | Нет | Валюта | minLength: 3, maxLength: 3, pattern: `^[A-Z]{3}$` | — | RUB | Transaction DB → currency_code |
| ├─ description | string | — | Да | Описание | maxLength: 500 | null | Пополнение... | Transaction DB → description |
| ├─ counterparty | object | — | Да | Контрагент | required: [name, accountMask] | null | {...} | Counterparty DB → counterparty |
| ├─ createdAt | string | ISO 8601 | Нет | Дата создания | format: date-time | — | 2026-01-15T10:30:00Z | Transaction DB → created_ts |
| └─ completedAt | string | ISO 8601 | Да | Дата завершения | format: date-time | null | 2026-01-15T10:30:05Z | Transaction DB → completed_ts |
| pagination | object | — | Нет | Пагинация | required: [page, pageSize, totalItems, totalPages] | — | {...} | Вычисляется |
| ├─ page | integer | — | Нет | Текущая страница | minimum: 1 | — | 1 | Query → page |
| ├─ pageSize | integer | — | Нет | Размер страницы | minimum: 1, maximum: 100 | — | 20 | Query → pageSize |
| ├─ totalItems | integer | — | Нет | Всего записей | minimum: 0 | — | 45 | COUNT(*) |
| └─ totalPages | integer | — | Нет | Всего страниц | minimum: 0 | — | 3 | CEIL(total / pageSize) |

**Пример запроса и ответа (СТД-СИНХ-ПАР-06):**
```http
GET /api/v1/accounts/550e8400-e29b-41d4-a716-446655440000/transactions?dateFrom=2026-01-01&dateTo=2026-01-31
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
X-Request-ID: 7c9e6679-7425-40de-944b-e07fc1f90ae7
```

```json
{
  "data": [
    {
      "transactionId": "txn-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "type": "DEPOSIT",
      "status": "COMPLETED",
      "amount": 50000.00,
      "currency": "RUB",
      "description": "Пополнение с карты *1234",
      "counterparty": null,
      "createdAt": "2026-01-15T10:30:00Z",
      "completedAt": "2026-01-15T10:30:05Z"
    }
  ],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 45,
    "totalPages": 3
  }
}
```

**Пограничный случай: Пустой результат (нет транзакций за период):**
```http
GET /api/v1/accounts/550e8400-e29b-41d4-a716-446655440000/transactions?dateFrom=2020-01-01&dateTo=2020-01-31
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
X-Request-ID: 8d0f7780-8536-51ef-055c-f18fd2f91bf8
```

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 0,
    "totalPages": 0
  }
}
```
> **Примечание:** При отсутствии данных возвращается пустой массив `data: []`, а не `null`. Пагинация содержит `totalItems: 0` и `totalPages: 0`.

**Коды ошибок (СТД-REST-03):**
| HTTP код | Код ошибки | Описание |
|----------|------------|----------|
| 400 | INVALID_PARAMETERS | Невалидный формат параметров |
| 401 | UNAUTHORIZED | Отсутствует/невалидный токен |
| 403 | FORBIDDEN | Нет доступа к счёту |
| 404 | ACCOUNT_NOT_FOUND | Счёт не существует |
| 429 | RATE_LIMIT_EXCEEDED | Превышен лимит запросов |
| 500 | INTERNAL_ERROR | Внутренняя ошибка сервера |
