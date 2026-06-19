# GraphQL [Query/Mutation/Subscription]: [operationName]

## Назначение

[Что делает операция и кто ее вызывает.]

## Тип операции

| Параметр | Значение |
|---|---|
| Тип | Query / Mutation / Subscription |
| Endpoint | `/graphql` |
| Producer | [GraphQL service/gateway] |
| Consumer | [client/service] |
| Аутентификация | [auth] |

## Headers

| Заголовок | Обязат. | Описание | Пример |
|---|---|---|---|
| Authorization | Да | Bearer token | `Bearer ...` |
| Content-Type | Да | Тип тела запроса | `application/json` |
| X-Request-ID | Да | Идентификатор запроса | `7c9e6679-7425-40de-944b-e07fc1f90ae7` |

## Schema definition

```graphql
type Query {
  """Описание операции"""
  operationName(
    """Описание параметра"""
    entityId: ID!
    first: Int = 20
    after: String
  ): EntityConnection!
}

type EntityConnection {
  edges: [EntityEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type EntityEdge {
  node: Entity!
  cursor: String!
}

type Entity {
  id: ID!
  name: String!
}

type PageInfo {
  hasNextPage: Boolean!
  hasPreviousPage: Boolean!
  startCursor: String
  endCursor: String
}
```

## Arguments / input

| Параметр | Тип | Обязат. | Описание | Валидация | По умолч. | Пример |
|---|---|---|---|---|---|---|
| entityId | ID! | Да | UUID сущности | `format: uuid` | — | `"550e8400-e29b-41d4-a716-446655440000"` |
| first | Int | Нет | Количество записей | `minimum: 1, maximum: 100` | `20` | `10` |
| after | String | Нет | Курсор пагинации | `maxLength: 256` | — | `"eyJpZCI6MX0="` |

## Response fields

| Поле | Тип | Nullable | Описание | Аргументы | Директивы | Пример |
|---|---|---|---|---|---|---|
| edges | [EntityEdge!]! | Нет | Ребра Relay-style списка | — | — | `[]` |
| pageInfo | PageInfo! | Нет | Информация о пагинации | — | — | `{...}` |
| totalCount | Int! | Нет | Общее количество | — | — | `42` |

## Ошибки

| Код | Описание | HTTP эквивалент | Условие |
|---|---|---|---|
| BAD_USER_INPUT | Невалидные входные данные | 400 | Ошибка в аргументах |
| UNAUTHENTICATED | Требуется аутентификация | 401 | Нет auth context |
| INTERNAL_SERVER_ERROR | Внутренняя ошибка | 500 | Ошибка сервиса |

## Примеры

```graphql
query {
  operationName(entityId: "550e8400-e29b-41d4-a716-446655440000", first: 10) {
    edges {
      node { id name }
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
    "operationName": {
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
