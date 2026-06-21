"""Smoke-тесты: cassettes (фикстуры) валидны и читаются."""

from __future__ import annotations

import json

import pytest

from tests.helpers import CASSETS_DIR


@pytest.mark.parametrize(
    "relative_path",
    [
        "runs/good_run.json",
        "runs/bad_run.json",
        "cache/chat_hit.json",
        "cache/features_chat_hit.json",
    ],
)
def test_cassettes_are_valid_json(relative_path: str) -> None:
    path = CASSETS_DIR / relative_path
    assert path.is_file(), f"missing cassette: {relative_path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
