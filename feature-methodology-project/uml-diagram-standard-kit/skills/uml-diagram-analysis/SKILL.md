---
name: uml-diagram-analysis
description: Selects, analyzes and documents UML diagrams using source evidence. Use when building Sequence, Activity or State diagrams for interactions, processes, algorithms, object states and lifecycles.
disable-model-invocation: true
---

# UML Diagram Analysis

## Purpose

Use this skill when an agent must choose or write a UML diagram. The skill defines the workflow. The required output format is defined by the general spec, type-specific specs, templates, canonical examples and quality gates in this kit.

This skill is not a substitute for evidence. Do not invent participants, system calls, states, transitions, guards, parallel branches, errors, retries, timings, colors, changed/new/deleted markers or business rules without evidence.

The final artifact must preserve uncertainty explicitly:

- Mark missing required information with precise `GAP-UML-NNN` IDs.
- Mark weak assumptions with precise `ASM-UML-NNN` IDs.
- Add every gap and assumption to the `Gaps и допущения` table.
- Do not write vague phrases like `требует уточнения`, `не указано`, or `unknown` without a linked GAP ID.
- If no gaps or assumptions remain, write `Gaps не выявлены` in the `Gaps и допущения` table.

## Clarification-First Policy

**Default behavior: ask clarifying questions first, do not draft the diagram immediately.**

When the user asks to build a Sequence, Activity or State diagram:

1. Parse the request and identify all missing information.
2. Ask grouped clarification questions for every critical gap.
3. Wait for user answers.
4. Only then write the final diagram artifact.

Do **not** skip clarification and jump straight to PlantUML when any of these are unknown:

- exact participant or service names;
- exact operation, endpoint, method or event names;
- sync vs async mode for each interaction;
- **alternative error paths and fallback behavior**;
- retry, timeout and invalid-response handling;
- parallel flow semantics;
- aggregation or mapping rules;
- names of external sources or integrations.

**Even if the user describes only the happy path**, you must still ask about errors, retries, timeouts, invalid responses and alternative branches before drafting the final diagram.

Draft without prior clarification is allowed **only** when the user explicitly asks for it, for example:

- `сделай черновик`;
- `draft`;
- `пока без уточнений`;
- `нарисуй как есть, gaps потом`.

If the user did not explicitly ask for a draft, producing a diagram full of `ASM-UML-*` instead of asking questions first is incorrect behavior.

## Required Files

Before writing a UML artifact, read the relevant files:

| Diagram type | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| General UML | `spec-kit/uml-diagram.schema.yaml` | type-specific template | type-specific example | `quality-gates/uml-diagram-review.yaml` |
| Sequence | `spec-kit/sequence-diagram.schema.yaml` | `templates/sequence-diagram.template.md` | `examples/sequence-diagram-example.md` | `quality-gates/sequence-diagram-review.yaml` |
| Activity | `spec-kit/activity-diagram.schema.yaml` | `templates/activity-diagram.template.md` | `examples/activity-diagram-example.md` | `quality-gates/activity-diagram-review.yaml` |
| State | `spec-kit/state-diagram.schema.yaml` | `templates/state-diagram.template.md` | `examples/state-diagram-example.md` | `quality-gates/state-diagram-review.yaml` |

## Instructions

1. Decide whether a UML diagram is needed.
   - Use Sequence Diagram for interaction scenarios, participants, messages, responses and sync/async chains.
   - Use Activity Diagram for processes, algorithms, conditions, fork/join and swimlanes.
   - Use State Diagram for object lifecycle, statuses, events, guards and transition actions.
   - Do not force a UML diagram when the requested artifact does not need a visual model.

2. Identify the diagram boundary.
   - Define the interaction, process, algorithm or object lifecycle being diagrammed.
   - Define the expected reader: analyst, developer, tester, architect, product owner or support.
   - Keep one diagram focused on one scenario, process or lifecycle. Split unrelated flows.

3. Collect evidence before writing.
   - Use requirements, contracts, process descriptions, state models, source code, tests, logs, architecture docs and existing diagrams.
   - If evidence is missing, ask clarification questions before inventing behavior.
   - If sources conflict, record the conflict in the working layer and do not silently choose a winner.

