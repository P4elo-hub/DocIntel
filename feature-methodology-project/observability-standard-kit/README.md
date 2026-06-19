# Observability Standard Kit

Раздел `8. Стандарты логирования и мониторинга` из `standarts_features (3).md`, разложенный на два домена — как REST/gRPC в `integration-standard-kit/` или performance/reliability в `nfr-standard-kit/`.

## Матрица доменов

| Домен | Spec | Template | Canonical example | Quality gate |
|---|---|---|---|---|
| Логирование | `spec-kit/logging.schema.yaml` | `templates/logging.template.md` | `examples/account-transfer-logging-example.md` | `quality-gates/logging-review.yaml` |
| Метрики | `spec-kit/metrics.schema.yaml` | `templates/metrics.template.md` | `examples/account-transfer-metrics-example.md` | `quality-gates/metrics-review.yaml` |

Общий gate: `quality-gates/observability-review.yaml`.

Umbrella spec: `spec-kit/observability-page.schema.yaml`.

## Слои

| Слой | Содержимое |
|---|---|
| `skills/observability-analysis/SKILL.md` | Методика, clarification-first, Assumption and Gap Registry |
| `spec-kit/` | Контракты + `observability-clarification.schema.yaml` |
| `templates/` | Формы документов и опросник |
| `examples/` | Эталон «Переводы между счетами» без `СТД-*` |
| `quality-gates/` | Приёмка |

## Clarification-first (два шага)

1. **Опросник** — агент сохраняет `08-Observability/<feature>-clarification.md`; вы заполняете колонку «Ваш ответ».
2. **Артефакты** — после ответов (или явного «режим B») пишутся `*-logging.md` и `*-metrics.md`.

До шага 1 агент **не** пишет финальные logging/metrics (hard stop в schema + skills).

- Spec: `spec-kit/observability-clarification.schema.yaml`
- Template: `templates/observability-clarification-questionnaire.template.md`
- Gate: `OBS-GATE-000` в `observability-review.yaml`

Режимы: **A** evidence · **B** DESIGN-OBS · **C** частично · **D** GAP-OBS.

## GAP / DESIGN (обязательный проход)

- `GAP-OBS-*` — неизвестное
- `DESIGN-OBS-*` — спроектировано / не спрашивалось
- Колонка **«Статус»** + секция **Gaps и допущения** (синхронизация с телом)
- Gate: `OBS-GATE-007`

## Выход runbook

```text
08-Observability/<feature>-clarification.md   # сначала
08-Observability/<feature>-logging.md          # после ответов
08-Observability/<feature>-metrics.md
```

## Entrypoint

`.cursor/skills/describe-observability/SKILL.md`
