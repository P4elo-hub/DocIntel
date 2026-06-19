# gRPC сервис: [ServiceName]

## Назначение

[Что делает сервис и кто его вызывает.]

## Service и package

| Параметр | Значение |
|---|---|
| Package | `[package].v1` |
| Service | `[ServiceName]` |
| Тип RPC | Unary / Server Streaming / Client Streaming / Bidirectional |
| Producer | `[service]` |
| Consumer | `[client]` |

## Proto definition

```protobuf
syntax = "proto3";
package [package].v1;

service [ServiceName] {
  rpc [MethodName]([RequestType]) returns ([ResponseType]);
}

message [RequestType] {
  string field_id = 1; // Описание
}

message [ResponseType] {
  string result = 1; // Описание
}
```

## Metadata

| Metadata key | Обязат. | Описание | Пример |
|---|---|---|---|
| authorization | Да | Bearer token | `Bearer ...` |
| x-request-id | Да | Идентификатор запроса | `7c9e6679-7425-40de-944b-e07fc1f90ae7` |

## Request messages

| Поле | Тип | Номер поля | Обязательность | Описание | Валидация | Пример |
|---|---|---:|---|---|---|---|
| field_id | string | 1 | required | [описание] | `format: uuid` | `550e8400-e29b-41d4-a716-446655440000` |

## Response messages

| Поле | Тип | Номер поля | Обязательность | Описание | Валидация | Пример |
|---|---|---:|---|---|---|---|
| result | string | 1 | required | [описание] | — | `OK` |

## gRPC statuses

| gRPC код | Название | Использование | Условие |
|---:|---|---|---|
| 0 | OK | Успешное выполнение | Запрос обработан |
| 3 | INVALID_ARGUMENT | Невалидные параметры | Нарушена валидация |
| 13 | INTERNAL | Внутренняя ошибка | Ошибка сервиса |
| 14 | UNAVAILABLE | Сервис недоступен | Target недоступен |

## Примеры

[Добавить пример grpcurl или фрагмент запроса/ответа, если источник это подтверждает.]