4. Run mandatory clarification before writing the final artifact.
   - Build a gap list across all relevant categories before asking questions.
   - Ask as many focused questions as needed to make the diagram correct. Do not artificially limit the batch to 5-7 questions when more gaps exist.
   - Group questions by category: participants, interactions, parallel behavior, **errors and alternative paths**, aggregation, traceability, visual markers.
   - **Always include the error/alternative-path category**, even when the user request mentions only successful flow.
   - Prefer interactive structured questions when the environment supports them.
   - If several categories have gaps, ask them in one structured message with numbered sections.
   - If the user explicitly asks for a quick draft, write a draft and put unanswered items into `Gaps и допущения` as `GAP-UML-*` rows.
   - If the user did not ask for a draft, do not produce the final diagram while critical gaps remain unanswered.
   - Do not deliver a happy-path-only diagram as the final artifact when error behavior is still unknown. Either ask first, or mark the artifact as draft/incomplete.

5. Mark unresolved gaps and assumptions.
   - If required information is still missing after clarification, write a precise `GAP-UML-NNN` marker in the affected field.
   - Add the same `GAP-UML-NNN` to the `Gaps и допущения` table with:
     - where the gap was found;
     - what exact information is missing;
     - how to close it manually.
   - If you infer a value from weak evidence or from a reasonable but unconfirmed assumption, mark it with `ASM-UML-NNN`.
   - Add the same `ASM-UML-NNN` to the `Gaps и допущения` table with what was assumed and how to confirm it.
   - If the user describes participants in business words but does not provide exact technical names, do not silently normalize them to service names, aliases, endpoints, topics, queues, event names, status codes or state names.
   - If you choose a likely technical identifier anyway, mark it as an assumption, for example `очередь уведомлений (предполагаемое имя topic: notification.events, ASM-UML-001)`.
   - This applies to service names, participant aliases, operation names, endpoints, topics, queues, event names, state names, transition events, guards and error statuses.

6. Apply common diagram requirements.
   - Every diagram must have a title.
   - Every diagram must have a caption or short purpose.
   - Every diagram must have a legend explaining notation, colors or special markers.
   - Numbered diagram elements must correspond to numbered text steps.
   - Prefer PlantUML and `.puml` / `.svg` storage for UML diagrams.
   - Keep PlantUML valid and renderable between `@startuml` and `@enduml`.

7. Apply type-specific rules.
   - Sequence: use correct arrows, participants, lifelines, activation bars for synchronous calls and fragments such as `alt`, `opt`, `loop`, `par`, `break`, `ref`.
   - Sequence: when error behavior is known, show alternative paths with `alt`, `opt`, `loop`, `break` rather than hiding them in prose only.
   - Sequence: before submitting, run the mandatory **Lifeline Logic** audit message by message.
   - Sequence: only actor may send without activation; every participant message requires live lifeline and `++` on sync callee.
   - Activity: use `start`, `stop`, actions, decisions, explicit branch labels, fork/join or merge when parallel behavior exists.
   - Activity: when error behavior is known, show failure branches with `if/else`, terminal outcomes and return paths.
   - State: use `[*]` initial/final states, transitions in `event [guard] / action` format and state actions such as `entry/`, `exit/`, `do/` when known.

8. Run quality gates.
   - Always apply `quality-gates/uml-diagram-review.yaml`.
   - Then apply the type-specific gate.
   - For Sequence diagrams, explicitly verify lifeline and activation balance before approval.
   - If any blocking check fails, do not mark the diagram as done.

## Lifeline Logic (mandatory for Sequence)

This section is the canonical lifeline specification. Run it **message by message** before submitting any Sequence Diagram.

### Definitions

| Term | Meaning |
|---|---|
| **Live lifeline** | Participant has an open activation bar (`++`, `activate`, or stacked `++` level) for the current processing scope |
| **Empty lifeline** | Participant has **no** activation bar at the message timestamp |
| **Dead lifeline** | Participant had activation, but it was already closed by `--`, `deactivate`, or `return` |

A Sequence Diagram is **incorrect** if any message starts from a dead/empty lifeline (when not allowed) or arrives at a dead/empty lifeline (when not allowed).

