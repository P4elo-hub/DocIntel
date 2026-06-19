#### Пример: Событие PaymentCompleted (Kafka) (согласно стандартам СТД-ИНТ-01, СТД-АСИНХ-01-03, СТД-АСИНХ-ПАР-01-10, СТД-АСИНХ-ЗАГОЛ-01)

**Общая информация (СТД-ИНТ-01, СТД-АСИНХ-01):**
| Параметр | Значение |
|----------|----------|
| Назначение | Уведомление о завершении платежа по заказу |
| Система-источник | Payment Service |
| Система-получатель | Order Service, Notification Service, Analytics Service |
| Тип интеграции | Асинхронная |
| Протокол | Kafka |
| Направление | Однонаправленная (pub/sub) |
| Topic | payments.completed |
| Partition Key | orderId |
| Число партиций | 12 |
| Replication Factor | 3 |
| Retention | 7 days |
| Гарантия доставки | At-least-once |
| Формат сериализации | JSON (Schema Registry) |
| Версия схемы | 1.0 |
| Стратегия совместимости | BACKWARD |

**Consumer информация (СТД-АСИНХ-03):**
| Consumer | Consumer Group | Retry Policy | DLQ Topic | Идемпотентность |
|----------|---------------|--------------|-----------|-----------------|
| Order Service | order-service-payments | 3 retries, exponential backoff (1s, 5s, 30s) | payments.completed.order.dlq | По orderId + paymentId |
| Notification Service | notification-service-payments | 5 retries, fixed delay 2s | payments.completed.notify.dlq | По messageId |
| Analytics Service | analytics-service-payments | Без retry (best-effort) | — | Дедупликация по paymentId |

**Kafka Headers (СТД-АСИНХ-ЗАГОЛ-01):**
| Header Key | Обязат. | Описание | Пример |
|------------|---------|----------|--------|
| X-Message-Id | Да | UUID сообщения | 550e8400-e29b-41d4-a716-446655440000 |
| X-Correlation-Id | Да | ID для трассировки (distributed tracing) | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |
| X-Event-Type | Да | Тип события (роутинг без десериализации) | PaymentCompleted |
| X-Schema-Version | Да | Версия схемы сообщения | 1.0 |
| X-Source | Да | Сервис-источник | payment-service |
| X-Timestamp | Нет | Время отправки (ISO 8601) | 2026-02-04T14:25:00Z |
| content-type | Да | Формат сериализации | application/json |

**Структура Envelope (СТД-АСИНХ-ПАР-05):**
```json
{
  "metadata": {
    "messageId": "550e8400-e29b-41d4-a716-446655440000",
    "correlationId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "timestamp": "2026-02-04T14:25:00Z",
    "eventType": "PaymentCompleted",
    "version": "1.0",
    "source": "payment-service"
  },
  "payload": {
    // Бизнес-данные (см. таблицу параметров ниже)
  }
}
```

**Параметры metadata (СТД-АСИНХ-ПАР-01, СТД-АСИНХ-ПАР-05, СТД-АСИНХ-ПАР-08):**
| Параметр | Тип | Обязат. | Описание | Валидация | По умолч. | Пример |
|----------|-----|---------|----------|-----------|-----------|--------|
| messageId | string | Да | UUID сообщения | minLength: 36, maxLength: 36, format: uuid | — | 550e8400-e29b-41d4-a716-446655440000 |
| correlationId | string | Да | ID для трассировки | minLength: 36, maxLength: 36, format: uuid | — | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |
| timestamp | string | Да | Время создания | format: date-time | — | 2026-02-04T14:25:00Z |
| eventType | string | Да | Тип события | enum: [PaymentCompleted, PaymentFailed, PaymentRefunded] | — | PaymentCompleted |
| version | string | Да | Версия схемы | pattern: `^\d+\.\d+$` | — | 1.0 |
| source | string | Да | Сервис-источник | minLength: 1, maxLength: 100 | — | payment-service |

