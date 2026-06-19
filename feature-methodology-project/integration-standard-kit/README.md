# Integration Standard Kit

Этот каталог показывает, как разложить раздел `4. Стандарты описания интеграций` из `standarts_features (3).md` на рабочие слои для агентного pipeline.

## Зачем нужен kit

Один большой стандарт удобен человеку, но агенту сложно понять, где методика, где обязательный формат, где шаблон, а где пример. Kit разделяет эти роли:

| Слой | Зачем нужен | Что лежит здесь |
|---|---|---|
| `skills/` | Учит агента, как анализировать интеграции. | `integration-analysis/SKILL.md` |
| `spec-kit/` | Задает контракт валидного результата. | YAML-схемы страниц и протоколов |
| `templates/` | Дает форму документа, которую агент заполняет. | Markdown-шаблоны REST, gRPC, async и общей интеграции |
| `examples/` | Показывает ожидаемый стиль результата. | Пример описания REST-интеграции |
| `quality-gates/` | Проверяет, можно ли принимать результат. | Чек-листы и gates для ревью |

## Как использовать в runbook

Пример шага:

```text
Команда: описать интеграции.

Используй:
- skill: integration-standard-kit/skills/integration-analysis/SKILL.md
- spec: integration-standard-kit/spec-kit/integration-page.schema.yaml
- template: integration-standard-kit/templates/integration-page.template.md
- quality gate: integration-standard-kit/quality-gates/integration-review.yaml

Выход:
- 04-Interfaces/<integration>.md
```

## Главная идея

- Skill говорит агенту, как думать и что искать.
- Spec говорит, каким должен быть результат.
- Template говорит, куда писать.
- Example показывает норму качества.
- Quality gate решает, можно ли считать страницу готовой.

## Матрица протоколов

| Протокол | Spec | Template | Example | Quality gate |
|---|---|---|---|---|
| REST | `spec-kit/rest-api.schema.yaml` | `templates/rest-endpoint.template.md` | `examples/rest-integration-example.md` | `quality-gates/rest-review.yaml` |
| gRPC | `spec-kit/grpc-service.schema.yaml` | `templates/grpc-service.template.md` | `examples/grpc-service-example.md` | `quality-gates/grpc-review.yaml` |
| GraphQL | `spec-kit/graphql-operation.schema.yaml` | `templates/graphql-operation.template.md` | `examples/graphql-operation-example.md` | `quality-gates/graphql-review.yaml` |
| SOAP | `spec-kit/soap-operation.schema.yaml` | `templates/soap-operation.template.md` | `examples/soap-operation-example.md` | `quality-gates/soap-review.yaml` |
| Async / event | `spec-kit/async-message.schema.yaml` | `templates/async-message.template.md` | `examples/async-message-example.md` | `quality-gates/async-review.yaml` |

## Как выбирать слой

Сначала применяется общий `integration-review.yaml`: он проверяет границы интеграции, evidence, contract, mapping и отсутствие незакрытых маркеров. Затем применяется протокольный gate: REST, gRPC, GraphQL, SOAP или async.
