"""Offline-валидация golden_dataset_generate.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "eval" / "golden_dataset_generate.json"
METHODOLOGY_DIR = ROOT / "feature-methodology-project"

REQUIRED_FIELDS = {
    "id",
    "feature_brief",
    "question",
    "expected_answer",
    "expected_keywords",
    "category",
    "difficulty",
    "source",
    "methodology_ref",
    "template_ref",
    "spec_ref",
    "gate_ref",
    "shablon_section",
}


@pytest.fixture
def golden_data() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_golden_generate_has_minimum_items(golden_data: dict) -> None:
    assert golden_data["version"] == 2
    assert golden_data.get("endpoint") == "/features/generate"
    assert len(golden_data["items"]) >= 18


def test_golden_generate_items_have_required_fields(golden_data: dict) -> None:
    for item in golden_data["items"]:
        missing = REQUIRED_FIELDS - set(item.keys())
        assert not missing, f"{item['id']} missing: {missing}"


def test_golden_generate_methodology_bundle_exists(golden_data: dict) -> None:
    bundle_keys = ("methodology_ref", "template_ref", "spec_ref", "gate_ref")
    for item in golden_data["items"]:
        for key in bundle_keys:
            path = METHODOLOGY_DIR / item[key]
            assert path.is_file(), f"{item['id']}: missing {key}={item[key]}"


def test_golden_generate_gate_ids_defined(golden_data: dict) -> None:
    for item in golden_data["items"]:
        if item.get("quality_gates"):
            assert item["quality_gates"], f"{item['id']}: empty quality_gates"
        else:
            assert item.get("gate_blocking_ids"), f"{item['id']}: no gate_blocking_ids"


def test_golden_generate_has_gate_focus_cases(golden_data: dict) -> None:
    focus_ids = {i["id"] for i in golden_data["items"] if i["source"] == "methodology_gate"}
    assert "gen_gate_async_focus" in focus_ids
    assert "gen_gate_metrics_focus" in focus_ids
    assert "gen_gate_uc_focus" in focus_ids


def test_golden_generate_has_hard_cases(golden_data: dict) -> None:
    hard = [i for i in golden_data["items"] if i["difficulty"] == "hard"]
    assert len(hard) >= 3


def test_golden_generate_covers_major_kits(golden_data: dict) -> None:
    kits = {item["kit"] for item in golden_data["items"]}
    expected = {
        "integration-standard-kit",
        "use-case-standard-kit",
        "requirements-standard-kit",
        "nfr-standard-kit",
        "observability-standard-kit",
        "data-standard-kit",
    }
    assert expected.issubset(kits)