**Параметры payload (СТД-АСИНХ-ПАР-01, СТД-АСИНХ-ПАР-04, СТД-АСИНХ-ПАР-08):**
| Параметр | Тип | Обязат. | Описание | Валидация | По умолч. | Пример | Маппинг |
|----------|-----|---------|----------|-----------|-----------|--------|---------|
| paymentId | string | Да | UUID платежа | minLength: 36, maxLength: 36, format: uuid | — | pay-a1b2c3d4-... | Payment DB → payment_id |
| orderId | string | Да | UUID заказа (partition key) | minLength: 36, maxLength: 36, format: uuid | — | ord-e5f6a7b8-... | Payment DB → order_id |
| customerId | string | Да | UUID клиента | minLength: 36, maxLength: 36, format: uuid | — | cust-11223344-... | Payment DB → customer_id |
| amount | object | Да | Сумма платежа | required: [value, currency] | — | {...} | Payment DB → amount |
| ├─ value | number | Да | Сумма | minimum: 0.01, maximum: 99999999.99 | — | 15000.50 | Payment DB → amount_value |
| └─ currency | string | Да | Валюта ISO 4217 | minLength: 3, maxLength: 3, pattern: `^[A-Z]{3}$` | — | RUB | Payment DB → currency_code |
| paymentMethod | string | Да | Способ оплаты | enum: [CARD, SBP, BANK_TRANSFER, WALLET] | — | CARD | Payment DB → payment_method |
| cardInfo | object | Условно* | Информация о карте | required: [maskedPan, bankName] | null | {...} | Payment DB → card_info |
| ├─ maskedPan | string | Да | Маскированный номер | pattern: `^\*{4}\d{4}$`, maxLength: 8 | — | ****1234 | Payment DB → masked_pan |
| └─ bankName | string | Да | Банк-эмитент | minLength: 1, maxLength: 200 | — | Сбербанк | Payment DB → card_bank_name |
| sbpInfo | object | Условно* | Информация о СБП | required: [bankId, phoneLastDigits] | null | {...} | Payment DB → sbp_info |
| ├─ bankId | string | Да | БИК банка | pattern: `^\d{9}$`, minLength: 9, maxLength: 9 | — | 044525225 | Payment DB → sbp_bank_id |
| └─ phoneLastDigits | string | Да | Последние 4 цифры телефона | pattern: `^\d{4}$`, minLength: 4, maxLength: 4 | — | 7890 | Payment DB → sbp_phone_last |
| items | array | Да | Оплаченные позиции | minItems: 1, maxItems: 100, uniqueItems: false | — | [...] | Order DB → order_items |
| ├─ productId | string | Да | UUID товара | minLength: 36, maxLength: 36, format: uuid | — | prod-99887766-... | Order DB → product_id |
| ├─ name | string | Да | Наименование товара | minLength: 1, maxLength: 500 | — | Смартфон Samsung Galaxy | Product DB → product_name |
| ├─ quantity | integer | Да | Количество | minimum: 1, maximum: 9999 | — | 1 | Order DB → quantity |
| └─ price | number | Да | Цена за единицу | minimum: 0.01, maximum: 99999999.99 | — | 15000.50 | Order DB → item_price |
| paidAt | string | Да | Дата/время оплаты | format: date-time | — | 2026-02-04T14:25:00Z | Payment DB → paid_at |
| externalTransactionId | string | Нет | ID транзакции платёжного шлюза | maxLength: 256 | null | pg-txn-9876543210 | Payment Gateway → txn_id |

**Условия обязательности (СТД-АСИНХ-ПАР-02):**
| Параметр | Условие обязательности |
|----------|------------------------|
| cardInfo | Обязателен, если paymentMethod = "CARD" |
| sbpInfo | Обязателен, если paymentMethod = "SBP" |

**Enum: eventType (СТД-АСИНХ-ПАР-03):**
| Значение | Описание | Когда публикуется |
|----------|----------|-------------------|
| PaymentCompleted | Платёж успешно завершён | Подтверждение от платёжного шлюза |
| PaymentFailed | Платёж отклонён | Отказ шлюза / недостаточно средств |
| PaymentRefunded | Платёж возвращён | Возврат по заявке клиента / автоматический |

**Enum: paymentMethod (СТД-АСИНХ-ПАР-03):**
| Значение | Описание | Когда использовать |
|----------|----------|-------------------|
| CARD | Банковская карта | Visa, Mastercard, МИР |
| SBP | Система быстрых платежей | Оплата по QR / номеру телефона |
| BANK_TRANSFER | Банковский перевод | Платёжное поручение |
| WALLET | Электронный кошелёк | Внутренний баланс / ЮMoney / WebMoney |

