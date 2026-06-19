#### Пример GraphQL Query (согласно стандартам СТД-ИНТ-01, СТД-GQL-01-08, СТД-СИНХ-ПАР-01-09)

**GraphQL Query:** userOrders
**Назначение:** Получение заказов пользователя с фильтрацией и пагинацией

**Общая информация (СТД-ИНТ-01):**
| Параметр | Значение |
|----------|----------|
| Назначение | Получение списка заказов пользователя |
| Система-источник | Mobile App / Web App (SPA) |
| Система-получатель | Order Service (GraphQL Gateway) |
| Тип интеграции | Синхронная |
| Протокол | GraphQL (HTTPS) |
| Направление | Однонаправленная (Query → Response) |
| Тип операции | Query (read-only) |
| Аутентификация | Bearer Token (JWT) |
| Rate Limit | 200 req/min per client |
| Timeout | 15 секунд |
| Retry Policy | 3 попытки с exponential backoff |

**Request Headers (СТД-ЗАГОЛ-01):**

> GraphQL работает поверх HTTP (обычно POST на единый endpoint `/graphql`), поэтому используются стандартные HTTP заголовки.

| Заголовок | Обязат. | Описание | Пример |
|-----------|---------|----------|--------|
| Authorization | Да | Bearer JWT токен | Bearer eyJhbGciOiJSUzI1NiJ9... |
| Content-Type | Да | Тип тела запроса | application/json |
| Accept | Да | Ожидаемый формат ответа | application/json |
| X-Request-ID | Да | UUID для трассировки | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |
| X-Client-ID | Да | Идентификатор клиентского приложения | mobile-app-ios |

**Response Headers (СТД-ЗАГОЛ-02):**
| Заголовок | Описание | Пример |
|-----------|----------|--------|
| X-Request-ID | Echo request ID | 7c9e6679-7425-40de-944b-e07fc1f90ae7 |
| X-RateLimit-Limit | Лимит запросов | 200 |
| X-RateLimit-Remaining | Осталось запросов | 195 |
| Cache-Control | Политика кэширования | no-store |

> **Примечание:** В GraphQL HTTP статус **всегда 200 OK**, даже при ошибках. Ошибки передаются в теле ответа в массиве `errors` (СТД-GQL-05). Поэтому HTTP-заголовки ответа не содержат информации об ошибках бизнес-логики.

**Schema Definition (СТД-GQL-01, СТД-GQL-07):**
```graphql
type Query {
  """Получение заказов пользователя с фильтрацией и пагинацией"""
  userOrders(
    userId: ID!                    # UUID пользователя
    dateFrom: DateTime!            # Начало периода
    dateTo: DateTime!              # Конец периода
    status: OrderStatus            # Фильтр по статусу
    first: Int = 20                # Кол-во записей (пагинация)
    after: String                  # Курсор (Relay-style)
  ): OrderConnection!
}

type OrderConnection {             # Relay-style пагинация
  edges: [OrderEdge!]!             # Массив рёбер
  pageInfo: PageInfo!              # Информация о пагинации
  totalCount: Int!                 # Общее кол-во заказов
}

type OrderEdge {
  node: Order!                     # Объект заказа
  cursor: String!                  # Курсор элемента
}

type Order {
  id: ID!                          # UUID заказа
  status: OrderStatus!             # Статус заказа
  totalAmount: Float!              # Сумма заказа
  currency: String!                # Валюта (ISO 4217)
  items: [OrderItem!]!             # Позиции заказа
  createdAt: DateTime!             # Дата создания
  completedAt: DateTime            # Дата завершения (nullable)
}

type OrderItem {
  productId: ID!                   # UUID продукта
  productName: String!             # Название продукта
  quantity: Int!                   # Количество
  price: Float!                    # Цена за единицу
}

type PageInfo {                    # Relay-style PageInfo
  hasNextPage: Boolean!            # Есть следующая страница
  hasPreviousPage: Boolean!        # Есть предыдущая страница
  startCursor: String              # Курсор первого элемента
  endCursor: String                # Курсор последнего элемента
}

enum OrderStatus {
  PENDING                          # Ожидает подтверждения
  CONFIRMED                        # Подтверждён
  PROCESSING                       # В обработке
  SHIPPED                          # Отправлен
  DELIVERED                        # Доставлен
  CANCELLED                        # Отменён
  REFUNDED                         # Возврат
}
```

