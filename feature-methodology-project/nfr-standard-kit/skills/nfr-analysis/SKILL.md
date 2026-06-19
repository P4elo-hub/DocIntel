---
name: nfr-analysis
description: Analyzes and documents non-functional requirements (performance, reliability, security, configuration, feature toggles) using source evidence. Use when describing SLA, SLO, latency, throughput, CCU, caching, graceful degradation, config parameters, feature flags, rollout and go/no-go criteria.
disable-model-invocation: true
---

# NFR Analysis

## Purpose

Use this skill when an agent must analyze or write NFR artifacts for a feature. The skill defines the workflow. The required output format is defined by domain specs, templates, canonical examples (where present) and quality gates in this kit.

This skill is not a substitute for evidence. Do not invent SLA, SLO, p85/p95 targets, RPS, CCU, cache TTL, pool sizes, config defaults, toggle keys, rollout thresholds, AML thresholds or security rules without evidence.

Final reader-facing artifacts must:

- Use title format `#### NFR — <Название фичи> (<Домен>)` where domain is `Производительность`, `Надёжность`, `Безопасность`, `Конфигурация` or `Feature Toggles`.
- Not write `Пример:` in the title.
- Not expose source standard IDs such as `СТД-*` in the final artifact.
- Not copy canonical example values for a different feature without evidence or explicit greenfield authorization.

## Required Files

| Domain | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| Clarification (обязательно первым) | `spec-kit/nfr-clarification.schema.yaml` | `templates/nfr-clarification-questionnaire.template.md` | — | `quality-gates/nfr-review.yaml` (NFR-GATE-000) |
| Umbrella | `spec-kit/nfr-page.schema.yaml` | — | domain examples | `quality-gates/nfr-review.yaml` |
| Производительность | `spec-kit/performance.schema.yaml` | `templates/performance.template.md` | `examples/account-transfer-performance-example.md` | `quality-gates/performance-review.yaml` |
| Надёжность | `spec-kit/reliability.schema.yaml` | `templates/reliability.template.md` | `examples/account-transfer-reliability-example.md` | `quality-gates/reliability-review.yaml` |
| Безопасность | `spec-kit/security.schema.yaml` | `templates/security.template.md` | — | `quality-gates/security-review.yaml` |
| Конфигурация | `spec-kit/configuration.schema.yaml` | `templates/configuration.template.md` | `examples/account-transfer-configuration-example.md` | `quality-gates/configuration-review.yaml` |
| Feature Toggles | `spec-kit/feature-toggles.schema.yaml` | `templates/feature-toggles.template.md` | `examples/account-transfer-feature-toggles-example.md` | `quality-gates/feature-toggles-review.yaml` |

## Instructions

0. **Clarification-first (обязательный шаг до финального NFR).**
   - Read `spec-kit/nfr-clarification.schema.yaml` and `templates/nfr-clarification-questionnaire.template.md`.
   - On a short first request (feature name only, «опиши NFR», без метрик) — **do not** write final `#### NFR — …` pages yet.
   - Output **only** the clarification questionnaire grouped by selected domains.
   - Offer modes **A / B / C / D** (evidence / greenfield DESIGN-NFR / partial / gap-only).
   - For **performance** domain you **must** ask explicitly:
     - перцентиль и цель latency (p85/p95/p99) + условия измерения (CCU, RPS, объём данных);
     - штатная и пиковая нагрузка (RPS, множитель, окно пика);
     - **Rate Limiting** — да/нет и параметры;
     - **Throttling** — да/нет и параметры;
     - **Circuit Breaker** — да/нет, зависимости, порог %, cooldown;
     - CCU и поведение при перегрузке.
   - «Нет» for limiter/breaker is a valid answer — record it; do not assume defaults from canonical transfer example.
   - Set `clarificationPassCompleted: true` in working layer only when mandatory topics are answered, GAP-marked, or DESIGN-NFR-authorized.
   - Final artifacts are allowed after user replies, or when `draftWithoutClarificationAllowedWhen` applies.

1. Classify which NFR domains apply.
   - Performance: API, UI, DB, queues, sagas, caching.
   - Reliability: SLO, availability, dependency failure behavior.
   - Security: auth, roles, PII, payments, secrets, masking.
   - Configuration: runtime parameters, limits, thresholds stored in config.
   - Feature toggles: release/experiment/ops flags with rollout and removal plan.
   - Split into separate files per domain unless the runbook requires one combined page.

2. Collect evidence before writing.
   - Architecture docs, capacity plans, load tests, monitoring dashboards, SRE runbooks.
   - API/integration contracts for endpoints referenced in latency tables.
   - Frontend performance budgets, Web Vitals targets.
   - DB explain plans, index migrations, pool settings.
   - ConfigMaps, feature-flag services, product rollout plans.
   - Security policies, DLP rules, compliance requirements.