**Ключ партиционирования (СТД-АСИНХ-ПАР-07):**
| Поле | Тип | Описание | Влияние на порядок |
|------|-----|----------|-------------------|
| orderId | string (UUID) | ID заказа | Все события одного заказа попадают в одну партицию — гарантирован порядок обработки по заказу |

**JSON Schema (СТД-АСИНХ-ПАР-09):**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PaymentCompletedEvent",
  "description": "Событие завершения платежа по заказу",
  "type": "object",
  "required": ["metadata", "payload"],
  "additionalProperties": false,
  "properties": {
    "metadata": {
      "type": "object",
      "required": ["messageId", "correlationId", "timestamp", "eventType", "version", "source"],
      "additionalProperties": false,
      "properties": {
        "messageId": { "type": "string", "format": "uuid", "minLength": 36, "maxLength": 36 },
        "correlationId": { "type": "string", "format": "uuid", "minLength": 36, "maxLength": 36 },
        "timestamp": { "type": "string", "format": "date-time" },
        "eventType": { "type": "string", "enum": ["PaymentCompleted", "PaymentFailed", "PaymentRefunded"] },
        "version": { "type": "string", "pattern": "^\\d+\\.\\d+$" },
        "source": { "type": "string", "minLength": 1, "maxLength": 100 }
      }
    },
    "payload": {
      "type": "object",
      "required": ["paymentId", "orderId", "customerId", "amount", "paymentMethod", "items", "paidAt"],
      "additionalProperties": false,
      "properties": {
        "paymentId": { "type": "string", "format": "uuid", "minLength": 36, "maxLength": 36 },
        "orderId": { "type": "string", "format": "uuid", "minLength": 36, "maxLength": 36 },
        "customerId": { "type": "string", "format": "uuid", "minLength": 36, "maxLength": 36 },
        "amount": {
          "type": "object",
          "required": ["value", "currency"],
          "properties": {
            "value": { "type": "number", "minimum": 0.01, "maximum": 99999999.99 },
            "currency": { "type": "string", "minLength": 3, "maxLength": 3, "pattern": "^[A-Z]{3}$" }
          }
        },
        "paymentMethod": { "type": "string", "enum": ["CARD", "SBP", "BANK_TRANSFER", "WALLET"] },
        "cardInfo": {
          "type": ["object", "null"],
          "required": ["maskedPan", "bankName"],
          "properties": {
            "maskedPan": { "type": "string", "pattern": "^\\*{4}\\d{4}$", "maxLength": 8 },
            "bankName": { "type": "string", "minLength": 1, "maxLength": 200 }
          }
        },
        "sbpInfo": {
          "type": ["object", "null"],
          "required": ["bankId", "phoneLastDigits"],
          "properties": {
            "bankId": { "type": "string", "pattern": "^\\d{9}$", "minLength": 9, "maxLength": 9 },
            "phoneLastDigits": { "type": "string", "pattern": "^\\d{4}$", "minLength": 4, "maxLength": 4 }
          }
        },
        "items": {
          "type": "array",
          "minItems": 1,
          "maxItems": 100,
          "items": {
            "type": "object",
            "required": ["productId", "name", "quantity", "price"],
            "properties": {
              "productId": { "type": "string", "format": "uuid", "minLength": 36, "maxLength": 36 },
              "name": { "type": "string", "minLength": 1, "maxLength": 500 },
              "quantity": { "type": "integer", "minimum": 1, "maximum": 9999 },
              "price": { "type": "number", "minimum": 0.01, "maximum": 99999999.99 }
            }
          }
        },
        "paidAt": { "type": "string", "format": "date-time" },
        "externalTransactionId": { "type": ["string", "null"], "maxLength": 256 },
        "error": {
          "type": ["object", "null"],
          "description": "Объект ошибки (только для eventType = PaymentFailed)",
          "required": ["code", "message", "retriable"],
          "properties": {
            "code": {
              "type": "string",
              "description": "Код ошибки",
              "enum": ["INSUFFICIENT_FUNDS", "CARD_EXPIRED", "CARD_BLOCKED", "GATEWAY_TIMEOUT", "GATEWAY_ERROR", "FRAUD_SUSPECTED", "3DS_FAILED", "LIMIT_EXCEEDED"]
            },
            "message": {
              "type": "string",
              "description": "Человекочитаемое описание ошибки",
              "minLength": 1,
              "maxLength": 500
            },
            "gatewayCode": {
              "type": ["string", "null"],
              "description": "Код ошибки от платёжного шлюза",
              "maxLength": 20
            },
            "retriable": {
              "type": "boolean",
              "description": "Можно ли повторить платёж"
            }
          }
        },
        "attemptNumber": {
          "type": ["integer", "null"],
          "description": "Номер попытки оплаты (только для PaymentFailed)",
          "minimum": 1,
          "maximum": 10
        },
        "failedAt": {
          "type": ["string", "null"],
          "description": "Дата/время ошибки (только для PaymentFailed)",
          "format": "date-time"
        },
        "originalAmount": {
          "type": ["object", "null"],
          "description": "Исходная сумма платежа (только для PaymentRefunded)",
          "required": ["value", "currency"],
          "properties": {
            "value": { "type": "number", "minimum": 0.01, "maximum": 99999999.99 },
            "currency": { "type": "string", "minLength": 3, "maxLength": 3, "pattern": "^[A-Z]{3}$" }
          }
        },
        "refundAmount": {
          "type": ["object", "null"],
          "description": "Сумма возврата (только для PaymentRefunded)",
          "required": ["value", "currency"],
          "properties": {
            "value": { "type": "number", "minimum": 0.01, "maximum": 99999999.99 },
            "currency": { "type": "string", "minLength": 3, "maxLength": 3, "pattern": "^[A-Z]{3}$" }
          }
        },
        "refundType": {
          "type": ["string", "null"],
          "description": "Тип возврата (только для PaymentRefunded)",
          "enum": ["FULL", "PARTIAL"]
        },
        "reason": {
          "type": ["string", "null"],
          "description": "Причина возврата (только для PaymentRefunded)",
          "maxLength": 500
        },
        "refundedAt": {
          "type": ["string", "null"],
          "description": "Дата/время возврата (только для PaymentRefunded)",
          "format": "date-time"
        },
        "externalRefundId": {
          "type": ["string", "null"],
          "description": "ID возврата от платёжного шлюза",
          "maxLength": 256
        }
      }
    }
  }
}
```

**Happy Path (СТД-АСИНХ-ПАР-06):**
```
Topic: payments.completed
Key: ord-e5f6a7b8-c9d0-1234-5678-abcdef012345
Headers: X-Message-Id=550e8400-..., X-Event-Type=PaymentCompleted, 
         X-Schema-Version=1.0, X-Source=payment-service, content-type=application/json