### Rule 1 — Only `actor` may send without activation

| Participant kind | May send message without activation bar? |
|---|---|
| `actor` (User, Client, external user) | **Yes** — only actors may initiate from empty lifeline |
| `participant` (Frontend, Backend, Service, BFF, API) | **No** — every outbound message requires live activation |
| `queue` with consume/processing | **No** — same as participant when processing |

**Corollary:** `Frontend`, `Backend`, and every service **must** have a live activation bar at the moment they send or receive a synchronous message or return.

```plantuml
' CORRECT
User -> FE: 1. click
activate FE
FE --> User: 2. render page

' WRONG — FE sends/replies without activation
User -> FE: 1. click
FE --> User: 2. render page
```

### Rule 2 — Every sync call opens callee activation with `++`

Any synchronous call `A -> B: message` between participants (not actor-only UI trigger) must use:

```plantuml
A -> B ++: message
```

The callee `B` must receive the call on an **opening** activation bar. A plain `A -> B:` without `++` leaves callee lifeline **empty** at receive time — **forbidden** for participants.

**Forbidden:**

```plantuml
FE -> Backend: POST /search
Backend -> RecSvc: getRecommendations()
```

**Required:**

```plantuml
FE -> Backend ++: POST /search
Backend -> RecSvc ++: getRecommendations()
```

### Rule 3 — Every sync return closes callee and lands on live caller

```plantuml
Callee --> Caller --: response
```

At send time: **Callee must be live**. At receive time: **Caller must be live** (waiting scope).

**Forbidden:**

```plantuml
Backend --> FE: response
FE <-- Backend: timeout
```

when Backend or FE has no activation bar at that point.

Use `--` on return when closing callee activation.

### Rule 4 — No arrow from dead lifeline

If participant `A` already closed activation, `A` must not send any processing message until reopened with `++` / `activate`.

**Forbidden:** downstream call after `--` without reopen in the same operand.

### Rule 5 — No arrow to empty/dead lifeline

Do not draw a message to a participant with empty lifeline when that participant is supposed to process the message.

**Forbidden:**

```plantuml
FE -> Backend: failed attempt
note over Backend: inactive
FE <-- Backend: timeout
```

Here the arrow goes to empty Backend and return comes from empty Backend — **reject**.

**Allowed alternatives for client-side timeout / connection failure (Backend never processes):**

```plantuml
' Option A — self-call on live Frontend only
FE -> FE ++: awaitBackendResponse(timeout)
FE -> FE --: timeout / connection error
FE --> User: error message

' Option B — Backend accepted request but returned error
FE -> Backend ++: POST /search
Backend --> FE --: 503 / timeout
```

Never draw cross-participant arrows to a participant that does not open activation for that hop.

### Rule 6 — `activate FE` immediately after `User -> FE` before any FE message

Pattern for every user interaction turn:

```plantuml
User -> FE: [user action]
activate FE
FE -> Backend ++: ...
' or
FE --> User: ...
' or
FE -> FE ++: internal step
deactivate FE
```

Every `FE --> User`, `FE -> Backend ++`, `FE -> FE ++` requires FE to be live.

### Rule 7 — Fragment rules (`alt`, `loop`, `par`)

1. Open activation **inside** the operand that uses it.
2. All operands of one `alt` must end with the same activation state at merge-point.
3. Do not close callee in operand A and draw callee work in operand B without reopen.
4. UI render after backend response stays inside the success operand.
5. Parent activation in `par` stays live until join + merge complete.

### Rule 8 — Error paths

| Error type | How to draw |
|---|---|
| Backend never accepted request (connection failed, DNS, client timeout before accept) | **Only live Frontend** — `FE -> FE ++` / `--` or `note over FE`; **no arrow to Backend** |
| Backend accepted and returned error | `FE -> Backend ++` … `Backend --> FE --: error` — both live |
| Downstream service failed inside Backend | Backend stays live; inner service `--`; Backend handles fallback on live lifeline |
| Retry | Each attempt that reaches Backend: `FE -> Backend ++` … `Backend --> FE --`; client-only retry wait: `FE -> FE ++` |

### Mandatory message-by-message audit

For **each arrow** in order:

1. **Source:** is it `actor` (allowed empty) or participant (must be live)?
2. **Target:** if sync call — does `++` open activation? If return — is target live and waiting?
3. **After message:** does activation state still match the process?
4. **Visual check:** would PlantUML show this arrow starting/ending on an activation bar?

| Result | Action |
|---|---|
| Participant sends without activation | Add `activate` before message or move message inside live scope |
| Call to empty lifeline without `++` | Change to `-> Target ++` or remove arrow |
| Return from empty lifeline | Remove or precede with `++` scope on sender |
| Return to empty lifeline | Add `activate Caller` before original call |
| Error path arrows to inactive Backend | Replace with `FE -> FE ++` client-side timeout pattern |

### Core balance rules (still required)

1. Every `++` / `activate` has matching `--` / `deactivate` / `return`.
2. No open activation at diagram end (unless intentionally still processing).
3. Nested calls close inside-out before outer `--`.
4. Pure async `->>` does not use blocking activation on caller/callee incorrectly.

### Nested subprocesses and stacked activations

When a participant performs bounded internal work, use `group` and stacked self-calls on **live** lifeline:

```plantuml
group [Search Backend] Parallel fetch and merge
  Backend -> RecSvc ++: getRecommendations()
  RecSvc --> Backend --: RecommendedProducts[]
  Backend -> Backend ++: mergeFeed()
  return
end
```

| Mechanism | PlantUML | When to use |
|---|---|---|
| `group` | `group [label] ... end` | Bounded subprocess on diagram |
| `ref` | `ref over A, B : Name` | Reusable subprocess on another diagram |
| Self-call | `A -> A ++: step` + `return` | Internal step; stacked bar on same live lifeline |

### Canonical patterns

**Actor → Frontend → Backend (happy path):**

```plantuml
User -> FE: 1. submit search
activate FE
FE -> Backend ++: 2. POST /search
Backend -> RecSvc ++: 2.1 getRecommendations()
RecSvc --> Backend --: products
Backend --> FE --: 3. SearchFeedResponse
FE --> User: 4. render feed
deactivate FE
```

**Client-side timeout (Backend never activated):**

```plantuml
User -> FE: 1. submit search
activate FE
FE -> FE ++: 2. awaitBackendResponse(timeout)
FE -> FE --: connection error / timeout
FE --> User: 3. "Попробуйте позже"
deactivate FE
```

**Backend error response (Backend was live):**

```plantuml
activate FE
FE -> Backend ++: 1. POST /search
Backend --> FE --: 503 Service Unavailable
FE --> User: 2. error message
deactivate FE
```

**Retry loop with live lifelines:**

```plantuml
activate FE
loop retry (max 3)
  alt backend available
    FE -> Backend ++: POST /search
    Backend --> FE --: SearchFeedResponse
    FE --> User: render feed
    break
  else backend unavailable before accept
    FE -> FE ++: awaitBackendResponse(timeout)
    FE -> FE --: timeout
    opt attempt = 3
      FE --> User: error message
    end
  end
end
deactivate FE
```

Do not mark a Sequence diagram as done until the message-by-message lifeline audit passes.

## Mandatory Clarification Checklist

Before drafting, check every item below. If any item is unknown and affects diagram correctness, ask about it.

### Common for all diagram types

- Diagram type: Sequence, Activity or State.
- Scenario scope: what is included and excluded.
- Textual traceability: which numbered steps the diagram must match.
- Visual markers or colors: are special markers needed on the diagram.

### Sequence Diagram — participants and interactions

- Exact names and aliases of all participants: frontend, services, queues, external systems, sources.
- Who initiates each hop and in which direction.
- Exact operation, endpoint, method, RPC, query or event name for **each** message.
- Protocol for each hop: REST, gRPC, GraphQL, SOAP, Kafka, internal call or other.
- Sync vs async for **each** message: `->`, `->>`, `-->`.
- Request parameters and response payload at a level sufficient for the diagram.
- Whether activation bars are needed for each synchronous hop.

### Sequence Diagram — parallel flows

- Which calls run in parallel.
- Whether all parallel branches must complete before continuing (`par` + join).
- What happens if one branch fails while others succeed.
- Whether partial results are allowed on the screen.

