# [METHOD] [path]

## Назначение

[Что делает endpoint и кто его использует.]

## Endpoint

| Параметр | Значение |
|---|---|
| Метод | `[GET/POST/PUT/PATCH/DELETE]` |
| Path | `[path]` |
| Producer | `[service]` |
| Consumer | `[client/service]` |
| Аутентификация | `[auth]` |
| Формат данных | `JSON` |

## Request headers

| Заголовок | Обязат. | Описание | Пример |
|---|---|---|---|
| Authorization | Да | Bearer token | `Bearer ...` |
| X-Request-ID | Да | Идентификатор запроса | `550e8400-e29b-41d4-a716-446655440000` |

## Path parameters

| Параметр | Тип | Обязат. | Описание | Валидация | Пример |
|---|---|---|---|---|---|
| `[id]` | string | Да | [описание] | `format: uuid` | `550e8400-e29b-41d4-a716-446655440000` |

## Query parameters

| Параметр | Тип | Обязат. | Описание | Валидация | Пример |
|---|---|---|---|---|---|
| `[name]` | string | Нет | [описание] | `maxLength: 100` | `[value]` |

## Request body

| Поле | Тип | Формат | Nullable | Описание | Валидация | Пример | Маппинг |
|---|---|---|---|---|---|---|---|
| `[field]` | string | uuid | Нет | [описание] | `format: uuid` | `550e8400-e29b-41d4-a716-446655440000` | [mapping] |

## Response body

| Поле | Тип | Формат | Nullable | Описание | Валидация | Пример | Маппинг |
|---|---|---|---|---|---|---|---|
| `[field]` | string | — | Нет | [описание] | — | `[value]` | [mapping] |

## Коды ответов

| HTTP код | Код ошибки | Описание |
|---|---|---|
| 200 | — | Успешный ответ |
| 400 | VALIDATION_ERROR | Ошибка валидации |
| 401 | UNAUTHORIZED | Нет или неверный auth context |
| 500 | INTERNAL_ERROR | Внутренняя ошибка |

## Примеры

```http
GET /api/v1/resources/550e8400-e29b-41d4-a716-446655440000
Authorization: Bearer eyJ...
X-Request-ID: 7c9e6679-7425-40de-944b-e07fc1f90ae7
```

```json
{
  "field": "value"
}
```