**Параметры запроса (СТД-СИНХ-ПАР-01, СТД-СИНХ-ПАР-08):**
| Параметр | Тип | Обязат. | Описание | Валидация | По умолч. | Пример |
|----------|-----|---------|----------|-----------|-----------|--------|
| userId | ID! | Да | UUID пользователя | minLength: 36, maxLength: 36, format: uuid | — | "550e8400-e29b-41d4-a716-446655440000" |
| dateFrom | DateTime! | Да | Начало периода | format: date-time, <= dateTo | — | "2026-01-01T00:00:00Z" |
| dateTo | DateTime! | Да | Конец периода | format: date-time, >= dateFrom, <= now | — | "2026-01-31T23:59:59Z" |
| status | OrderStatus | Нет | Фильтр по статусу | enum: [PENDING, CONFIRMED, PROCESSING, SHIPPED, DELIVERED, CANCELLED, REFUNDED] | — | DELIVERED |
| first | Int | Нет | Кол-во записей | minimum: 1, maximum: 100 | 20 | 10 |
| after | String | Условно* | Курсор пагинации | minLength: 1, maxLength: 256, format: base64 | — | "eyJpZCI6MTB9" |

**Условия обязательности:**
| Параметр | Условие обязательности |
|----------|----------------------|
| after | Обязателен при запросе следующей страницы (pageInfo.hasNextPage = true в предыдущем ответе) |

**Параметры ответа (СТД-СИНХ-ПАР-05, СТД-СИНХ-ПАР-08):**
| Параметр | Тип | Обязат. | Описание | Валидация | По умолч. | Пример | Маппинг |
|----------|-----|---------|----------|-----------|-----------|--------|---------|
| edges | [OrderEdge!]! | Да | Массив рёбер | minItems: 0, maxItems: 100 | [] | [...] | — |
| ├─ node | Order! | Да | Объект заказа | required: [id, status, totalAmount, currency, items, createdAt] | — | {...} | — |
| │ ├─ id | ID! | Да | UUID заказа | minLength: 36, maxLength: 36, format: uuid | — | "ord-a1b2c3..." | Orders DB → order_id |
| │ ├─ status | OrderStatus! | Да | Статус заказа | enum: [PENDING, CONFIRMED, ...] | — | DELIVERED | Orders DB → status |
| │ ├─ totalAmount | Float! | Да | Сумма заказа | minimum: 0, maximum: 999999999 | — | 12500.00 | Orders DB → total_cents / 100 |
| │ ├─ currency | String! | Да | Валюта | minLength: 3, maxLength: 3, pattern: `^[A-Z]{3}$` | — | "RUB" | Orders DB → currency_code |
| │ ├─ items | [OrderItem!]! | Да | Позиции заказа | minItems: 1, maxItems: 100 | — | [...] | — |
| │ │ ├─ productId | ID! | Да | UUID продукта | minLength: 36, maxLength: 36, format: uuid | — | "prod-..." | Products DB → product_id |
| │ │ ├─ productName | String! | Да | Название | minLength: 1, maxLength: 200 | — | "Наушники" | Products DB → name |
| │ │ ├─ quantity | Int! | Да | Количество | minimum: 1, maximum: 9999 | — | 2 | OrderItems DB → qty |
| │ │ └─ price | Float! | Да | Цена за единицу | minimum: 0, maximum: 999999999 | — | 6250.00 | OrderItems DB → unit_price |
| │ ├─ createdAt | DateTime! | Да | Дата создания | format: date-time | — | "2026-01-15T10:30:00Z" | Orders DB → created_at |
| │ └─ completedAt | DateTime | Нет | Дата завершения | format: date-time | null | "2026-01-16T14:00:00Z" | Orders DB → done_at |
| └─ cursor | String! | Да | Курсор элемента | minLength: 1, maxLength: 256 | — | "eyJpZCI6MX0=" | Вычисляется |
| totalCount | Int! | Да | Общее кол-во заказов | minimum: 0 | — | 42 | COUNT(*) |
| pageInfo | PageInfo! | Да | Пагинация | required: [hasNextPage, hasPreviousPage] | — | {...} | Вычисляется |
| ├─ hasNextPage | Boolean! | Да | Есть следующая страница | — | false | true | offset + first < total |
| ├─ hasPreviousPage | Boolean! | Да | Есть предыдущая страница | — | false | false | offset > 0 |
| ├─ startCursor | String | Нет | Курсор первого элемента | maxLength: 256 | null | "eyJpZCI6MX0=" | edges[0].cursor |
| └─ endCursor | String | Нет | Курсор последнего элемента | maxLength: 256 | null | "eyJpZCI6MTB9" | edges[-1].cursor |

