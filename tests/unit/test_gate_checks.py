"""Unit-тесты quality-gate проверок."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.gate_checks import load_gate, run_item_quality_gates, run_quality_gates

ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "feature-methodology-project"


@pytest.fixture
def metrics_example_text() -> str:
    path = METHODOLOGY / "observability-standard-kit/examples/account-transfer-metrics-example.md"
    return path.read_text(encoding="utf-8")


@pytest.fixture
def async_example_text() -> str:
    path = METHODOLOGY / "integration-standard-kit/examples/async-message-example.md"
    return path.read_text(encoding="utf-8")


def test_load_metrics_gate_yaml() -> None:
    gate = load_gate("observability-standard-kit/quality-gates/metrics-review.yaml")
    assert gate["gate"] == "metrics-review"
    assert len(gate["blockingChecks"]) >= 3


@pytest.mark.parametrize(
    "gate_ref",
    [
        "integration-standard-kit/quality-gates/rest-review.yaml",
        "integration-standard-kit/quality-gates/integration-review.yaml",
        "use-case-standard-kit/quality-gates/use-case-review.yaml",
    ],
)
def test_load_gate_yaml_with_backticks(gate_ref: str) -> None:
    gate = load_gate(gate_ref)
    assert gate["blockingChecks"]
    assert any("`" in str(c.get("description", "")) for c in gate["blockingChecks"])


def test_canonical_metrics_example_passes_gate_checks(metrics_example_text: str) -> None:
    results = run_quality_gates(
        metrics_example_text,
        "observability-standard-kit/quality-gates/metrics-review.yaml",
        ["METR-GATE-001", "METR-GATE-002", "METR-GATE-005"],
    )
    assert all(r["passed"] for r in results), results


def test_empty_answer_fails_gate_checks() -> None:
    results = run_quality_gates(
        "пустой ответ",
        "observability-standard-kit/quality-gates/metrics-review.yaml",
        ["METR-GATE-001"],
    )
    assert results[0]["passed"] is False


def test_run_item_quality_gates_from_golden_item(async_example_text: str) -> None:
    item = {
        "gate_ref": "integration-standard-kit/quality-gates/async-review.yaml",
        "gate_blocking_ids": ["ASYNC-GATE-001", "ASYNC-GATE-003"],
    }
    summary = run_item_quality_gates(item, async_example_text)
    assert summary["total"] == 2
    assert summary["pass_rate"] == 1.0
