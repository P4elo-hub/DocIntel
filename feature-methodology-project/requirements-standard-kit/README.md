# Requirements Standard Kit

Этот каталог раскладывает раздел `1. Стандарты сбора и анализа требований` из `standarts_features (3).md` на рабочие слои для агентного pipeline.

## Зачем нужен kit

Requirements kit нужен как первый шаг аналитического процесса: зафиксировать источник требования, стейкхолдеров, бизнес-правила, ограничения, цель фичи, SMART-проверку и противоречия.

| Слой | Зачем нужен | Что лежит здесь |
|---|---|---|
| `skills/` | Учит агента собирать и анализировать требования. | `requirements-analysis/SKILL.md` |
| `spec-kit/` | Задает контракт валидного результата. | `requirements-analysis.schema.yaml` |
| `templates/` | Дает форму документа, которую агент заполняет. | `requirements-analysis.template.md` |
| `examples/` | Показывает ожидаемый стиль результата. | Канонический пример анализа требований |
| `quality-gates/` | Проверяет, можно ли принимать результат. | `requirements-review.yaml` |

## Как использовать как шаг процесса

Пример шага:

```text
Команда: собрать и проанализировать требования.

Используй:
- skill: requirements-standard-kit/skills/requirements-analysis/SKILL.md
- spec: requirements-standard-kit/spec-kit/requirements-analysis.schema.yaml
- template: requirements-standard-kit/templates/requirements-analysis.template.md
- example: requirements-standard-kit/examples/operation-history-requirements-example.md
- quality gate: requirements-standard-kit/quality-gates/requirements-review.yaml

Выход:
- 01-Requirements/<feature>.md
```

## Когда применять

Применяй этот kit, если нужно:

- зафиксировать источник требования;
- определить стейкхолдеров;
- выделить бизнес-правила и ограничения;
- сформулировать цель фичи;
- проверить цель по SMART;
- зафиксировать противоречивые требования и решение.

## Главная идея

- Skill говорит агенту, как собирать требования и когда уточнять gaps.
- Spec говорит, каким должен быть результат.
- Template говорит, куда писать.
- Example показывает норму качества.
- Quality gate решает, можно ли считать анализ требований готовым.