3. Complete mandatory clarification catalog before writing final tables.
   - Follow every `mandatory: true` and applicable `mandatory: when` item in `nfr-clarification.schema.yaml`.
   - Map each answer to sections 7.1.x / 7.2 / config / toggles; unmapped topics stay `GAP-NFR-*`.
   - If the user explicitly asks for a draft with known gaps, mark gaps as `GAP-NFR-*` and still show which mandatory questions were skipped.

4. Use canonical examples as the target level of detail.
   - Match section order and table columns from the canonical example for that domain.
   - For performance, include all subsections 7.1.1–7.1.7 when the feature has API, UI, DB or cache impact.
   - For toggles, include card, ON/OFF behavior, dependencies, removal plan and verification checklist per toggle.
   - Security has no canonical example in source section 7 — follow `templates/security.template.md` and fill only from evidence.

5. Write the domain artifact using templates and canonical section order.

6. **Обязательный проход: Inline traceability + реестр Gaps** (выполнять для **каждого** финального файла NFR **перед** quality gates).  
   Spec: `spec-kit/nfr-page.schema.yaml` → `inlineTraceability`.  
   Этот проход **часть skill**, не опциональное улучшение файла вручную.

7. Run quality gates.
   - Always run `quality-gates/nfr-review.yaml` first.
   - Then run each produced domain gate.
   - If any blocking check fails, do not mark the domain artifact as done.

## Interactive Clarification Mode

When required information is missing, use structured questions (table from `nfr-clarification-questionnaire.template.md`).

| Gap type | Use for | Question style |
|----------|---------|----------------|
| Choice gap | да/нет, перцентиль, тип rollout | Single choice |
| Numeric gap | p85, RPS, CCU, TTL, порог breaker | Free text or «не знаю → GAP» |
| Evidence gap | load test, SLO doc | Free text or mode A |

**Non-negotiable for performance:** PERF-Q-007, PERF-Q-008, PERF-Q-009 must appear in the first clarification block when performance is in scope.

## Clarification Triggers

Ask follow-up questions when unknown and the answer affects the NFR artifact:

**Performance**

- Which endpoints, screens, queues or DB queries are in scope?
- Target percentile: p85, p95 or other? Measurement conditions (CCU, RPS, data volume)?
- Peak load profile: steady RPS, peak multiplier, duration, calendar triggers?
- End-to-end business transactions: steps, step timeouts, global timeout, client HTTP timeout, compensation?
- Web Vitals per screen? Loading strategy per UI block?
- CCU, sessions per user, overload behavior?
- Rate limit, throttle, circuit breaker, bulkhead parameters and where they apply?
- DB query SLA, indexes, connection pool sizing rationale?
- Cache keys, level (L1–L4), TTL, invalidation, max size, miss behavior?

**Reliability**

- SLO for availability, error rate, latency — per service or per critical operation?
- Which dependencies need graceful degradation and exact fallback?

**Security**

- Authentication mechanism per channel? Step-up auth (2FA) thresholds?
- Roles and permissions per operation?
- Sensitive fields: storage, transit, UI masking, log masking, retention?
- Regulatory constraints (PCI, personal data law)?

**Configuration**

- Parameter key, type, default, validation range, storage, change frequency, rollback?
- Who may change static vs dynamic vs runtime parameters?

**Feature toggles**

- Toggle key, type, owner, default, rollout strategy (blocks, segments, canary)?
- ON/OFF behavior for UI and API?
- Dependencies (requires / conflicts / includes)?
- Removal plan and go/no-go metrics with OK vs Rollback thresholds?

Example grouped block:

```text
Нужно уточнить NFR:

1. Performance: какие endpoint/экран/очередь в scope и целевые p85/RPS/CCU?
2. Transactions: есть ли saga с step timeout и global timeout?
3. Reliability: целевые SLO и fallback при отказе зависимостей?
4. Security: роли, 2FA, чувствительные поля и маскирование?
5. Config: какие параметры меняются без деплоя и кто их меняет?
6. Toggles: ключи, rollout, зависимости и метрики go/no-go?
```

## Domain Selection Hints

| User wording | Domains to open |
|--------------|-----------------|
| SLA, latency, RPS, нагрузка, кэш, Web Vitals | performance (+ reliability if SLO mentioned) |
| availability, degradation, fallback, SLO | reliability |
| 2FA, роли, PII, маскирование, доступ | security (+ configuration if thresholds in config) |
| ConfigMap, лимит, порог, параметр | configuration |
| feature flag, toggle, rollout, A/B, kill switch | feature-toggles |

## Output Splitting

Prefer separate artifacts per domain (as in integration kit protocol matrix):

```text
07-NFR/performance.md
07-NFR/reliability.md
07-NFR/security.md
07-NFR/configuration.md
07-NFR/feature-toggles.md
```

When the user asks for one combined NFR page, keep domain section order: performance → reliability → security → configuration → feature toggles.

---

## Assumption and Gap Registry (обязательный проход)

