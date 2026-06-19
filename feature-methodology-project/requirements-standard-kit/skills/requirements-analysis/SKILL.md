---
name: requirements-analysis
description: Collects and analyzes feature requirements using source evidence. Use when identifying requirement sources, stakeholders, business rules, constraints, feature goals, SMART criteria, metrics, contradictions, decisions and rationale.
disable-model-invocation: true
---

# Requirements Analysis

## Purpose

Use this skill when an agent must collect, normalize or document the initial requirements for a feature. The skill defines the workflow. The required output format is defined by the spec, template, canonical example and quality gate in this kit.

This skill is not a substitute for evidence. Do not invent requirement sources, stakeholders, metrics, business value, business rules, constraints, decisions or rationale.

The final artifact must follow the current requirements standard:

- Use the title format `#### Анализ требований — <Название фичи>`.
- Do not expose source standard IDs in the final artifact.
- Keep source, stakeholder, SMART and contradiction data explicit.
- If contradictions are not found, state `Противоречия не выявлены` in the contradictions table.
- Mark missing information with precise `GAP-REQ-NNN` IDs.
- Mark weak assumptions with precise `ASM-REQ-NNN` IDs.
- Add every gap and assumption to the `Gaps и допущения` table.

## Required Files

Before writing a requirements artifact, read the relevant files:

| Artifact | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| Requirements analysis | `spec-kit/requirements-analysis.schema.yaml` | `templates/requirements-analysis.template.md` | `examples/operation-history-requirements-example.md` | `quality-gates/requirements-review.yaml` |

## Instructions

1. Decide whether requirements analysis is needed.
   - Use this kit at the start of a feature flow.
   - Use it when the request mentions a new feature, change request, business goal, stakeholder request, metric, source document, contradiction or unclear requirement.
   - Do not use it for a narrow artifact-only task where source, goal and scope are already fixed by a higher-level document.

2. Identify the requirement source.
   - Capture the source type: interview, document, Jira task, product request, incident, analytics, support request or another source.
   - Capture source identifier, link, author/initiator and date/version when available.
   - If source is unknown, ask before writing the final artifact unless the user explicitly wants a draft.

3. Identify stakeholders.
   - List all known stakeholders interested in the feature.
   - For each stakeholder, capture role, interest/expectation and influence or responsibility.
   - Do not invent stakeholders. Ask if the feature clearly affects users, product, operations, support, compliance, security or engineering but stakeholders are not named.

4. Extract business rules and constraints.
   - Business rules describe domain logic that must hold.
   - Constraints describe limits, dependencies, regulation, architecture, timelines, channels or operational boundaries.
   - Keep rules and constraints traceable to user input or evidence.
   - If a rule or limit is implied but not specified, ask for the exact rule, threshold, unit, period or owner.

5. Formulate the feature goal.
   - The goal must answer:
     - What business problem does the feature solve?
     - What value does it bring to the user?
     - Which metrics should improve?
   - If one of these is missing, ask a clarification question.
   - Do not invent numeric metric targets. If the metric is known but target is unknown, write that the target requires confirmation.

6. Check SMART.
   - Specific: goal is concrete.
   - Measurable: metric or measurement method is identified.
   - Achievable: goal looks feasible within known constraints.
   - Relevant: goal is connected to business/user value.
   - Time-bound: deadline, release, quarter or review point is known.
   - If a SMART criterion cannot be confirmed, mark it with `GAP-REQ-NNN` and add the same ID to `Gaps и допущения`.

7. Analyze contradictions.
   - Compare requirements from different sources and stakeholders.
   - If requirements conflict, document both requirements, both sources, decision and rationale.
   - Escalate unresolved contradictions to Product Owner or the named decision owner.
   - If no contradictions are known, explicitly state that contradictions are not identified.

8. Ask clarification questions for critical gaps before writing the final artifact.
   - Ask focused questions only for gaps that affect scope, goal, stakeholder alignment, business rules, constraints, SMART criteria or conflict resolution.
   - If multiple gaps exist, group questions by category: source, stakeholders, goal, metrics, rules/constraints and contradictions.
   - Detect the task domain and ask minimal domain-specific questions needed to make the requirement clear.
   - Prefer interactive structured questions when the environment supports them.
   - Use choice questions for known option sets, multi-choice questions for lists of affected items and free-text questions for links, IDs, rationale and custom rules.
   - Do not ask more than 5-7 questions in one batch unless the user explicitly asks for exhaustive discovery.
   - If the user explicitly asks for a quick draft, write a draft and put unanswered items into `Gaps и допущения` as `GAP-REQ-*` rows.

