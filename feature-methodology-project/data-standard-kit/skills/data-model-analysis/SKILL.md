---
name: data-model-analysis
description: Analyzes and designs database data models using source evidence. Use when describing new or changed entities, tables, collections, attributes, relationships, ER diagrams, constraints, indexes, junction tables, or persistent storage structure for relational and non-relational databases.
disable-model-invocation: true
---

# Data Model Analysis

## Purpose

Use this skill when an agent must analyze, design or document a data model for persistent storage. The skill defines the workflow. The required output format is defined by the spec, template, canonical example and quality gate in this kit.

This skill is not a substitute for evidence. Do not invent entity names, field types, nullable rules, constraints, indexes, FK behavior, cardinality, enum values, default values, storage engine specifics or migration scripts.

The final artifact must follow the current data model standard:

- Use the title format `#### Модель данных — <Название фичи или изменения>`.
- Do not expose source standard IDs such as `СТД-*` in the final artifact.
- ER-diagram in PlantUML is required when the feature changes storage structure.
- Every new or changed entity must have an attribute table.
- Every relationship must be documented in the relationships table with FK or reference semantics.
- Direct N:M relationships are forbidden; use a junction entity/table.
- Mark missing information with precise `GAP-DATA-NNN` IDs.
- Mark weak assumptions with precise `ASM-DATA-NNN` IDs.
- Add every gap and assumption to the `Gaps и допущения` table.

## Required Files

Before writing a data model artifact, read the relevant files:

| Artifact | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| Data model | `spec-kit/data-model.schema.yaml` | `templates/data-model.template.md` | `examples/payment-processing-data-model-example.md` | `quality-gates/data-model-review.yaml` |

The file in `examples/` is based on `standarts_features (3).md` and keeps the standard blocks unchanged. It additionally includes kit sections: `Контекст изменения`, `Сводные таблицы (junction)`, `Область изменения`, `Gaps и допущения`. Use it as the quality reference for ER diagram, entity attribute tables, relationships and kit-specific sections. The agent's final artifact follows `templates/data-model.template.md`, not the example title, `СТД-*` section labels or migration blocks from the standard example.

## Instructions

1. Decide whether a data model artifact is needed.
   - Use this kit when the feature adds, changes or removes persistent entities, attributes, relationships, constraints or indexes.
   - Use it when requirements mention new tables/collections, new fields, status models, audit fields, ownership links or reference data.
   - Do not force a data model for pure UI, copy, API-only DTO changes without persistence impact, or integration mapping without storage change.
   - If another kit implies DB writes or new business objects, check whether this kit is also required.

2. Classify the storage context.
   - Identify storage type: relational SQL, document DB, key-value, graph, wide-column or mixed.
   - Identify target engine when known: PostgreSQL, Oracle, MongoDB, etc.
   - Identify change scope: new entities, changed entities, removed entities, relationship-only change, constraint/index-only change.
   - Adapt terminology without changing logical rules:
     - relational: table, column, PK, FK, index, CHECK;
     - document: collection, field, `_id`, reference/embedded document, compound index;
     - graph: node label, relationship type, properties.
   - If storage type is unknown and affects type notation or relationship mechanics, ask before finalizing.

3. Collect evidence before writing.
   - Existing ER diagrams, DDL, migrations, ORM models, entity classes, OpenAPI schemas tied to persistence, DB exports, analytics specs, requirements and Use Cases can be evidence.
   - Distinguish confirmed current-state entities from proposed TO BE entities.
   - If evidence is missing, run **Clarification-First Mode** before writing the final artifact.
   - If sources conflict, record the conflict in the working layer and do not silently choose a winner.
   - **Never** fill a new or changed entity attribute table from the canonical example alone when the user has not confirmed fields and has not authorized greenfield design.

