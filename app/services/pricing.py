"""Расчёт стоимости LLM-вызова по usage и каталогу моделей."""

from __future__ import annotations

from app.routers.models import CATALOG
from app.schemas.chat import Usage


def estimate_cost_usd(model: str, usage: Usage) -> float:
    """Стоимость в USD: (prompt * input_rate + completion * output_rate) / 1M."""
    info = CATALOG.get(model)
    if info is None:
        return 0.0
    cost = (
        usage.prompt_tokens * info.input_per_1m
        + usage.completion_tokens * info.output_per_1m
    ) / 1_000_000
    return round(cost, 8)
