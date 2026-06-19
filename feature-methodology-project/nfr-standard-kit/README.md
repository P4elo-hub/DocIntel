# NFR Standard Kit

Этот каталог разлагает раздел `7. Стандарты нефункциональных требований` из `standarts_features (3).md` на рабочие слои для агентного pipeline — по той же схеме, что `integration-standard-kit/` (отдельные домены вместо REST / gRPC / async).

## Зачем нужен kit

NFR в исходном стандарте объединяют производительность, надёжность, безопасность, конфигурацию и feature toggles. Агенту нужны отдельные контракты, шаблоны, эталоны и gates для каждого домена.

| Слой | Зачем нужен | Что лежит здесь |
|---|---|---|
| `skills/` | Методика анализа NFR и уточняющие вопросы. | `nfr-analysis/SKILL.md` |
| `spec-kit/` | Контракт валидного результата по доменам. | YAML-схемы |
| `templates/` | Форма документа для заполнения. | Markdown-шаблоны |
| `examples/` | Эталон качества из блока «Переводы между счетами». | Примеры без `СТД-*` |
| `quality-gates/` | Приёмка результата. | Общий gate + доменные gates |

## Матрица доменов NFR

| Домен | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| Производительность | `spec-kit/performance.schema.yaml` | `templates/performance.template.md` | `examples/account-transfer-performance-example.md` | `quality-gates/performance-review.yaml` |
| Надёжность | `spec-kit/reliability.schema.yaml` | `templates/reliability.template.md` | `examples/account-transfer-reliability-example.md` | `quality-gates/reliability-review.yaml` |
| Безопасность | `spec-kit/security.schema.yaml` | `templates/security.template.md` | — (в исходном стандарте нет эталонного примера в блоке 7) | `quality-gates/security-review.yaml` |
| Конфигурация | `spec-kit/configuration.schema.yaml` | `templates/configuration.template.md` | `examples/account-transfer-configuration-example.md` | `quality-gates/configuration-review.yaml` |
| Feature Toggles | `spec-kit/feature-toggles.schema.yaml` | `templates/feature-toggles.template.md` | `examples/account-transfer-feature-toggles-example.md` | `quality-gates/feature-toggles-review.yaml` |

Общий gate: `quality-gates/nfr-review.yaml` (граница фичи, evidence, отсутствие `СТД-*` и незакрытых маркеров).

## Clarification-first (обязательно)

Перед финальными страницами NFR агент **обязан** пройти опросник:

- Spec: `spec-kit/nfr-clarification.schema.yaml`
- Форма: `templates/nfr-clarification-questionnaire.template.md`
- Gate: `NFR-GATE-000` в `quality-gates/nfr-review.yaml`

На первом коротком запросе («опиши NFR для фичи X») — **только вопросы**, без таблиц с цифрами. Явно спрашивается: перцентиль latency, RPS/пик, CCU, **Rate Limit**, **Throttling**, **Circuit Breaker** (да/нет + параметры), кэш, SLO, toggles.

Режимы ответа: **A** evidence · **B** DESIGN-NFR · **C** частично · **D** только GAP.

## Как использовать в runbook

```text
Команда: описать NFR фичи.

Используй:
- skill: nfr-standard-kit/skills/nfr-analysis/SKILL.md
- spec: nfr-standard-kit/spec-kit/nfr-page.schema.yaml
- доменные spec/template/example/gate по матрице выше
- quality gate: nfr-standard-kit/quality-gates/nfr-review.yaml

Выход (по одному файлу на домен или один сводный):
- 07-NFR/performance.md
- 07-NFR/reliability.md
- 07-NFR/security.md
- 07-NFR/configuration.md
- 07-NFR/feature-toggles.md
```

## Главная идея

- Skill говорит агенту, как думать, что уточнять и что не выдумывать.
- Spec говорит, каким должен быть результат.
- Template задаёт форму.
- Example (где есть в стандарте) задаёт норму детализации один в один из блока примера, без ссылок на `СТД-*`.
- Quality gate решает, можно ли считать артефакт готовым.

## Ограничение по эталону безопасности

В `standarts_features (3).md` раздел `7.3. Безопасность` содержит только правила `СТД-БЕЗ-01` и `СТД-БЕЗ-02`; в сворачиваемом примере фичи «Переводы между счетами» отдельного блока безопасности нет. Для безопасности используйте `templates/security.template.md` и заполняйте по evidence; не копируйте содержимое из performance/reliability examples.

## GAP / assumption / DESIGN (обязательный проход в skill)

После написания таблиц агент выполняет **Assumption and Gap Registry** (`skills/nfr-analysis/SKILL.md`):

1. Колонка **«Статус»** в таблицах — `Подтверждено — вы` / `DESIGN-NFR-*` / `GAP-NFR-*` / `Из постановки`.
2. Секция **Gaps и допущения** внизу **каждого** доменного файла — строка на **каждый** `DESIGN-NFR` / `GAP` из тела (сверка в обе стороны).
3. Зависимости тоглов и «конфликтов нет» **нельзя** писать как факт без маркера и строки в Gaps.

- `GAP-NFR-*` — неизвестное после уточнений.
- `DESIGN-NFR-*` — спроектировано (режим B) или дописано без вопроса пользователю.
- Gate: `NFR-GATE-007` в `nfr-review.yaml`.

## Entrypoint

Project skill: `.cursor/skills/describe-nfr/SKILL.md`
