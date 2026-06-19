#### Sequence Diagram — [Название сценария]

**Назначение:**

[Кратко описать, какой сценарий взаимодействия показывает диаграмма.]

**Участники:**

| Участник | Тип | Роль |
|---|---|---|
| `[Actor]` | actor | [Внешний пользователь или система] |
| `[Service]` | participant | [Сервис или компонент] |
| `[Queue]` | queue | [Очередь или topic, если есть] |

**PlantUML:**

```plantuml
@startuml
title Sequence Diagram — [Название сценария]
caption [Краткое назначение диаграммы или версия]

actor "[Актор]" as User
participant "[Frontend]" as FE
participant "[Backend Service]" as Backend
participant "[Downstream Service]" as Downstream

== [Фаза сценария] ==

User -> FE: 1. [user action]
activate FE
FE --> User: 2. [UI response to user action]

alt [условие успеха — Backend принимает запрос]
  FE -> Backend ++: 3. [operationName(params)]
  group [Backend Service] [bounded subprocess label]
    Backend -> Downstream ++: 3.1 [downstreamCall()]
    Downstream --> Backend --: [Result]
    Backend -> Backend ++: 3.2 [internalStep()]
    return
  end
  Backend --> FE --: 4. [Status / Result]
  alt [условие отображения A]
    FE --> User: 5a. [render variant A]
  else [условие отображения B]
    FE --> User: 5b. [render variant B]
  end
else [client-side timeout — Backend не активирован]
  FE -> FE ++: 3. [awaitBackendResponse(timeout)]
  FE -> FE --: timeout / connection error
  FE --> User: 4. [error message]
end

deactivate FE

legend right
  | Правило | Значение |
  | actor | Единственный участник, который может слать без activation |
  | activate FE | Сразу после User -> FE, до любого FE --> User / FE -> ... |
  | -> Target ++ | Sync-вызов всегда открывает activation callee |
  | --> Source -- | Return закрывает activation callee |
  | FE -> FE ++ | Client-side timeout без стрелок на пустой Backend |
  | group | Bounded subprocess на live lifeline |
  | A -> A ++ / return | Stacked activation |
endlegend
@enduml
```

**Легенда:**

| Обозначение | Значение |
|---|---|
| `->` | Синхронный вызов (между participant только с `++` на callee) |
| `->>` | Асинхронный вызов |
| `-->` | Ответ / return (с `--` при закрытии callee) |
| `++` / `--` | Activation start / end на callee |
| `activate` / `deactivate` | Явное открытие/закрытие lifeline Frontend на scope обработки |
| `actor` | Может инициировать сообщение без activation bar |
| `participant` | Должен быть live на каждой исходящей/входящей sync-стрелке |
| `alt` / `else` | Все operands согласованы по activation state на merge-point |
| `group` | Bounded subprocess внутри live lifeline |
| `FE -> FE ++` | Client-side timeout/retry без стрелок на пустой Backend |

**Соответствие тексту:**

| Элемент на диаграмме | Номер | Описание в тексте |
|---|---|---|
| `[operationName(params)]` | 1 | [Ссылка на шаг текстового описания] |

**Gaps и допущения:**

| ID | Тип | Где найдено | Описание | Как закрыть |
|---|---|---|---|---|
| GAP-UML-001 | Gap | [Участники / PlantUML / Соответствие тексту] | [Какой информации не хватает] | [Что нужно уточнить] |
| ASM-UML-001 | Assumption | [Участники / PlantUML / Соответствие тексту] | [Что агент предположил] | [Как подтвердить] |
