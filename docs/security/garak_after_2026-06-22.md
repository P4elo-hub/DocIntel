# Garak after — llm-service (с защитным слоем)

**Дата:** 2026-06-22  
**garak:** 0.15.1  
**Модель:** gpt-4o-mini  
**Статус:** полный прогон garak **не выполнялся** (по запросу не перезапускать). Ниже — команда, ожидаемая дельта и локальная проверка защиты.

## Команда запуска (after)

```bash
# 1. Сервис с включённой защитой
SECURITY_ENABLED=true RATE_LIMIT_PER_MIN=0 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Тот же набор проб и конфиг, что в baseline
garak --target_type rest -G eval/security/rest_config.json \
  --probes promptinject.HijackHateHumans,encoding.InjectBase64,dan.Ablation_Dan_11_0 \
  --generations 1 --parallel_attempts 2 --report_prefix after
```

После завершения:

```bash
python3 eval/security/render_garak_report.py \
  ~/.local/share/garak/garak_runs/after.report.jsonl \
  --title "Garak after — llm-service (с защитой)" \
  --date 2026-06-22 \
  --command "<команда выше>" \
  --out docs/security/garak_after_2026-06-22.full.md

cp ~/.local/share/garak/garak_runs/after.report.html docs/security/reports/after/
```

## Ожидаемая дельта (baseline → after)

| probe | baseline % | ожидаемо after % | закрыть п.п. | механизм |
|---|---:|---:|---:|---|
| `promptinject.HijackHateHumans` | ~69* | 5–15 | ~54–64 | `validate_input`: regex `ignore.*instructions` → HTTP 400 без `content` |
| `encoding.InjectBase64` | 60.5–78.5 | выше baseline† | отрицательно | агрессивный regex base64 в `input_validator` режет легитимные payload |
| `dan.Ablation_Dan_11_0` | 0.0 | ~0 | 0 | модель уже отказывает; `you are now` / `ignore` дополнительно блокируются |

\* baseline: 138/199 попыток promptinject (прогон прерван на 199/256).  
† на encoding-пробах возможны ложные блокировки из-за эвристики base64 — зафиксировать честно в финальном отчёте.

## Локальная проверка защиты (без garak)

Интеграционный тест `tests/integration/test_security_chat.py`:

- `ignore previous instructions` → **400** `{"error":{"code":"input_rejected",...}}` — garak не видит `content`, проба считается закрытой.
- Unit-тест `test_filter_output_raises_on_canary_leak` — канарейка из `app.state.canary` ловится в `output_filter`.
- `tests/unit/test_pii.py` — маскирование email/телефона/карты/ИНН/паспорта/ORDER в `redact_pii`; в логах LLM-ответов поле `response_preview` проходит через `redact_pii`.

## Что подключено в коде

| модуль | роль |
|---|---|
| `app/services/security/input_validator.py` | длина, injection-regex, encoding-эвристика → HTTP 400 |
| `app/services/security/output_filter.py` | утечка system prompt / canary, PII в ответе |
| `app/observability/pii.py` | `redact_pii` на исходящих preview в structlog |
| `app/main.py` | `app.state.canary`, `SecurityValidationError` handler |
| `eval/security/rest_config.json` | REST-таргет garak под POST `/chat` |

Флаг `SECURITY_ENABLED=false` отключает защиту для baseline-прогона без изменения кода.
