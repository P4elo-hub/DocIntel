#### State Diagram — Жизненный цикл заказа

Канонические примеры State Diagram из `standarts_features (3).md`: базовый жизненный цикл заказа, вложенные состояния платежа и параллельные регионы.

**Назначение:**

Диаграммы показывают состояния заказа, события переходов, guards, transition actions, entry/exit/do actions, вложенные состояния и параллельные регионы.

**Состояния и переходы:**

| № | Состояние / переход | Событие | Guard | Действие |
|---|---|---|---|---|
| 1 | `[*] -> Created` | `createOrder` | - | - |
| 2 | `Created -> Pending` | `submit` | - | - |
| 3 | `Pending -> Paid` | `payment_received` | `[amount >= total]` | `reserveStock` |
| 4 | `Pending -> Cancelled` | `timeout` | `[> 30 min]` | `releaseHold` |
| 5 | `Paid -> Processing` | `startProcessing` | - | `notifyWarehouse` |

**PlantUML: Базовая State Diagram**

```plantuml
@startuml
title State Diagram — Жизненный цикл заказа
caption Базовый жизненный цикл заказа от создания до доставки или отмены

[*] --> Created : 1. createOrder
Created --> Pending : 2. submit
Pending --> Paid : 3. payment_received\n[amount >= total]\n/ reserveStock
Pending --> Cancelled : 4. timeout [> 30 min]\n/ releaseHold
Paid --> Processing : 5. startProcessing\n/ notifyWarehouse
Processing --> Shipped : 6. shipOrder\n/ sendTrackingEmail
Shipped --> Delivered : 7. confirmDelivery\n/ completeOrder
Delivered --> [*]
Cancelled --> [*]

Created : entry/ initializeOrder
Created : exit/ logStateChange
Pending : entry/ holdAmount
Pending : do/ waitForPayment
Paid : entry/ confirmPayment
Processing : entry/ assignToWarehouse
Shipped : entry/ generateTrackingNumber

legend right
  | Обозначение | Значение |
  | [*] | Начальное или конечное состояние |
  | State --> State | Переход между состояниями |
  | event [guard] / action | Событие, условие и действие перехода |
  | entry/ | Действие при входе в состояние |
  | exit/ | Действие при выходе из состояния |
  | do/ | Внутреннее действие состояния |
endlegend
@enduml
```

**PlantUML: State Diagram с вложенными состояниями и guard**

```plantuml
@startuml
title State Diagram — Заказ с обработкой платежа
caption Вложенное состояние Payment Processing и retry-логика оплаты

[*] --> Draft

state "Payment Processing" as PayProc {
  [*] --> Authorizing
  Authorizing --> Authorized : success
  Authorizing --> Declined : failure\n[retriable = false]
  Authorizing --> RetryWait : failure\n[retriable = true]
  RetryWait --> Authorizing : retry\n[attempts < 3]
  RetryWait --> Declined : maxRetries\n[attempts >= 3]
  Authorized --> Captured : capture\n/ debitAccount
  Authorized --> Voided : void\n[within 24h]\n/ releaseHold
  Captured --> Refunded : refund\n/ creditAccount
  Declined --> [*]
  Captured --> [*]
  Refunded --> [*]
  Voided --> [*]
}

Draft --> Submitted : submit\n[isValid]
Submitted --> PayProc : initiatePayment
PayProc --> Completed : paymentSuccess
PayProc --> Failed : paymentFailed
Completed --> [*]
Failed --> Draft : retry

Draft : entry/ validateFields
Submitted : entry/ freezeOrder

note right of PayProc
  Вложенное состояние:
  детализация процесса оплаты
end note

note left of RetryWait
  exponential backoff:
  1s -> 5s -> 30s
end note

legend right
  | Обозначение | Значение |
  | state { ... } | Вложенное состояние |
  | [guard] | Условие перехода |
  | / action | Действие перехода |
  | note | Пояснение к состоянию или переходу |
endlegend
@enduml
```

**PlantUML: State Diagram с параллельными состояниями**

```plantuml
@startuml
title State Diagram — Активный сервис
caption Параллельные регионы: обработка запросов и мониторинг здоровья

[*] --> Active

state Active {
  [*] --> Idle
  Idle --> Processing : newRequest
  Processing --> Idle : done

  --

  [*] --> Healthy
  Healthy --> Degraded : errorRate > 5%
  Degraded --> Healthy : errorRate < 1%
  Degraded --> Unhealthy : errorRate > 50%
  Unhealthy --> Degraded : partial_recovery
}

Active --> Maintenance : admin_shutdown\n/ drainConnections
Maintenance --> Active : admin_start\n/ warmupCache
Active --> [*] : decommission

note right of Active
  Параллельные регионы:
  обработка запросов || мониторинг здоровья
end note

legend right
  | Обозначение | Значение |
  | -- | Разделитель параллельных регионов |
  | [*] | Начальное или конечное состояние региона |
  | note | Пояснение к параллельным регионам |
endlegend
@enduml
```

**Легенда:**

| Обозначение | Значение |
|---|---|
| `[*]` | Начальное или конечное состояние |
| `State --> State` | Переход |
| `event [guard] / action` | Событие, условие и действие перехода |
| `entry/`, `exit/`, `do/` | Действия состояния |
| `state { ... }` | Вложенное состояние |
| `--` | Разделитель параллельных регионов |

**Соответствие тексту:**

| Элемент на диаграмме | Номер | Описание в тексте |
|---|---|---|
| `Created -> Pending` | 2 | Заказ отправлен в обработку |
| `Pending -> Paid` | 3 | Платеж получен и сумма достаточна |
| `Pending -> Cancelled` | 4 | Истекло время ожидания платежа |
| `Paid -> Processing` | 5 | Старт обработки заказа |

**Gaps и допущения:**

| ID | Тип | Где найдено | Описание | Как закрыть |
|---|---|---|---|---|
| - | - | - | Gaps не выявлены | - |
