# Eval

## Chat (FAQ / search_kb / agent)

```bash
uv run python eval/run_evaluation.py \
  --golden eval/golden_dataset.json \
  --judge gpt-5.2 \
  --out eval/runs/chat-2026-06-21.json

uv run python eval/check_thresholds.py \
  --run eval/runs/chat-2026-06-21.json \
  --thresholds eval/thresholds.yaml
```

## Generate (sectioned /features/generate, methodology)

```bash
uv run python eval/run_evaluation_generate.py \
  --golden eval/golden_dataset_generate.json \
  --judge gpt-5.2 \
  --out eval/runs/generate-2026-06-21.json

uv run python eval/check_thresholds.py \
  --run eval/runs/generate-2026-06-21.json \
  --thresholds eval/thresholds_generate.yaml
```

Smoke: `uv run python eval/run_evaluation_generate.py --limit 2`

Один кейс по id:

```bash
uv run python eval/run_evaluation_generate.py \
  --id gen_gate_async_focus \
  --out eval/runs/generate-one.json
```

Несколько выбранных кейсов:

```bash
uv run python eval/run_evaluation_generate.py \
  --id gen_async_001 --id gen_gate_metrics_focus \
  --out eval/runs/generate-pick.json
```

Список id: поле `"id"` в `eval/golden_dataset_generate.json` (например `gen_rest_001`, `gen_gate_uc_focus`).

| Файл | Endpoint | Кейсов |
|------|----------|--------|
| `golden_dataset.json` | `/features/chat` | 22 FAQ/KB |
| `golden_dataset_generate.json` v2 | `/features/generate` | 18 methodology |

### Что в каждом generate-кейсе (v2)

| Поле | Назначение |
|------|------------|
| `methodology_ref` | example из kit (`examples/*.md`) |
| `template_ref` | шаблон секции (`templates/*.template.md`) |
| `spec_ref` | JSON/YAML schema (`spec-kit/*.schema.yaml`) |
| `gate_ref` | quality gate (`quality-gates/*-review.yaml`) |
| `gate_blocking_ids` | какие blocking checks применить к ответу |
| `quality_gates` | несколько gate для составных кейсов (Kafka full) |

### Два слоя оценки в generate-eval

1. **Judge (G-Eval)** — rubric `expected_answer` + keywords, scores 1–5  
2. **Quality gates** — детерминированные проверки по YAML (`eval/gate_checks.py`)

В run JSON: `gate_checks`, `gate_summary.pass_rate`, агрегаты `gate_pass_rate_avg`.

Фокус-кейсы `gen_gate_*_focus` — расширенный набор `gate_blocking_ids` для async/metrics/use-case.

## Security (garak, Б3.8)

Конфиги REST-таргета:

| Файл | Endpoint |
|------|----------|
| `eval/security/rest_config.json` | `POST /chat` |
| `eval/security/rest_config_features.json` | `POST /features/chat` |

```bash
# baseline (защита выключена)
SECURITY_ENABLED=false docker compose up -d app

garak --target_type rest -G eval/security/rest_config.json \
  --probes promptinject.HijackHateHumans,encoding.InjectBase64,dan.Ablation_Dan_11_0 \
  --generations 1 --parallel_attempts 2 --report_prefix baseline

# after (SECURITY_ENABLED=true в .env / compose)
garak --target_type rest -G eval/security/rest_config.json \
  --probes promptinject.HijackHateHumans,encoding.InjectBase64,dan.Ablation_Dan_11_0 \
  --generations 1 --parallel_attempts 2 --report_prefix after
```

Отчёты: `docs/security/garak_*.md`, HTML/JSONL — `docs/security/reports/`.  
Рендер markdown из JSONL: `python3 eval/security/render_garak_report.py …`