После заполнения таблиц NFR агент **обязан** выполнить этот проход для **каждого** доменного артефакта. Цель: в теле документа сразу видно, что подтверждено, а внизу — полный реестр всего неподтверждённого.

### Что маркировать в колонке «Статус» (или `**DESIGN-NFR-NNN**` в ячейке)

| Категория | Примеры | ID |
|-----------|---------|-----|
| Подтверждено пользователем | «retry 3», «без circuit breaker», явный ответ в чате | `Подтверждено — вы` |
| Подтверждено evidence | SLO из load test, Jira, контракт, мониторинг | `Подтверждено — evidence` + ссылка в Gaps |
| Из постановки / requirements | «только торговые заявки», Kafka, 6 источников | `Из постановки` (строку в Gaps не дублировать) |
| Спроектировано (greenfield B) | p85, RPS, endpoint path, ключи config | `DESIGN-NFR-NNN` |
| Спросили — не ответили | обязательный вопрос из clarification без ответа | `GAP-NFR-NNN` |
| **Не спрашивали и дописали сами** | **зависимость тогла, «конфликтов нет», владелец, даты, пороги go/no-go** | **`DESIGN-NFR-NNN` обязательно** |

**Запрещено:** строка в таблице выглядит как факт, а в Gaps нет записи.  
**Запрещено:** `—` в зависимостях тоглов без `DESIGN-NFR-*` («конфликтов нет»).

### Алгоритм прохода (выполнить по шагам)

```text
Шаг A — Инвентаризация
Пройти каждую таблицу артефакта. Для каждой строки с конкретным значением (число, URL, ключ,
endpoint, тогл, зависимость, дата, порог, «нет», «не применяется») классифицировать:
Подтверждено / Из постановки / DESIGN-NFR / GAP-NFR.

Шаг B — Inline-маркировка
Добавить колонку «Статус» в таблицы, где её нет (карточка тогла, зависимости, config,
ключевые performance-таблицы при greenfield). В ячейке «Статус» — ID или «Подтверждено — вы».

Шаг C — Нумерация ID
Вести единую нумерацию DESIGN-NFR-001… и GAP-NFR-001… в рамках фичи (можно сквозную
по всем файлам 07-NFR/ или per-file — но без дубликатов смысла).

Шаг D — Сборка секции «Gaps и допущения»
Для КАЖДОГО DESIGN-NFR-* и GAP-NFR-* из тела документа добавить строку в таблицу внизу:

| ID | Тип | Где в документе | Что предположено / не уточнялось | Подтверждено? | Как закрыть |

Шаг E — Сверка (blocking self-check)
- [ ] Каждый DESIGN-NFR/GAP в теле → есть строка в Gaps
- [ ] Каждая строка в Gaps → есть маркер в теле
- [ ] Нет зависимостей тоглов без Статус
- [ ] Секция Gaps не пуста, если в документе есть DESIGN-NFR
- [ ] В шапке файла (blockquote) одна строка: «Неподтверждённое помечено DESIGN-NFR / GAP-NFR, см. таблицу внизу»

Шаг F — Feature toggles (дополнительно)
Перед записью зависимости requires/conflicts/includes — задать вопрос пользователю ИЛИ
записать с DESIGN-NFR и в Gaps: «не спрашивалось».
```

### Шаблон секции «Gaps и допущения» (обязателен в каждом доменном файле при DESIGN/GAP)

```markdown
---

**Gaps и допущения**

| ID | Тип | Где в документе | Что предположено / не уточнялось | Подтверждено? | Как закрыть |
|----|-----|-----------------|----------------------------------|---------------|-------------|
| DESIGN-NFR-017 | Design | Feature Toggles → Зависимости | Тогл `ops.integration.bph.gateway.enabled` и связь requires | Нет — не спрашивалось | Подтвердить у DevOps или удалить строку |
```

Если после прохода не осталось DESIGN/GAP (только «Подтверждено» и «Из постановки»):

```markdown
**Gaps и допущения**

Gaps и design-допущения не выявлены — все значения подтверждены пользователем или evidence.
```

### Связь с режимами A / B / C / D

| Режим | Проход Gaps |
|-------|-------------|
| A (evidence) | Максимум «Подтверждено — evidence»; остальное GAP-NFR |
| B (greenfield) | Каждое спроектированное значение → DESIGN-NFR + строка в Gaps |
| C (частично) | Смесь: подтверждённое + DESIGN-NFR + GAP-NFR |
| D (только GAP) | Таблицы узкие, числа не выдумывать; GAP-NFR в теле и в реестре |

### Что проверяют quality gates

- `nfr-review.yaml` — `inlineTraceability`, пустой Gaps при маркерах в теле
- `feature-toggles-review.yaml` — `TOGL-GATE-006` assumptions_traceable

Если self-check Шаг E не пройден — **исправить артефакт**, затем запускать gates. Не сдавать файл пользователю без синхронизации тела и Gaps.