9. Mark unresolved gaps and assumptions.
   - If required information is still missing after clarification, write a precise `GAP-REQ-NNN` marker in the affected field.
   - Add the same `GAP-REQ-NNN` to the `Gaps и допущения` table with:
     - where the gap was found;
     - what exact information is missing;
     - how to close it manually.
   - If you infer a value from weak evidence or from a reasonable but unconfirmed assumption, mark it with `ASM-REQ-NNN`.
   - Add the same `ASM-REQ-NNN` to the `Gaps и допущения` table with what was assumed and how to confirm it.
   - If the user describes a business concept but does not provide an exact technical identifier, do not silently normalize it to a field, status, enum, endpoint, metric or system name.
   - If you choose a likely technical identifier anyway, mark it as an assumption, for example `дата изменения товара (предполагаемое поле: updated_at, ASM-REQ-001)`.
   - This applies to field names such as `created_at`, `updated_at`, status codes, metric names, source names, endpoint names, event names and database/entity names.
   - Prefer business wording when exact technical names are unknown. Example: write `дата изменения товара` instead of `updated_at` unless the exact field was provided or marked with `ASM-REQ-*`.
   - Do not write vague phrases like `требует уточнения`, `не указано`, or `unknown` without a linked GAP ID.
   - If no gaps or assumptions remain, write `Gaps не выявлены` in the `Gaps и допущения` table.

10. Run the quality gate.
   - Apply `quality-gates/requirements-review.yaml`.
   - If any blocking check fails, do not mark the artifact as done.

## Clarification Triggers

Ask the user follow-up questions when any of these are unknown:

- Requirement source: type, link/ID, author, version or date.
- Stakeholders: who requested, who approves, who is affected, who operates or supports.
- Business problem: what pain, risk, cost or opportunity is being addressed.
- User value: what changes for the user or internal actor.
- Metrics: conversion, time, error rate, cost, SLA, adoption, retention or another measurable effect.
- Business rules: thresholds, eligibility, statuses, limits, formulas, priority rules.
- Constraints: timeline, architecture boundary, regulation, channel, dependency, migration, rollout.
- Contradictions: two sources disagree, two stakeholders expect different behavior, or decision owner is unknown.

Use concise grouped questions. Example:

```text
Нужно уточнить требования:

1. Источник: это Jira-задача, интервью, документ или продуктовая постановка?
2. Стейкхолдеры: кто владелец решения и кто принимает результат?
3. Цель: какую бизнес-проблему решаем и какую метрику хотим улучшить?
4. Ограничения: есть ли сроки, каналы, архитектурные или регуляторные ограничения?
5. Противоречия: есть ли разные ожидания у продукта, бизнеса, поддержки или разработки?
```

If the user cannot answer or asks to proceed, keep remaining unknowns as explicit `GAP-REQ-*` rows in `Gaps и допущения`. Do not turn gaps into confident claims.

## Domain-Aware Clarification

Before writing the final requirements artifact, detect the task domain from the user's wording. Ask only the minimum domain-specific questions needed to clarify the requirement. Do not perform full specialized analysis here; detailed artifacts belong to downstream kits.

| Domain | Trigger words | Minimal questions |
|--------|---------------|-------------------|
| Integration / source / API / event | источник, интеграция, API, endpoint, event, Kafka, topic, contract, система, get, send, receive | Есть ли ссылка на контракт/schema/API/event? Кто владелец источника или контракта? Какие объекты или события приходят? Что включается и что исключается? Контракт подтвержден или draft? |
| Data / database / model | БД, таблица, модель, сущность, поле, миграция, маппинг, агрегация, дедупликация | Какая сущность меняется? Какие поля добавляются/меняются? Нужна ли миграция? Есть ли правила маппинга? Есть ли обратная совместимость? |
| Sorting / filtering / search | сортировка, фильтр, поиск, порядок, дата создания, дата изменения, null, empty | Какое поле или бизнес-понятие используется? Какое направление? Что делать с пустыми значениями? Где применяется изменение? Есть ли fallback? |
| UI / screen / frontend | экран, UI, кнопка, форма, состояние, сообщение, пользователь видит | Какой экран меняется? Кто пользователь? Какие состояния нужны? Что показывать при пустом результате и ошибке? Откуда приходят данные? |
| Business rule / validation | правило, лимит, порог, условие, валидация, eligibility, restriction | Какое точное условие? Какие пороги/единицы/периоды? Какие исключения? Кто владелец правила? Где правило подтверждено? |
| NFR / performance / reliability | SLA, SLO, latency, timeout, retry, нагрузка, производительность, надежность | Какая метрика? Целевое значение? Нагрузка? Как измерять? Что считается нарушением? |
| Security / access | роль, доступ, permission, авторизация, персональные данные, маскирование | Какие роли? Какие права? Какие данные чувствительные? Нужна ли маскировка? Где подтверждено правило доступа? |
| Reporting / analytics | отчет, аналитика, метрика, BI, дашборд, событие аналитики | Какая метрика или отчет? Кто потребитель? Какой источник данных? Как часто обновлять? Какие срезы нужны? |

If several domains apply, ask a compact mixed batch and keep it to the most important 5-7 questions.

Use domain questions to clarify requirements only. Examples:

```text
Для задачи про новый источник:
1. Есть ли ссылка на контракт/schema/API/event?
2. Кто владелец источника и контракта?
3. Какие объекты должны приходить и какие исключаются?
4. Контракт подтвержден или draft?

Для задачи про БД:
1. Какая сущность или таблица меняется?
2. Какие поля добавляются/изменяются?
3. Нужна ли миграция существующих данных?
4. Есть ли правила маппинга и обратная совместимость?
```

## Interactive Clarification Mode

When required information is missing, prefer a structured question form over a plain text list if the environment supports it.

Classify gaps before asking:

| Gap type | Use for | Question style |
|----------|---------|----------------|
| Choice gap | Known finite options | Single choice |
| Multi-choice gap | Several applicable values | Multi-select |
| Text gap | Link, ID, exact wording, rationale | Free text |
| Evidence gap | Source document or confirmation needed | Free text or explicit `unknown` option |

Recommended choice options:

```text
Источник требования:
- Jira
- Product request
- Interview
- Document
- Analytics
- Support request
- Incident
- Other
- Unknown

Статус противоречий:
- Противоречия не выявлены
- Есть конфликтующие требования
- Нужно проверить
- Unknown

SMART completeness:
- Достаточно для draft
- Не хватает метрик
- Не хватает срока
- Не хватает бизнес-ценности
- Не хватает ограничения достижимости

Тип ограничения:
- Timeline
- Architecture
- Regulation
- Channel
- Dependency
- Migration
- Rollout
- Other
```

For sorting-related requirements, use domain-specific choices when relevant:

```text
Направление сортировки:
- По убыванию
- По возрастанию
- Как сейчас, меняется только поле
- Unknown

Поведение при пустом значении поля сортировки:
- Использовать fallback field
- Помещать в конец списка
- Помещать в начало списка
- Исключать из выдачи
- Unknown

Область изменения:
- Все списки
- Один экран
- Один endpoint/query
- Нужно уточнить
```

After the user answers:

1. Merge selected options into the working requirements shape.
2. Ask one short follow-up only if a selected option creates a new critical gap.
3. Produce the final artifact only when blocking gaps are resolved or the user explicitly asks for a draft with gaps.
4. Keep unanswered items visible as `GAP-REQ-*` rows in `Gaps и допущения`, not as confident requirements.

## Output Discipline

For each requirements artifact, produce or update:

1. Final requirements analysis artifact using `templates/requirements-analysis.template.md`.
2. Review status based on `quality-gates/requirements-review.yaml`.
3. Remaining questions/gaps as `GAP-REQ-*` rows in `Gaps и допущения` when relevant.

Use Russian for reader-facing explanations by default. Keep Jira IDs, source IDs, metric names, system names and technical identifiers in their original spelling.

## Final Artifact Format

Use this exact top-level shape:

```markdown
#### Анализ требований — [Название фичи]

**Источник требования:**

**Стейкхолдеры:**

**Бизнес-правила и ограничения:**

**Цель фичи:**

**SMART-проверка цели:**

**Противоречия и решения:**

**Gaps и допущения:**
```

The final artifact should match `examples/operation-history-requirements-example.md` in section order, table granularity and explicit handling of unknown or conflicting requirements.

## Gap And Assumption Marking

Use these markers in final artifacts:

```text
GAP-REQ-001
ASM-REQ-001
```

Use `GAP-REQ-*` when information is missing and must be filled manually.

Examples:

```text
| Дата / версия | GAP-REQ-001 |
| Time-bound | Ограниченная по времени | GAP-REQ-002 |
```

Use `ASM-REQ-*` when the artifact contains an unconfirmed assumption.

Examples:

```text
| Инициатор | Product Owner (ASM-REQ-001) |
| Relevant | Релевантная | Предположительно влияет на конверсию (ASM-REQ-002) |
| BR-01 | Бизнес-правило | Сортировать по дате изменения товара (предполагаемое поле: updated_at, ASM-REQ-003) |
```

Every `GAP-REQ-*` and `ASM-REQ-*` used in the artifact must have a matching row in `Gaps и допущения`.

## Forbidden Without Evidence

- Requirement source, author, link or Jira ID.
- Stakeholder names, roles or approval responsibility.
- Metric targets and deadlines.
- Business rules, thresholds, limits or formulas.
- Regulatory, security, operational or architectural constraints.
- Product Owner decisions and rationale.

If the canonical example contains such details but the project evidence does not, do not invent them. Ask a clarification question or keep the item as a `GAP-REQ-*` row in `Gaps и допущения`.

## Forbidden In Final Artifact

- Source standard IDs.
- Unresolved markers such as `TODO`, `TRACE-`, `OQ-`, `CONFLICT-` or `[ТРЕБУЕТ УТОЧНЕНИЯ]`.
- Confident metric targets, stakeholder decisions or business rules without evidence.
- Vague unknown markers without `GAP-REQ-*`.
