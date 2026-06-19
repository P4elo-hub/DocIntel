---
name: use-case-analysis
description: Analyzes and documents Use Cases using source evidence. Use when describing actor goals, user scenarios, system behavior, happy paths, alternative scenarios, business rules, preconditions, postconditions, or relationships between Use Cases.
disable-model-invocation: true
---

# Use Case Analysis

## Purpose

Use this skill when an agent must analyze or write a Use Case. The skill defines the workflow. The required output format is defined by the spec, template, canonical example and quality gate in this kit.

This skill is not a substitute for evidence. Do not invent business rules, validation rules, limits, actor permissions, error behavior, technical fallback, retry behavior, statuses or side effects.

The final artifact must follow the current Use Case standard:

- Use the title format `#### Use Case — <Название>`.
- Do not write `Пример:` in the title.
- Do not expose source standard IDs such as `СТД-*` in the final artifact.
- Use markdown-safe relationship values: `include`, `extend`, `Generalization`.
- Do not use angle-bracket relationship notation in Markdown output.

## Required Files

Before writing a Use Case artifact, read the relevant files:

| Artifact | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| Use Case | `spec-kit/use-case.schema.yaml` | `templates/use-case.template.md` | `examples/transfer-between-accounts-use-case-example.md` | `quality-gates/use-case-review.yaml` |

## Instructions

1. Decide whether a Use Case is needed.
   - Use a Use Case when the request contains an actor goal, scenario, business process, behavior change, alternative path, exception handling, UI flow or system reaction.
   - Do not force a Use Case for pure schema, configuration, copy, documentation or internal refactoring changes without behavior.
   - If another kit requires AS IS or TO BE behavior, use this kit for the scenario body.

2. Identify the scenario boundary.
   - Define the actor and the actor's goal.
   - Define the trigger that starts the scenario.
   - Define the successful end state.
   - Keep one Use Case focused on one actor goal. Split separate goals into separate Use Cases.

3. Collect evidence before writing.
   - Product requirements, Jira tasks, process descriptions, UI mockups, user stories, acceptance criteria, API contracts, code, tests, logs and existing documentation can be evidence.
   - If evidence is missing, ask clarifying questions before inventing behavior.
   - If sources conflict, record the conflict in the working layer and do not silently choose a winner.

4. Ask clarification questions for gaps before writing the final artifact.
   - If the user only gives a happy path sketch, do not produce a final Use Case immediately.
   - First identify missing business rules, validations, limits, permissions, state transitions, alternative branches, error handling and boundary cases.
   - Ask focused questions for the missing pieces that affect scenario correctness.
   - If a business rule is implied but not specified, ask for the exact rule and where it applies.
   - If a limit is missing, ask for the threshold, unit, currency, period or default behavior.
   - If a branch is mentioned but the outcome is unclear, ask what the system should do and whether the scenario returns to a step or ends unsuccessfully.
   - If an actor action can fail, ask what validation, business and technical failures must be described.
   - If a related Use Case is implied, ask whether it is `include`, `extend` or `Generalization`.
   - If multiple gaps exist, group questions by category: business rules, validations, alternative scenarios, postconditions and relationships.
   - If the user explicitly asks for a draft with known gaps, write a draft but mark it as incomplete in the working response and list the unanswered questions outside the final artifact.

5. Write the Use Case structure.
   - Название must be phrased as an actor goal: verb + object.
   - Actor(s), trigger, preconditions, postconditions, business rules, main scenario, alternative scenarios and relationships are required.
   - Preconditions must be checkable, not vague.
   - Postconditions must cover success, business failure and technical failure when those outcomes are relevant.
   - Use the section order and heading style from `templates/use-case.template.md`:
     - `**Структура Use Case:**`
     - `**Предусловия:**`
     - `**Постусловия:**`
     - `**Бизнес-правила:**`
     - `**Основной сценарий — Happy Path:**`
     - `**Альтернативные сценарии:**`
     - `**Связи между Use Cases:**`
   - Do not add front matter, `Назначение`, `Кратко`, `Связанные артефакты`, evidence tables or traceability sections to the final Use Case artifact unless a higher-level runbook explicitly requires them outside this page.

