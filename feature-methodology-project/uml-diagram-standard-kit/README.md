# UML Diagram Standard Kit

Этот каталог раскладывает разделы `2.3. Общие требования к диаграммам` и `2.4. UML-диаграммы` из `standarts_features (3).md` на рабочие слои для агентного pipeline.

## Зачем нужен kit

Этот каталог задает единый стандарт для выбора типа UML-диаграммы, построения PlantUML, проверки легенды, нумерации и связи элементов диаграммы с текстовым описанием.

| Слой | Зачем нужен | Что лежит здесь |
|---|---|---|
| `skills/` | Учит агента выбирать и строить UML-диаграммы. | `uml-diagram-analysis/SKILL.md` |
| `spec-kit/` | Задает общий контракт и контракты конкретных UML-типов. | `uml-diagram.schema.yaml`, `sequence-diagram.schema.yaml`, `activity-diagram.schema.yaml`, `state-diagram.schema.yaml` |
| `templates/` | Дает Markdown/PlantUML-шаблоны. | Шаблоны Sequence, Activity и State Diagram |
| `examples/` | Показывает ожидаемый стиль результата. | Примеры PlantUML из исходного стандарта |
| `quality-gates/` | Проверяет готовность диаграмм. | Общий gate и gates по типам диаграмм |

## Матрица типов

| Ситуация | Тип диаграммы | Когда применять |
|---|---|---|
| Описание сценариев взаимодействия | Sequence Diagram | Участники, сообщения, ответы, синхронные/асинхронные цепочки |
| Описание процесса или алгоритма | Activity Diagram | Действия, условия, ветвления, параллельные потоки, swimlanes |
| Описание состояний объекта | State Diagram | Жизненный цикл заявки, заказа, операции, статусы и переходы |

## Clarification-first

По умолчанию skill **не рисует диаграмму сразу**. Сначала он собирает gaps и задает уточняющие вопросы по:

- именам участников и сервисов;
- именам операций, endpoint, method, RPC, topic, event;
- sync/async режиму каждого взаимодействия;
- параллельным веткам и правилам агрегации;
- **альтернативным error paths**: timeout, retry, invalid response, partial/degraded response, поведение UI при ошибке.

Draft без уточнений допустим только если пользователь явно просит черновик. Даже если пользователь описал только happy path, skill обязан спросить про ошибки и показать их на схеме, когда поведение подтверждено.

## Lifeline Logic для Sequence

Перед сдачей skill проходит **message-by-message audit** по канонической логике lifeline (`skills/uml-diagram-analysis/SKILL.md` → секция **Lifeline Logic**).

### Определения

| Термин | Смысл |
|---|---|
| **Live lifeline** | У участника открыта activation bar |
| **Empty lifeline** | Activation bar нет |
| **Dead lifeline** | Activation bar уже закрыта |

### Жёсткие правила

1. **Только `actor`** может отправить сообщение без activation bar.
2. **Frontend, Backend, Service** — live на **каждой** sync-стрелке (исходящей и входящей).
3. **Sync-вызов** между participant: только `A -> B ++` — plain `A -> B` **запрещён**.
4. **Return**: `Callee --> Caller --` — callee и caller live в момент отправки/получения.
5. **Запрещено**: стрелка из dead/empty lifeline participant или в empty/dead lifeline participant.
6. **`User -> FE`** → сразу **`activate FE`** перед любым `FE --> User` / `FE -> Backend ++` / `FE -> FE ++`.
7. **Client-side timeout** (Backend не принял запрос): `FE -> FE ++` / `--` — **без** стрелок на пустой Backend.

### Quality gates

`SEQ-GATE-005K` … `SEQ-GATE-005Q` — live lifeline, `++` на callee, `activate FE`, client-side timeout, return endpoints.

## Gaps и допущения

Если данных для диаграммы не хватает, skill сначала задает уточняющие вопросы. Если пользователь просит draft или часть данных все еще неизвестна, неопределенность фиксируется явно:

- `GAP-UML-001` — обязательная информация отсутствует;
- `ASM-UML-001` — агент сделал слабое предположение;
- каждый `GAP-UML-*` и `ASM-UML-*` должен быть отражен в секции `Gaps и допущения`.

## Главная идея

- Skill говорит агенту, как выбрать тип диаграммы и какие уточнения задать.
- Spec говорит, каким должен быть результат.
- Template говорит, куда писать.
- Example показывает норму качества.
- Quality gate решает, можно ли считать диаграмму готовой.