**JSON Schema запроса:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "userOrders Query Variables",
  "type": "object",
  "required": ["userId", "dateFrom", "dateTo"],
  "additionalProperties": false,
  "properties": {
    "userId": {
      "type": "string",
      "description": "UUID пользователя",
      "minLength": 36,
      "maxLength": 36,
      "format": "uuid"
    },
    "dateFrom": {
      "type": "string",
      "description": "Начало периода",
      "format": "date-time"
    },
    "dateTo": {
      "type": "string",
      "description": "Конец периода",
      "format": "date-time"
    },
    "status": {
      "type": "string",
      "description": "Фильтр по статусу заказа",
      "enum": ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"]
    },
    "first": {
      "type": "integer",
      "description": "Количество записей",
      "minimum": 1,
      "maximum": 100,
      "default": 20
    },
    "after": {
      "type": "string",
      "description": "Курсор пагинации (обязателен при запросе следующей страницы)",
      "minLength": 1,
      "maxLength": 256
    }
  }
}
```

**JSON Schema ответа:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "userOrders Response",
  "type": "object",
  "required": ["data"],
  "properties": {
    "data": {
      "type": "object",
      "required": ["userOrders"],
      "properties": {
        "userOrders": {
          "type": "object",
          "required": ["edges", "pageInfo", "totalCount"],
          "properties": {
            "edges": {
              "type": "array",
              "minItems": 0,
              "maxItems": 100,
              "items": {
                "type": "object",
                "required": ["node", "cursor"],
                "properties": {
                  "node": { "$ref": "#/definitions/Order" },
                  "cursor": { "type": "string", "maxLength": 256 }
                }
              }
            },
            "pageInfo": { "$ref": "#/definitions/PageInfo" },
            "totalCount": { "type": "integer", "minimum": 0 }
          }
        }
      }
    }
  },
  "definitions": {
    "Order": {
      "type": "object",
      "required": ["id", "status", "totalAmount", "currency", "items", "createdAt"],
      "properties": {
        "id": { "type": "string", "minLength": 36, "maxLength": 36, "format": "uuid" },
        "status": { "type": "string", "enum": ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED", "CANCELLED", "REFUNDED"] },
        "totalAmount": { "type": "number", "minimum": 0, "maximum": 999999999 },
        "currency": { "type": "string", "minLength": 3, "maxLength": 3, "pattern": "^[A-Z]{3}$" },
        "items": { "type": "array", "minItems": 1, "maxItems": 100, "items": { "$ref": "#/definitions/OrderItem" } },
        "createdAt": { "type": "string", "format": "date-time" },
        "completedAt": { "type": ["string", "null"], "format": "date-time" }
      }
    },
    "OrderItem": {
      "type": "object",
      "required": ["productId", "productName", "quantity", "price"],
      "properties": {
        "productId": { "type": "string", "minLength": 36, "maxLength": 36, "format": "uuid" },
        "productName": { "type": "string", "minLength": 1, "maxLength": 200 },
        "quantity": { "type": "integer", "minimum": 1, "maximum": 9999 },
        "price": { "type": "number", "minimum": 0, "maximum": 999999999 }
      }
    },
    "PageInfo": {
      "type": "object",
      "required": ["hasNextPage", "hasPreviousPage"],
      "properties": {
        "hasNextPage": { "type": "boolean" },
        "hasPreviousPage": { "type": "boolean" },
        "startCursor": { "type": ["string", "null"], "maxLength": 256 },
        "endCursor": { "type": ["string", "null"], "maxLength": 256 }
      }
    }
  }
}
```

**Пример запроса и ответа — Happy Path:**
```graphql
query {
  userOrders(
    userId: "550e8400-e29b-41d4-a716-446655440000"
    dateFrom: "2026-01-01T00:00:00Z"
    dateTo: "2026-01-31T23:59:59Z"
    first: 10
  ) {
    edges {
      node { id status totalAmount currency createdAt
        items { productName quantity price } }
      cursor
    }
    pageInfo { hasNextPage endCursor }
    totalCount
  }
}
```

```json
{
  "data": {
    "userOrders": {
      "edges": [
        {
          "node": {
            "id": "ord-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "status": "DELIVERED",
            "totalAmount": 12500.00,
            "currency": "RUB",
            "createdAt": "2026-01-15T10:30:00Z",
            "items": [
              {
                "productName": "Беспроводные наушники",
                "quantity": 2,
                "price": 6250.00
              }
            ]
          },
          "cursor": "eyJpZCI6MX0="
        }
      ],
      "pageInfo": {
        "hasNextPage": true,
        "endCursor": "eyJpZCI6MTB9"
      },
      "totalCount": 42
    }
  }
}
```

**Пограничный случай: Пустой результат (нет заказов за период):**
```json
{
  "data": {
    "userOrders": {
      "edges": [],
      "pageInfo": {
        "hasNextPage": false,
        "hasPreviousPage": false,
        "startCursor": null,
        "endCursor": null
      },
      "totalCount": 0
    }
  }
}
```
> **Примечание:** При отсутствии данных: `edges = []`, `totalCount = 0`, `pageInfo.hasNextPage = false`, курсоры = `null`.

**Коды ошибок (СТД-GQL-06):**
| Код | Описание | HTTP эквивалент |
|-----|----------|-----------------|
| GRAPHQL_PARSE_FAILED | Ошибка парсинга запроса | 400 |
| GRAPHQL_VALIDATION_FAILED | Ошибка валидации схемы | 400 |
| BAD_USER_INPUT | Невалидные входные данные | 400 |
| UNAUTHENTICATED | Требуется аутентификация | 401 |
| FORBIDDEN | Нет прав доступа | 403 |
| NOT_FOUND | Пользователь не найден | 404 |
| INTERNAL_SERVER_ERROR | Внутренняя ошибка | 500 |