6. Write the happy path.
   - Use numbered steps: `Шаг 1`, `Шаг 2`, `Шаг 3`.
   - Keep numbering sequential.
   - Each step must be atomic: one action by one actor or by the system.
   - Clearly separate actor actions from system reactions.
   - Attach business rules to the affected step, for example `[BR-01]`.
   - Every condition must be concrete and verifiable.
   - Every branch must explicitly show both paths:
     - `ЕСЛИ [condition]`
     - `ТО [successful continuation]`
     - `ИНАЧЕ`
     - `ПЕРЕЙТИ К альтернативному сценарию Na`
   - Do not use compressed branch notation like `[condition] -> иначе -> Na`.
   - If a condition has multiple failure cases, use explicit `ИНАЧЕ ЕСЛИ` branches and point each branch to its alternative scenario.
   - The successful path must be visible, for example `ТО сценарий продолжается с шага N`, `ТО перейти к проверке BR-N`, or `ТО выполнить [действие]`.

7. Write alternative scenarios.
   - Number each alternative by the branching step: `3a`, `3b`, `10a`.
   - Classify each alternative as validation error, business error, technical error or boundary case.
   - For every alternative, specify either `Возврат к шагу N` or `Сценарий завершается неуспешно`.
   - Do not leave branch references in the main scenario without a matching alternative scenario.

8. Document relationships.
   - Use `include` for mandatory sub-processes and specify the main scenario step.
   - Use `extend` for optional extensions and specify the extension point and condition.
   - Do not use angle-bracket relationship notation in Markdown output because it can render incorrectly.
   - Use generalization only when one Use Case specializes another Use Case.
   - Use the same relationship value in the main scenario and in the relationships table.

9. Run the quality gate.
   - Apply `quality-gates/use-case-review.yaml`.
   - If any blocking check fails, do not mark the Use Case as done.

## Clarification Triggers

Ask the user follow-up questions when any of these are unknown:

- Actor role, permissions or eligibility.
- Trigger that starts the scenario.
- Preconditions that must be true before step 1.
- Success postcondition and unsuccessful postconditions.
- Business rule value, threshold, period, currency, status or formula.
- Validation rule for user input or system input.
- Behavior for empty values, missing data, duplicate action, max/min value or expired state.
- What happens after a failed validation: return to which step, retry, cancel or finish unsuccessfully.
- Technical failure behavior: rollback, retry, pending state, alert, notification or no state change.
- Whether a nested operation is a separate Use Case and which relationship type it has.

Use concise grouped questions. Example:

```text
Нужно уточнить, чтобы закрыть Use Case:

1. Бизнес-правила: какой лимит/порог действует и на каком шаге?
2. Альтернативные сценарии: что делать, если проверка не прошла — вернуть пользователя к шагу N или завершить сценарий?
3. Постусловия: какое состояние системы после бизнес-ошибки и после технической ошибки?
```

## Output Discipline

For each Use Case artifact, produce or update:

1. Working-layer evidence pack or traceability entry when project flow requires it.
2. Final Use Case artifact using `templates/use-case.template.md`.
3. Review status based on `quality-gates/use-case-review.yaml`.

Use Russian for reader-facing explanations by default. Keep technical identifiers, statuses, field names, endpoint names, event names, classes, methods and source IDs in their original spelling.

## Final Artifact Format

Use this exact top-level shape:

```markdown
#### Use Case — [Название]

**Структура Use Case:**

| Элемент | Значение |
|---------|----------|

**Предусловия:**

**Постусловия:**

**Бизнес-правила:**

**Основной сценарий — Happy Path:**

**Альтернативные сценарии:**

**Связи между Use Cases:**
```

The final artifact should match `examples/transfer-between-accounts-use-case-example.md` in section order, table granularity, relationship notation and explicit condition format.

## Forbidden Without Evidence

- Business limits and validation ranges.
- Actor roles and permissions.
- System statuses and state transitions.
- Retry, timeout, rollback or fallback behavior.
- Error text and notification behavior.
- Side effects such as DB writes, events, integration calls and logs.
- Links to other Use Cases.

If the canonical example contains such details but the project evidence does not, do not invent them. Keep the section narrower and record the gap in the working layer.

## Forbidden In Final Artifact

- `Пример:` in the document title.
- `СТД-*` source standard IDs.
- Angle-bracket relationship notation.
- Unresolved markers such as `TODO`, `TRACE-`, `OQ-`, `CONFLICT-` or `[ТРЕБУЕТ УТОЧНЕНИЯ]`.