### Sequence Diagram — errors and fallback

Ask about these **even if the user did not mention errors**:

- Validation, business and technical errors for each hop.
- HTTP/gRPC/status codes or error names if known.
- Retry count, timeout, backoff, fallback, compensation or rollback behavior.
- What happens when a source returns an invalid, malformed or semantically wrong response.
- What the caller receives when a downstream source fails.
- Whether the whole request fails or degraded/partial response is returned.
- What the user sees on the screen for each failure mode.
- Whether error branches must be shown with `alt`, `opt`, `break` or `loop`.
- For parallel source fetch: behavior when 1 of N sources fails, times out, retries, or returns invalid payload.

When answers are known, model them on the diagram. Do not leave error behavior only in `Gaps и допущения` if the user already confirmed it.

### Sequence Diagram — aggregation and mapping

- Who merges or aggregates responses from multiple sources.
- Aggregation, sorting, filtering or deduplication rules if relevant.
- Which source is new or changed relative to the previous process.

### Activity Diagram — process structure

- Start trigger and successful end state.
- Actors or swimlanes if several systems perform actions.
- Decision conditions and branch labels.
- Whether parallel branches use `fork/end fork` or `fork/end merge`.
- Error branches and terminal outcomes.
- Return path after a failed branch.
- Retry loops, timeout exits and invalid-response branches when relevant.

When answers are known, show alternative paths on the Activity diagram with explicit `if/else` branches and terminal outcomes.

### State Diagram — lifecycle

- Full state list, initial state and terminal states.
- Events, guards and transition actions.
- Entry, exit and do actions when known.
- Nested or parallel states if relevant.

## Domain-Aware Clarification

Detect the diagram domain from user wording and ask domain-specific questions before drafting.

| Domain | Trigger words | Questions to ask |
|--------|---------------|------------------|
| Multi-service interaction / chain | сервис, frontend, API, запрос, ответ, screen, backend | Точные имена сервисов? Имена endpoint/method на каждом hop? Sync или async? Кто инициирует каждый вызов? |
| External source / integration | источник, интеграция, BPH, get, events, linked, contract | Точное имя источника? Точное имя операции/endpoint/event? Протокол? Что приходит в ответ? Что делать при ошибке источника? |
| Parallel source fetch | параллель, fork, несколько источников, 5 запросов | Список всех источников? Ждем все ответы или достаточно одного? Что показываем при частичном успехе? Кто агрегирует ответы? |
| UI screen flow | экран, frontend, пользователь, история, отображение | Какой экран? Какой триггер открытия? Что показываем при пустом результате? Что показываем при ошибке одного источника? |
| Error handling | ошибка, fallback, timeout, retry, недоступен, partial | Какие ошибки возможны на каждом шаге? Что видит пользователь? Падает весь запрос или degraded response? Есть retry/timeout? |
| Object lifecycle | статус, состояние, lifecycle, переход | Полный список состояний? События переходов? Guards? Terminal states? |

If several domains apply, ask a mixed batch covering all of them. Prefer completeness over brevity.

## Mandatory Error-Path Clarification

For Sequence and Activity diagrams with service calls, integrations or parallel branches, error clarification is **mandatory**, not optional.

Ask even when the initial user message contains only happy path.

Minimum error questions:

1. Какие ошибки возможны на каждом hop: validation, business, technical?
2. Есть ли timeout? Сколько? Что происходит после timeout?
3. Есть ли retry? Сколько попыток? На каких шагах? Retry только для technical errors или и для business?
4. Что делать, если источник недоступен?
5. Что делать, если ответ пришел, но payload invalid / malformed / semantically wrong?
6. Что видит пользователь или caller при каждом типе ошибки?
7. Для parallel fetch: что делать, если упал 1 из N источников?
8. Весь сценарий завершается ошибкой, возвращается partial/degraded response, или продолжается без данных этого источника?
9. Нужно ли показывать эти ветки на Sequence через `alt` / `opt` / `loop` / `break`?
10. Нужно ли показывать failure paths на Activity через `if/else` и terminal outcomes?

Do not consider the diagram complete until either:

- error/alternative paths are modeled on the diagram, or
- the user explicitly requested a draft and remaining unknowns are captured as `GAP-UML-*`.

