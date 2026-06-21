"""Unit-тесты выбора golden items."""

from __future__ import annotations

import pytest

from eval.run_evaluation import select_golden_items

ITEMS = [
    {"id": "a", "question": "first"},
    {"id": "b", "question": "second"},
    {"id": "c", "question": "third"},
]


def test_select_by_id() -> None:
    selected = select_golden_items(ITEMS, ids=["b"])
    assert [i["id"] for i in selected] == ["b"]


def test_select_by_multiple_ids_preserves_order() -> None:
    selected = select_golden_items(ITEMS, ids=["c", "a"])
    assert [i["id"] for i in selected] == ["c", "a"]


def test_select_by_limit() -> None:
    selected = select_golden_items(ITEMS, limit=2)
    assert [i["id"] for i in selected] == ["a", "b"]


def test_id_takes_precedence_over_limit() -> None:
    selected = select_golden_items(ITEMS, limit=1, ids=["c"])
    assert [i["id"] for i in selected] == ["c"]


def test_unknown_id_raises() -> None:
    with pytest.raises(ValueError, match="Unknown golden item id"):
        select_golden_items(ITEMS, ids=["missing"])