4. Run Clarification-First Mode before the final artifact.
   - **Default rule:** if the user gives only a short feature sketch, do **not** produce the final data model in the first response.
   - First response must be a compact clarification block or structured questions.
   - Draft without clarification is allowed only if the user explicitly asks for a draft, or explicitly authorizes greenfield design for specific entities/fields.
   - Do not copy field lists from `examples/payment-processing-data-model-example.md` into the final artifact unless the user confirmed them or chose greenfield design for that scope.

   **What to clarify before schema design:**

   | Категория | Что спросить |
   |---|---|
   | Источник схемы | Есть ли DDL, ER, ORM, export существующих `users/orders/...`? |
   | Новые сущности | Какие таблицы/коллекции новые, какие только связаны? |
   | Связи | Cardinality: 1:1, 1:N, нужна ли junction для N:M? |
   | Атрибуты новых сущностей | Какие поля обязательны по бизнесу: статусы, суммы, внешние ID, audit? |
   | Ограничения | CHECK/enum/index в БД или только в приложении? |
   | Контекст | Есть ли Use Case, integration contract, requirements? |

   **Обязательные варианты ответа** — включай их в каждый вопрос про неизвестные поля или сущности:

   ```text
   Как задать схему для [payments / payment_refunds / конкретное поле]:
   A) Пришлю контекст — DDL, ER, ORM, API contract, excerpt из стандарта
   B) Спроектируй сам с нуля — наименуй поля, типы и ограничения; пометь DESIGN-DATA-*
   C) Частично знаю — опишу в свободном тексте, остальное GAP-DATA-*
   D) Пока не знаю — оставь GAP-DATA-* без выдуманных полей
   ```

   When the environment supports structured questions, prefer `AskQuestion` with these options instead of only free text.

   **Authorization rules after answers:**

   | Ответ пользователя | Поведение агента |
   |---|---|
   | `A) Пришлю контекст` | Ждать контекст. Не проектировать поля заранее. Можно описать только подтверждённые сущности и связи без детальной таблицы атрибутов. |
   | `B) Спроектируй сам с нуля` | Можно спроектировать поля, типы, enum, CHECK, index. Каждый такой блок помечать `DESIGN-DATA-NNN` в `Gaps и допущения`. |
   | `C) Частично знаю` | Использовать только подтверждённое. Остальное — `GAP-DATA-*` или `ASM-DATA-*`. |
   | `D) Пока не знаю` | Только `GAP-DATA-*`. Не заполнять attribute table выдуманными колонками. |

   **DESIGN-DATA vs ASM-DATA vs GAP-DATA:**

   - `GAP-DATA-*` — информация отсутствует и не разрешено проектировать.
   - `ASM-DATA-*` — агент предположил без явного подтверждения и без greenfield authorization.
   - `DESIGN-DATA-*` — поля/ограничения спроектированы агентом после явного выбора пользователя «спроектируй сам с нуля».

   If multiple gaps exist, group questions by category: evidence source, entities, attributes, relationships, constraints/indexes, lifecycle.
   Limit to 5–7 questions per batch unless the user asks for exhaustive discovery.

5. Design entities and attributes.
   - Name entities in domain language; use physical names (`snake_case` tables, camelCase document fields) only when confirmed or marked `ASM-DATA-*`.
   - For each new or changed entity, provide attribute table columns:
     - Атрибут
     - Тип
     - Nullable
     - Описание
     - Ограничения
   - Include PK, FK/reference fields, status fields, audit timestamps and business attributes that matter for the feature.
   - Do not invent CHECK constraints, enum lists, precision/scale, default values or index definitions without evidence or `DESIGN-DATA-*` authorization.
   - If a business term maps to a likely technical field (`created_at`, `updated_at`, `status`, `amount`, `currency`), either confirm it, mark `ASM-DATA-*`, or design under `DESIGN-DATA-*`.

6. Design relationships.
   - Document every relevant relationship in the relationships table:
     - Сущность 1
     - Сущность 2
     - Тип связи
     - FK / Reference
     - Описание
   - Allowed cardinalities in final artifact: `1:1`, `1:N`, `N:1`.
   - Do not document raw `N:M`. Replace with junction entity:
     - Entity A `1:N` Junction `N:1` Entity B
   - Junction entity must contain at least:
     - PK (own or composite from references)
     - reference to entity A
     - reference to entity B
     - relationship-specific attributes when applicable (date, status, role, etc.)
   - If ownership or cascade delete behavior is unknown and affects design, ask or mark `GAP-DATA-*`.

7. Draw the ER diagram.
   - Use PlantUML entity notation from the canonical example.
   - Show new/changed entities clearly; highlight new entities when useful.
   - Include PK, important attributes, FK fields and cardinalities.
   - Keep diagram aligned with attribute and relationship tables.
   - For document DB, diagram may show collections and references instead of SQL FK syntax, but logical relationships must still be explicit.

8. Summarize impact scope.
   - List new entities/collections.
   - List changed entities/collections.
   - List removed or deprecated entities if applicable.
   - List affected relationships and notable indexes/constraints introduced by the feature.

9. Mark unresolved gaps, assumptions and authorized designs.
   - If required information is still missing after clarification, write a precise `GAP-DATA-NNN` marker in the affected field or section.
   - Add the same `GAP-DATA-NNN` to `Gaps и допущения` with where found, what is missing and how to close it.
   - If you infer a value from weak evidence, mark `ASM-DATA-NNN` and add it to the same table.
   - If the user authorized greenfield design, mark `DESIGN-DATA-NNN` and list what was designed and on what basis.
   - Do not write vague phrases like `требует уточнения`, `не указано`, or `unknown` without a linked GAP ID.
   - If no gaps, assumptions or authorized designs remain, write `Gaps не выявлены` in `Gaps и допущения`.

