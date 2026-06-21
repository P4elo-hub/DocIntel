# Тесты

```
tests/
├── conftest.py          # общие фикстуры: mock_llm, mock_cache, client
├── helpers.py           # PROJECT_ROOT, CASSETS_DIR
├── unit/                # изолированные unit-тесты (без HTTP, без сети)
├── integration/         # API/component через httpx + FastAPI, моки провайдеров
│                        # chat, features, stream, cache, health, security
└── cassets/             # cassette-фикстуры (JSON) + smoke-тесты их валидности
    ├── cache/           # закешированные ChatResponse
    ├── runs/            # примеры eval-прогонов для check_thresholds
    └── test_fixtures.py
```

## Запуск

```bash
uv run python -m pytest tests/unit/ -v          # только unit
uv run python -m pytest tests/integration/ -v   # только integration
uv run python -m pytest tests/cassets/ -v       # cassettes + smoke
uv run python -m pytest tests/ -v               # всё (114 тестов)
```
