"""Детерминированные проверки ответа по quality-gates methodology."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
METHODOLOGY_DIR = ROOT / "feature-methodology-project"


def _contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def _contains_all(text: str, needles: list[str]) -> bool:
    return all(_contains(text, n) for n in needles)


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(_contains(text, n) for n in needles)


def _sanitize_gate_yaml(raw: str) -> str:
    """Quote unquoted YAML values that contain markdown backticks."""
    out: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"^(\s+description:\s+)(.+)$", line)
        if m:
            prefix, value = m.group(1), m.group(2)
            stripped = value.strip()
            already_quoted = (
                (stripped.startswith('"') and stripped.endswith('"'))
                or (stripped.startswith("'") and stripped.endswith("'"))
            )
            if "`" in value and not already_quoted:
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                line = f'{prefix}"{escaped}"'
        out.append(line)
    suffix = "\n" if raw.endswith("\n") else ""
    return "\n".join(out) + suffix


def load_gate(gate_ref: str, *, base: Path = METHODOLOGY_DIR) -> dict[str, Any]:
    path = base / gate_ref
    if not path.is_file():
        raise FileNotFoundError(f"Gate not found: {gate_ref}")
    raw = path.read_text(encoding="utf-8")
    if yaml is None:
        raise RuntimeError("PyYAML required for gate checks: uv add --dev pyyaml")
    data = yaml.safe_load(_sanitize_gate_yaml(raw))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid gate YAML: {gate_ref}")
    return data


def _blocking_by_id(gate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    checks = gate.get("blockingChecks") or []
    return {item["id"]: item for item in checks if isinstance(item, dict) and "id" in item}


def _evaluate_structured(answer: str, check: dict[str, Any]) -> tuple[bool, str]:
    if forbidden := check.get("forbidden"):
        for token in forbidden:
            if _contains(answer, str(token)):
                return False, f"forbidden token present: {token}"

    if pattern := check.get("requiredPattern"):
        if not re.search(pattern, answer, flags=re.MULTILINE):
            return False, f"requiredPattern not matched"

    for field in check.get("requiredFields", []) + check.get("requiredSections", []):
        if not _contains(answer, str(field)):
            return False, f"missing required field/section: {field}"

    for keyword in check.get("requiredKeywords", []):
        if not _contains(answer, str(keyword)):
            return False, f"missing keyword: {keyword}"

    for column in check.get("requiredColumns", []):
        if not _contains(answer, str(column)):
            return False, f"missing column: {column}"

    for row in check.get("requiredRows", []):
        if not _contains(answer, str(row)):
            return False, f"missing row: {row}"

    return True, "ok"


def _evaluate_heuristic(answer: str, check: dict[str, Any]) -> tuple[bool, str]:
    name = str(check.get("check", ""))
    rules: dict[str, tuple[list[str], list[str] | None]] = {
        "general_info_complete": (
            ["topic", "kafka"],
            ["partition", "гарант", "delivery", "schema"],
        ),
        "consumer_info_documented": (
            ["consumer"],
            ["group", "групп", "dlq", "retry", "идемпот"],
        ),
        "headers_documented": (
            ["header", "заголов"],
            ["message-id", "messageid", "correlation", "event-type", "eventtype"],
        ),
        "envelope_documented": (["metadata", "payload"], None),
        "metadata_parameters_documented": (["messageid", "correlation"], ["timestamp", "eventtype"]),
        "payload_parameters_documented": (["payload", "параметр"], ["validation", "валидац"]),
        "partition_key_documented": (["partition", "ключ"], None),
        "schema_documented": (["schema", "json"], None),
        "examples_present": (["пример", "example", "json"], None),
        "retry_dlq_documented": (["dlq", "retry"], None),
        # integration / rest
        "method_and_path_present": (["get ", "post ", "put ", "delete ", "/api"], None),
        "request_headers_documented": (["request headers", "заголов"], ["authorization", "x-request-id"]),
        "response_headers_documented": (["response headers", "исходящ"], None),
        "status_codes_documented": (["код", "http"], ["400", "401", "404", "500"]),
        # observability
        "log_levels_table": (["error", "warn", "info"], None),
        "events_table": (["eventtype", "журнал", "событ"], None),
        "automatic_fields_table": (["timestamp", "callid", "correlation"], None),
        "application_fields_table": (["eventtype", "calltype", "exsystem"], None),
        "integration_events_have_eventType": (["eventtype", "calltype"], None),
        "technical_metrics_section": (["prometheus", "метрик"], ["labels", "label", "тип"]),
        "error_metrics_section": (["error", "ошиб"], ["counter", "счётчик", "метрик"]),
        "business_metrics_section": (["business", "бизнес"], ["метрик", "formula", "формул"]),
        "assumptions_traceable": (
            ["gap", "gaps", "design-obs", "gap-obs"],
            ["status", "статус"],
        ),
        # nfr performance
        "all_subsections_present": (["7.1.1", "7.1.2"], ["p85", "rps", "пропуск"]),
        "response_time_table": (["p85", "endpoint"], None),
        "throughput_and_load_profile": (["rps", "пропуск", "нагруз"], None),
        # use case
        "main_scenario_numbering_sequential": (["шаг 1", "шаг 2"], None),
        "explicit_condition_format": (["если", "то", "иначе"], None),
        "alternative_path_explicit": (["альтернатив", "перейти к"], None),
        "business_rules_linked_to_steps": (["br-", "бизнес-правил"], ["шаг"]),
        # requirements
        "stakeholders_documented": (["стейкхолдер", "stakeholder"], ["роль", "интерес"]),
        "business_rules_and_constraints_present": (["br-", "cn-", "огранич"], None),
        # data model
        "required_structure_present": (["er-", "сущност", "entity"], ["миграц", "postgresql"]),
    }

    if name == "assumptions_traceable":
        if _contains_any(answer, ["gap", "gaps", "design-obs", "gap-obs"]):
            return True, "ok"
        if _contains(answer, "status") or _contains(answer, "статус"):
            return True, "ok"
        return False, "missing GAP/status traceability markers"

    if name not in rules:
        desc = str(check.get("description", name))
        return True, f"heuristic skipped (no rule): {desc}"

    required_any, also_any = rules[name]
    if not _contains_any(answer, required_any):
        return False, f"heuristic failed: expected any of {required_any}"
    if also_any and not _contains_any(answer, also_any):
        return False, f"heuristic failed: expected also any of {also_any}"
    return True, "ok"


def evaluate_gate_check(answer: str, check: dict[str, Any]) -> tuple[bool, str]:
    ok, detail = _evaluate_structured(answer, check)
    if not ok:
        return ok, detail
    if any(
        key in check
        for key in (
            "requiredFields",
            "requiredSections",
            "requiredKeywords",
            "requiredColumns",
            "requiredRows",
            "requiredPattern",
            "forbidden",
        )
    ):
        return True, detail
    return _evaluate_heuristic(answer, check)


def run_quality_gates(
    answer: str,
    gate_ref: str,
    blocking_ids: list[str],
    *,
    base: Path = METHODOLOGY_DIR,
) -> list[dict[str, Any]]:
    gate = load_gate(gate_ref, base=base)
    by_id = _blocking_by_id(gate)
    results: list[dict[str, Any]] = []

    for check_id in blocking_ids:
        check = by_id.get(check_id)
        if check is None:
            results.append(
                {
                    "id": check_id,
                    "gate_ref": gate_ref,
                    "passed": False,
                    "detail": "unknown check id",
                    "description": "",
                }
            )
            continue
        passed, detail = evaluate_gate_check(answer, check)
        results.append(
            {
                "id": check_id,
                "gate_ref": gate_ref,
                "passed": passed,
                "detail": detail,
                "description": check.get("description", ""),
            }
        )
    return results


def run_item_quality_gates(item: dict[str, Any], answer: str) -> dict[str, Any]:
    """Запускает все quality_gates из golden item."""
    specs: list[dict[str, Any]] = []

    if "quality_gates" in item:
        specs = item["quality_gates"]
    elif gate_ref := item.get("gate_ref"):
        specs = [
            {
                "gate_ref": gate_ref,
                "blocking_ids": item.get("gate_blocking_ids", []),
            }
        ]

    all_results: list[dict[str, Any]] = []
    for spec in specs:
        gate_ref = spec["gate_ref"]
        blocking_ids = spec.get("blocking_ids") or spec.get("gate_blocking_ids") or []
        all_results.extend(run_quality_gates(answer, gate_ref, blocking_ids))

    passed = sum(1 for r in all_results if r["passed"])
    total = len(all_results)
    return {
        "checks": all_results,
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 4) if total else 1.0,
    }


def compute_gate_aggregates(items: list[dict[str, Any]]) -> dict[str, float]:
    rates = [i.get("gate_summary", {}).get("pass_rate", 0.0) for i in items]
    if not rates:
        return {"gate_pass_rate_avg": 0.0, "min_gate_pass_rate": 0.0}
    return {
        "gate_pass_rate_avg": round(sum(rates) / len(rates), 4),
        "min_gate_pass_rate": round(min(rates), 4),
    }