```
```json
{
  "metadata": {
    "messageId": "550e8400-e29b-41d4-a716-446655440000",
    "correlationId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "timestamp": "2026-02-04T14:25:00Z",
    "eventType": "PaymentCompleted",
    "version": "1.0",
    "source": "payment-service"
  },
  "payload": {
    "paymentId": "pay-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "orderId": "ord-e5f6a7b8-c9d0-1234-5678-abcdef012345",
    "customerId": "cust-11223344-5566-7788-99aa-bbccddeeff00",
    "amount": {
      "value": 15000.50,
      "currency": "RUB"
    },
    "paymentMethod": "CARD",
    "cardInfo": {
      "maskedPan": "****1234",
      "bankName": "Сбербанк"
    },
    "sbpInfo": null,
    "items": [
      {
        "productId": "prod-99887766-5544-3322-1100-aabbccddeeff",
        "name": "Смартфон Samsung Galaxy S24",
        "quantity": 1,
        "price": 15000.50
      }
    ],
    "paidAt": "2026-02-04T14:25:00Z",
    "externalTransactionId": "pg-txn-9876543210"
  }
}
```

**Пограничный случай: Оплата через СБП с несколькими товарами (СТД-АСИНХ-ПАР-06):**
```
Topic: payments.completed
Key: ord-aaaabbbb-cccc-dddd-eeee-ffffffffffff
```
```json
{
  "metadata": {
    "messageId": "661f9511-f3ac-52e5-b827-557766551111",
    "correlationId": "8d0f7780-8536-51ef-055c-f18fd2f91bf8",
    "timestamp": "2026-02-04T16:00:00Z",
    "eventType": "PaymentCompleted",
    "version": "1.0",
    "source": "payment-service"
  },
  "payload": {
    "paymentId": "pay-bbccddee-ff00-1122-3344-556677889900",
    "orderId": "ord-aaaabbbb-cccc-dddd-eeee-ffffffffffff",
    "customerId": "cust-00112233-4455-6677-8899-aabbccddeeff",
    "amount": {
      "value": 42350.00,
      "currency": "RUB"
    },
    "paymentMethod": "SBP",
    "cardInfo": null,
    "sbpInfo": {
      "bankId": "044525225",
      "phoneLastDigits": "7890"
    },
    "items": [
      {
        "productId": "prod-11112222-3333-4444-5555-666677778888",
        "name": "Наушники Sony WH-1000XM5",
        "quantity": 1,
        "price": 29990.00
      },
      {
        "productId": "prod-aaaabbbb-cccc-dddd-eeee-111122223333",
        "name": "Чехол для наушников",
        "quantity": 2,
        "price": 6180.00
      }
    ],
    "paidAt": "2026-02-04T16:00:00Z",
    "externalTransactionId": null
  }
}
```
> **Примечание:** При оплате через СБП — `cardInfo = null`, `sbpInfo` обязателен. При отсутствии внешнего ID платёжного шлюза — `externalTransactionId = null`.

**Ошибочное событие: PaymentFailed (СТД-АСИНХ-ПАР-06):**
```
Topic: payments.completed
Key: ord-ff001122-3344-5566-7788-99aabbccddee
Headers: X-Event-Type=PaymentFailed
```
```json
{
  "metadata": {
    "messageId": "772a0622-d4be-63f6-c938-668877665544",
    "correlationId": "9e1f8891-9647-62f0-166d-g29ge3g02cg9",
    "timestamp": "2026-02-04T18:15:30Z",
    "eventType": "PaymentFailed",
    "version": "1.0",
    "source": "payment-service"
  },
  "payload": {
    "paymentId": "pay-ddeeff00-1122-3344-5566-778899aabb00",
    "orderId": "ord-ff001122-3344-5566-7788-99aabbccddee",
    "customerId": "cust-aabbccdd-eeff-0011-2233-445566778899",
    "amount": {
      "value": 89990.00,
      "currency": "RUB"
    },
    "paymentMethod": "CARD",
    "cardInfo": {
      "maskedPan": "****5678",
      "bankName": "Тинькофф"
    },
    "sbpInfo": null,
    "error": {
      "code": "INSUFFICIENT_FUNDS",
      "message": "Недостаточно средств на карте",
      "gatewayCode": "51",
      "retriable": false
    },
    "attemptNumber": 1,
    "failedAt": "2026-02-04T18:15:30Z"
  }
}
```
> **Примечание:** При `eventType = "PaymentFailed"` в payload добавляются дополнительные поля: `error` (объект с кодом и описанием ошибки), `attemptNumber` (номер попытки), `failedAt` (время ошибки). Поля `items` и `paidAt` отсутствуют.

**Enum: error.code (СТД-АСИНХ-ПАР-03):**
| Значение | Описание | retriable |
|----------|----------|-----------|
| INSUFFICIENT_FUNDS | Недостаточно средств | false |
| CARD_EXPIRED | Карта просрочена | false |
| CARD_BLOCKED | Карта заблокирована | false |
| GATEWAY_TIMEOUT | Таймаут платёжного шлюза | true |
| GATEWAY_ERROR | Внутренняя ошибка шлюза | true |
| FRAUD_SUSPECTED | Подозрение на мошенничество | false |
| 3DS_FAILED | Не пройдена 3D-Secure верификация | false |
| LIMIT_EXCEEDED | Превышен лимит на операции | false |

**Ошибочное событие: PaymentRefunded (СТД-АСИНХ-ПАР-06):**
```
Topic: payments.completed
Key: ord-e5f6a7b8-c9d0-1234-5678-abcdef012345
Headers: X-Event-Type=PaymentRefunded
```
```json
{
  "metadata": {
    "messageId": "883b1733-e5cf-74g7-d049-779988776655",
    "correlationId": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "timestamp": "2026-02-05T09:00:00Z",
    "eventType": "PaymentRefunded",
    "version": "1.0",
    "source": "payment-service"
  },
  "payload": {
    "paymentId": "pay-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "orderId": "ord-e5f6a7b8-c9d0-1234-5678-abcdef012345",
    "customerId": "cust-11223344-5566-7788-99aa-bbccddeeff00",
    "originalAmount": {
      "value": 15000.50,
      "currency": "RUB"
    },
    "refundAmount": {
      "value": 15000.50,
      "currency": "RUB"
    },
    "refundType": "FULL",
    "reason": "CLIENT_REQUEST",
    "refundedAt": "2026-02-05T09:00:00Z",
    "externalRefundId": "pg-rfnd-1234567890"
  }
}
```
> **Примечание:** При `eventType = "PaymentRefunded"` структура payload отличается: содержит `originalAmount`, `refundAmount`, `refundType` (FULL / PARTIAL), `reason` и `refundedAt`.

**Обработка ошибок (сводная таблица):**
| Ошибка | Обработка | Действие consumer |
|--------|-----------|-------------------|
| Невалидная схема (JSON Schema validation failed) | Отправка в DLQ | Логирование + alert, ручной разбор |
| Дубликат messageId | Идемпотентная обработка | Skip (уже обработано) |
| Order не найден (orderId не существует) | Retry с backoff | 3 попытки, затем DLQ |
| Таймаут обработки | Retry с backoff | Повтор + commit offset только при успехе |
| Ошибка сериализации / десериализации | Отправка в DLQ | Poison pill — немедленно в DLQ |

### 4.8. Документирование API
- **СТД-API-DOC-01**: Для каждого endpoint предоставлять:
  - Описание назначения
  - Таблицу входных параметров
  - Таблицу выходных параметров
  - Примеры запросов и ответов
  - Коды ошибок

- **СТД-API-DOC-02**: Использовать OpenAPI 3.0 спецификацию для REST API
- **СТД-API-DOC-03**: Swagger/Redoc документация должна быть актуальной

- **СТД-API-DOC-04**: JSON Schema обязательна для всех запросов и ответов:
  ```json
  {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "CreateOrderRequest",
    "description": "Запрос на создание заказа",
    "required": ["userId", "items"],
    "properties": {
      "userId": {
        "type": "string",
        "format": "uuid",
        "description": "Идентификатор пользователя"
      },
      "items": {
        "type": "array",
        "minItems": 1,
        "items": {
          "$ref": "#/$defs/OrderItem"
        }
      }
    },
    "$defs": {
      "OrderItem": {
        "type": "object",
        "required": ["productId", "quantity"],
        "properties": {
          "productId": {
            "type": "string",
            "description": "ID товара"
          },
          "quantity": {
            "type": "integer",
            "minimum": 1,
            "description": "Количество"
          }
        }
      }
    }
  }
  ```

- **СТД-API-DOC-05**: JSON Schema должна включать:
  | Элемент | Обязательность | Описание |
  |---------|----------------|----------|
  | $schema | Рекомендуется | Версия JSON Schema |
  | title | Обязательно | Название схемы |
  | description | Обязательно | Описание назначения |
  | type | Обязательно | Тип данных |
  | required | Обязательно | Список обязательных полей |
  | properties | Обязательно | Описание полей |
  | $defs | При необходимости | Переиспользуемые определения |

- **СТД-API-DOC-06**: Валидационные ключевые слова JSON Schema:
  | Тип | Ключевые слова |
  |-----|----------------|
  | string | minLength, maxLength, pattern, format, enum |
  | number/integer | minimum, maximum, exclusiveMinimum, exclusiveMaximum, multipleOf |
  | array | minItems, maxItems, uniqueItems, items |
  | object | required, properties, additionalProperties, minProperties, maxProperties |

- **СТД-API-DOC-07**: Стандартные форматы для string:
  | Формат | Описание | Пример |
  |--------|----------|--------|
  | date-time | ISO 8601 дата-время | 2024-01-01T00:00:00Z |
  | date | ISO 8601 дата | 2024-01-01 |
  | time | ISO 8601 время | 00:00:00Z |
  | email | RFC 5322 email | user@example.com |
  | uuid | RFC 4122 UUID | 123e4567-e89b-12d3-a456-426614174000 |
  | uri | RFC 3986 URI | https://example.com |

- **СТД-API-DOC-08**: Для асинхронных API использовать AsyncAPI спецификацию
- **СТД-API-DOC-09**: Для gRPC предоставлять .proto файлы и сгенерированную документацию
- **СТД-API-DOC-10**: Для GraphQL предоставлять SDL схему и GraphQL Playground/GraphiQL

### 4.9. Примеры запросов и ответов
- **СТД-ПРИМ-01**: Обязательно предоставлять примеры для:
  - Успешного сценария (happy path)
  - Каждого значимого ошибочного сценария
  - Пограничных случаев (boundary cases)

- **СТД-ПРИМ-02**: Примеры должны быть реальными, а не абстрактными:
  | Плохо | Хорошо |
  |-------|--------|
  | `"name": "string"` | `"name": "Иван Петров"` |
  | `"email": "email@email.com"` | `"email": "ivan.petrov@company.ru"` |
  | `"amount": 0` | `"amount": 15000.50` |
  | `"date": "date"` | `"date": "2024-03-15T14:30:00Z"` |

- **СТД-ПРИМ-03**: В примерах использовать реалистичные данные:
  - Валидные UUID (не "12345" или "xxx")
  - Реалистичные имена и email
  - Правдоподобные числовые значения
  - Корректные даты в формате ISO 8601

- **СТД-ПРИМ-04**: Примеры ошибочных ответов должны содержать корректные коды ошибок:
  ```json
  // Пример ошибки валидации (400)
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Поле email имеет неверный формат",
      "details": [
        {
          "field": "email",
          "reason": "invalid_format",
          "value": "invalid-email"
        }
      ],
      "timestamp": "2024-03-15T14:30:00Z",
      "traceId": "abc123-def456"
    }
  }
  ```

- **СТД-ПРИМ-05**: Для каждого примера указывать контекст:
  | Сценарий | Описание | HTTP код | Условие |
  |----------|----------|----------|---------|
  | Happy path | Успешное создание заказа | 201 | Все данные валидны |
  | Ошибка валидации | Невалидный email | 400 | email не соответствует формату |
  | Бизнес-ошибка | Недостаточно средств | 422 | balance < amount |
  | Пограничный случай | Пустой массив товаров | 400 | items.length = 0 |

### 4.10. Сценарии взаимодействия
- **СТД-СЦЕН-01**: Описывать последовательность вызовов в виде Sequence Diagram
- **СТД-СЦЕН-02**: Для каждого шага взаимодействия указывать:
  | Параметр | Описание | Обязательность |
  |----------|----------|----------------|
  | Инициатор | Система/компонент, инициирующий вызов | Обязательно |
  | Получатель | Система/компонент, обрабатывающий запрос | Обязательно |
  | Метод/операция | Название вызываемого метода или endpoint | Обязательно |
  | Данные запроса | Ключевые параметры запроса | Обязательно |
  | Ожидаемый ответ | Структура успешного ответа | Обязательно |
  | Таймаут | Максимальное время ожидания ответа | Обязательно |
  | Retry стратегия | Политика повторных попыток | Обязательно |

- **СТД-СЦЕН-03**: Обработка таймаутов:
  | Параметр | Описание | Пример |
  |----------|----------|--------|
  | Connection timeout | Время на установку соединения | 5 секунд |
  | Read timeout | Время на получение ответа | 30 секунд |
  | Действие при таймауте | Что делать при превышении | Retry / Fallback / Error |

- **СТД-СЦЕН-04**: Стратегия повторных попыток (Retry Policy):
  | Параметр | Описание | Пример |
  |----------|----------|--------|
  | Количество попыток | Максимальное число retry | 3 |
  | Интервал между попытками | Задержка перед повтором | Exponential backoff: 1s, 2s, 4s |
  | Retryable ошибки | Коды ошибок для retry | 503, 504, ETIMEDOUT |
  | Non-retryable ошибки | Коды без retry | 400, 401, 403, 404 |

- **СТД-СЦЕН-05**: Пример описания шага взаимодействия:
  ```
  Шаг 3: Запрос данных пользователя
  ├── Инициатор: Order Service
  ├── Получатель: User Service
  ├── Метод: GET /api/v1/users/{userId}
  ├── Данные запроса: userId = "uuid"
  ├── Ожидаемый ответ: { user: { id, name, email } }
  ├── Таймаут: 5 секунд
  ├── Retry: 3 попытки, exponential backoff (1s, 2s, 4s)
  └── Fallback: Использовать кэшированные данные
  ```

---