10. Run the quality gate.
    - Apply `quality-gates/data-model-review.yaml`.
    - If any blocking check fails, do not mark the artifact as done.

## Clarification-First Mode

**Default:** first response = questions only, not the final artifact.

Produce the final artifact only when at least one is true:

- the user answered the clarification batch;
- the user explicitly chose `B) Спроектируй сам с нуля` for the relevant entity/field scope;
- the user explicitly asked for a draft;
- the user attached sufficient schema evidence (DDL, ER, ORM, contract).

## Clarification Triggers

Ask the user follow-up questions when any of these are unknown:

- Storage type and target DB engine.
- Which entities are new vs changed vs reused from existing model.
- Entity ownership and lifecycle: who creates/owns/deletes records.
- Cardinality and optionality of relationships.
- Whether a many-to-many business relation exists and what junction attributes it needs.
- Status model: allowed values, transitions, need for history/audit.
- Money, quantity, currency, timezone and precision rules.
- Uniqueness and natural keys vs surrogate keys.
- Nullable behavior for optional business data.
- Soft delete, versioning, effective dates or append-only history.
- Index/search needs driven by queries, sorting or filtering.
- Cross-entity invariants that must be enforced in DB vs application layer.
- Whether existing tables/collections must remain backward compatible.
- **Where field definitions come from** for each new/changed entity.

Use concise grouped questions with mandatory answer options. Example:

```text
Нужно уточнить модель данных перед проектированием схемы:

1. Существующая модель
   users, orders, order_items, products — подтверждаете, что они уже есть?
   - Да, структура как в текущей БД — пришлю DDL/ER
   - Да, но детали не важны — показывай только связи с новыми таблицами
   - Нужно уточнить позже

2. Связи orders ↔ payments
   - 1 заказ → много попыток оплаты (1:N)
   - 1 заказ → один успешный платёж (1:1)
   - Спроектируй сам с нуля
   - Пришлю правило в тексте

3. Поля таблицы payments
   A) Пришлю контекст (DDL / contract / requirements)
   B) Спроектируй сам с нуля — наименуй поля, типы, enum, CHECK
   C) Частично опишу в тексте
   D) Пока не знаю — оставь GAP-DATA-*

4. Поля таблицы payment_refunds — те же варианты A/B/C/D

5. Ограничения
   - CHECK/enum/index в PostgreSQL
   - Только на уровне приложения
   - Спроектируй сам с нуля
   - Unknown
```

If the user chooses `B) Спроектируй сам с нуля`, you may design the schema and mark designed blocks with `DESIGN-DATA-*`.

If the user chooses `A) Пришлю контекст`, stop and wait — do not pre-fill attribute tables from the canonical example.

## Output Discipline

For each data model artifact, produce or update:

1. Working-layer evidence pack or traceability entry when project flow requires it.
2. Final data model artifact using `templates/data-model.template.md`.
3. Review status based on `quality-gates/data-model-review.yaml`.

Use Russian for reader-facing explanations by default. Keep entity names, field names, enum values, SQL types, index names and source IDs in their original spelling.

## Final Artifact Format

Use this exact top-level shape:

```markdown
#### Модель данных — [Название]

**Контекст изменения:**

| Элемент | Значение |
|---------|----------|

**ER-диаграмма:**

**Новые и изменённые сущности:**

**Связи между сущностями:**

**Сводные таблицы (junction):**

**Область изменения:**

**Gaps и допущения:**
```

The final artifact should match the **data model sections** of `examples/payment-processing-data-model-example.md` in table granularity, PlantUML style, relationship notation, impact scope and gaps/assumptions handling. Do not copy the example title, `СТД-*` section labels or migration blocks into the final artifact — those belong to the source standard example, not to the agent output template.

## Forbidden Without Evidence

- Entity and attribute names not present in requirements or confirmed existing schema.
- SQL/document types, length, precision, scale.
- Nullable/required decisions for business-critical fields.
- PK/FK strategy, cascade rules, orphan handling.
- Enum/status value lists.
- CHECK constraints, defaults, generated columns, triggers.
- Index definitions and uniqueness rules.
- Junction table structure for implied N:M relations.
- Storage engine-specific features unless confirmed.

If the canonical example contains such details but the user has not confirmed them and has not authorized greenfield design, do not copy them into the final artifact. Keep the section narrower and record the gap in `Gaps и допущения`.

## Forbidden In Final Artifact

- `Пример:` in the document title.
- `СТД-*` source standard IDs.
- Raw `N:M` in the relationships table without junction decomposition.
- Unresolved markers such as `TODO`, `TRACE-`, `OQ-`, `CONFLICT-` or `[ТРЕБУЕТ УТОЧНЕНИЯ]` without linked `GAP-DATA-*`.
- DDL/DML migration scripts — they belong to a separate migrations artifact.
