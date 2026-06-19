# Use Case Standard Kit

Этот каталог раскладывает раздел `6. Стандарты описания алгоритмов (Use Case)` из `standarts_features (3).md` на рабочие слои для агентного pipeline.

## Зачем нужен kit

Use Case повторно используется в AS IS, TO BE, feature, frontend и integration flows. Чтобы не дублировать правила сценариев в каждом kit, этот каталог задает единый стандарт для описания акторов, целей, предусловий, happy path, альтернативных сценариев, бизнес-правил и связей между Use Cases.

| Слой | Зачем нужен | Что лежит здесь |
|---|---|---|
| `skills/` | Учит агента анализировать и писать Use Cases. | `use-case-analysis/SKILL.md` |
| `spec-kit/` | Задает контракт валидного результата. | `use-case.schema.yaml` |
| `templates/` | Дает форму документа, которую агент заполняет. | `use-case.template.md` |
| `examples/` | Показывает ожидаемый стиль результата. | Канонический пример перевода между счетами |
| `quality-gates/` | Проверяет, можно ли принимать результат. | `use-case-review.yaml` |

## Как использовать в runbook

Пример шага:

```text
Команда: описать Use Case.

Используй:
- skill: use-case-standard-kit/skills/use-case-analysis/SKILL.md
- spec: use-case-standard-kit/spec-kit/use-case.schema.yaml
- template: use-case-standard-kit/templates/use-case.template.md
- example: use-case-standard-kit/examples/transfer-between-accounts-use-case-example.md
- quality gate: use-case-standard-kit/quality-gates/use-case-review.yaml

Выход:
- 02-Use-Cases/<use-case>.md
```

## Когда применять

Применяй этот kit, если артефакт описывает:

- цель актора;
- пользовательский или системный сценарий;
- пошаговый алгоритм поведения;
- ветвления, исключения или ошибки;
- проверяемые предусловия и постусловия;
- бизнес-правила, влияющие на шаги сценария;
- связи `include`, `extend` или generalization.

## Как переиспользовать в других kits

Другие kits не должны копировать правила Use Case локально. Они должны ссылаться на этот kit:

| Kit | Как использует Use Case |
|---|---|
| `feature-standard-kit` | Выбирает Use Case, если фича меняет поведение или содержит сценарий |
| `process-state-standard-kit` | Использует Use Case для AS IS и TO BE описаний |
| `frontend-standard-kit` | Привязывает экраны и состояния UI к шагам сценария |
| `integration-standard-kit` | Ссылается на Use Case как на бизнес-сценарий, который запускает интеграцию |

## Главная идея

- Skill говорит агенту, как думать и какие уточнения задать.
- Spec говорит, каким должен быть результат.
- Template говорит, куда писать.
- Example показывает норму качества.
- Quality gate решает, можно ли считать Use Case готовым.