## Interactive Clarification Mode

When required information is missing, prefer a structured question form over silently drafting with assumptions.

Classify gaps before asking:

| Gap type | Use for | Question style |
|----------|---------|----------------|
| Choice gap | Known finite options | Single choice |
| Multi-choice gap | Several applicable values | Multi-select |
| Text gap | Exact names, endpoints, IDs, rationale | Free text |
| Evidence gap | Contract, schema, existing diagram | Free text or link request |

Recommended error-handling choice options:

```text
Если один из параллельных источников недоступен:
- весь запрос падает с ошибкой
- возвращаем partial/degraded response
- скрываем операции только этого источника
- retry источника
- fallback на cached/legacy data
- другое

Если источник вернул invalid/malformed response:
- считаем источник failed
- игнорируем только invalid records
- retry запрос
- fail all
- другое

Если истек timeout:
- retry
- fail all
- partial/degraded response
- другое
```

## Clarification Examples

### Short integration request

User: `есть два сервиса, между ними асинхронное взаимодействие`

Ask before drafting:

```text
Нужно уточнить Sequence Diagram:

1. Участники: как называются оба сервиса и какие aliases использовать?
2. Инициатор: кто отправляет сообщение — Service A -> Service B или наоборот?
3. Режим: это только async (`->>`), или есть sync request/response (`->` / `-->`)?
4. Транспорт: queue/topic/event, HTTP callback, gRPC stream или другой механизм?
5. Имена: точное имя операции, endpoint, topic или event?
6. Ответ: есть ли response/ack или fire-and-forget?
7. Ошибки: что происходит при недоступности consumer/producer или при invalid payload?
```

### Operation history with parallel sources

User: `frontend -> screen api -> operation history -> 5 sources, one is BPH get link events`

Ask before drafting:

```text
Нужно уточнить Sequence и Activity Diagram:

1. Участники: точные имена Frontend, Screen API, Operation History Service и всех 5 источников?
2. Вызовы: точные endpoint/method names для Frontend -> Screen API и Screen API -> Operation History?
3. BPH: точное техническое имя операции `get link events` — endpoint, RPC, method или event name?
4. Остальные 4 источника: как они называются и какие у них операции?
5. Параллельность: ждем ответы от всех 5 источников или partial response допустим?
6. Агрегация: кто и по какому правилу объединяет ответы источников?
7. Ошибки: что происходит, если один источник недоступен, вернул timeout или business error?
8. UI: что видит пользователь при partial success, empty result и total failure?
9. Sync/async: все 5 вызовов синхронные или часть async?
10. Нумерация: нужно ли показывать error branches на Sequence (`alt`/`break`) и failure paths на Activity?

### Error paths — обязательный блок

11. Что происходит, если один из 5 источников недоступен?
12. Что происходит при timeout?
13. Есть retry? Сколько попыток и для каких ошибок?
14. Что делать, если BPH/DSM/EMS/BIO/IPO вернули invalid/malformed/semantically wrong response?
15. Что видит пользователь при partial success, empty result и total failure?
16. Fail all или partial/degraded feed?
```

## Output Discipline

For each UML diagram artifact, produce or update:

1. Clarification questions first, unless the user explicitly requested a draft.
2. Final Markdown artifact using the relevant template.
3. PlantUML code block, and optionally a `.puml` file when the project flow expects diagrams as code.
4. Review status based on the general and type-specific quality gates.

Use Russian for reader-facing explanations by default. Keep technical identifiers, service names, endpoint names, event names, field names, statuses and source IDs in their original spelling.

## Forbidden Without Evidence

- Participants, services, queues or external systems.
- Operation names, endpoints, topics, methods or message names.
- Retry, timeout, fallback, rollback, compensation, Saga or idempotency behavior.
- State names, status codes, guards and transition actions.
- Timings, SLA/SLO, latency and throughput numbers.
- Colors or markers meaning `[NEW]`, `[CHG]`, deleted, bottleneck or manual operation.
- Error branches and degraded/partial response behavior.

If a canonical example contains such details but the project evidence does not, do not invent them. Ask the user first. If the user asks to proceed with a draft, keep the diagram narrower and record the gap explicitly.
