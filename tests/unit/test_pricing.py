"""Unit-тесты: расчёт стоимости из usage."""

from __future__ import annotations

import pytest

from app.schemas.chat import Usage
from app.services.pricing import estimate_cost_usd


def test_estimate_cost_gpt4o_mini() -> None:
    usage = Usage(prompt_tokens=1_000_000, completion_tokens=0)
    cost = estimate_cost_usd("gpt-4o-mini", usage)
    assert cost == pytest.approx(0.15)


def test_estimate_cost_gpt4o_mixed_tokens() -> None:
    usage = Usage(prompt_tokens=1000, completion_tokens=500)
    cost = estimate_cost_usd("gpt-4o", usage)
    expected = (1000 * 2.50 + 500 * 10.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_estimate_cost_unknown_model_returns_zero() -> None:
    usage = Usage(prompt_tokens=1000, completion_tokens=500)
    assert estimate_cost_usd("unknown-model", usage) == 0.0
