#### Sequence Diagram — Перевод между счетами

Канонический пример Sequence Diagram из `standarts_features (3).md`: процесс перевода между счетами с синхронными вызовами, асинхронной публикацией события, retry-фрагментом, ветвлениями и легендой.

**Назначение:**

Диаграмма показывает целевой процесс перевода: клиент вызывает Transfer Service, сервис проверяет данные через АБС, публикует событие в Kafka и не блокирует UI на отправке уведомления.

**Участники:**

| Участник | Тип | Роль |
|---|---|---|
| `Client` | actor | Клиент в мобильном приложении |
| `Transfer` | participant | Transfer Service |
| `ABS` | participant | Автоматизированная банковская система |
| `Kafka` | queue | Topic `transfer.completed` |
| `Notify` | participant | Notification Service |

**PlantUML:**

```plantuml
@startuml
title Sequence Diagram — Перевод между счетами
caption Процесс перевода (Transfer Service + async Push через Kafka)

actor "Клиент\n(Мобильное приложение)" as Client
participant "Transfer Service\n[Java/Spring Boot]" as Transfer #LightBlue
participant "АБС" as ABS
queue "Kafka\ntransfer.completed" as Kafka #LightGreen
participant "Notification Service\n[Node.js]" as Notify #LightGreen

== Инициализация ==

Client -> Transfer ++: 1. GET /accounts (список счетов)
Transfer -> ABS ++: 1.1 getAccounts(clientId)
note right #36B37E: [NEW] параллельный запрос\nсчетов + лимитов
Transfer ->> ABS: 1.2 getLimits(clientId)
ABS --> Transfer --: Account[]
ABS --> Transfer: Limits
Transfer --> Client --: 200 OK — Account[] + Limits
note right: ~400 мс (было ~800 мс)

== Ввод данных ==

Client -> Client: 2. Выбирает счёт-источник и счёт-получатель
Client -> Client: 3. Вводит сумму перевода

== Проверка и проведение ==

Client -> Transfer ++: 4. POST /transfer(from, to, amount)
Transfer -> ABS ++: 4.1 checkBalance(accountId)
note right #0065FF: [CHG] retry до 3 раз\nпри таймауте АБС

loop retry (max 3, backoff 200/400/800 мс)
  ABS --> Transfer: balance / timeout
  break balance получен
  end
end
ABS --> Transfer --: balance
note right: ~500 мс

alt balance < amount
  Transfer --> Client: 400 — Недостаточно средств [BR-02]
else balance >= amount
  Transfer -> Transfer: 5. checkDailyLimit(clientId, amount)
  note right #36B37E: [NEW] Проверка дневного\nлимита [BR-03]\n3 000 000 RUB

  alt dailySpent + amount > 3 000 000
    Transfer --> Client: 400 — Превышен дневной лимит [BR-03]
  else dailySpent + amount <= 3 000 000
    Transfer -> ABS ++: 6. executeTransfer(from, to, amount, idempotencyKey)
    note right #0065FF: [CHG] retry с idempotency key
    ABS --> Transfer --: TransactionResult
    note right: ~1000 мс (было ~1200 мс)
  end
end

== Уведомление (асинхронное, НЕ блокирует UI) ==

Transfer ->> Kafka: 7. publish(TransferCompleted)
note right #36B37E: [NEW] async через Kafka\nне блокирует клиента

Transfer --> Client --: 200 OK — TransferResult
note right #0065FF: [CHG] Ответ сразу после\nпроведения (~1.9 сек)

Kafka ->> Notify ++: 8. consume(TransferCompleted)
Notify -> Notify: 8.1 formatPushMessage()
Notify ->> Client: 8.2 sendPush(deviceToken, message)
note right #36B37E: [NEW] Push вместо SMS
deactivate Notify

== Итого: ~1900 мс (было ~4500 мс) ==

legend right
  | Цвет / метка | Значение |
  | <back:#36B37E> [NEW] </back> | Новый элемент |
  | <back:#0065FF><color:white> [CHG] </color></back> | Изменённый элемент |
  | ──▶ (сплошная) | Синхронный вызов |
  | ──> (открытая) | Асинхронный вызов |
  | ──▷ (пунктир) | Ответ (return) |
  | █ Активация | Период обработки |
endlegend
@enduml
```

**Легенда:**

| Обозначение | Значение |
|---|---|
| `->` | Синхронный вызов |
| `->>` | Асинхронный вызов |
| `-->` | Ответ / return |
| `++` / `--` | Activation start / end |
| `[NEW]` | Новый элемент |
| `[CHG]` | Измененный элемент |

**Соответствие тексту:**

| Элемент на диаграмме | Номер | Описание в тексте |
|---|---|---|
| `GET /accounts` | 1 | Получение счетов клиента |
| `POST /transfer` | 4 | Инициация перевода |
| `checkDailyLimit` | 5 | Проверка дневного лимита |
| `executeTransfer` | 6 | Проведение перевода |
| `publish(TransferCompleted)` | 7 | Публикация события об успешном переводе |
| `consume(TransferCompleted)` | 8 | Асинхронная обработка уведомления |

**Gaps и допущения:**

| ID | Тип | Где найдено | Описание | Как закрыть |
|---|---|---|---|---|
| - | - | - | Gaps не выявлены | - |
