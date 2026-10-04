"""Validate = проверщик, не второй автор."""

from __future__ import annotations

import inspect

from app.services.docintel import validator


def test_no_length_rollback_heuristic() -> None:
    src = inspect.getsource(validator.validate_against_kb)
    assert "слишком короткий" not in src
    assert "min_ratio" not in src
    assert "оставляю draft" in src  # пустой ответ модели — ок


def test_system_prompts_are_reviewer_not_author() -> None:
    assert "ПРОВЕРЩИК" in validator._SYSTEM_ANSWER
    assert "ПРОВЕРЩИК" in validator._SYSTEM_DOCUMENT
    assert "НЕ удаляй" in validator._SYSTEM_DOCUMENT
    assert "БЕЗ изменений" in validator._SYSTEM_ANSWER


def test_collect_evidence_prefers_pipeline(monkeypatch) -> None:
    import asyncio

    async def _boom(*_a, **_k):
        raise AssertionError("fresh Qdrant must not run when pipeline context exists")

    monkeypatch.setattr(validator, "collect_fresh_rag_evidence", _boom)
    monkeypatch.setattr(validator, "_resolve_kb_handler", lambda _h: None)

    pipeline = "## RAG (Qdrant)\n\nкакой-то чанк про varmargin"

    async def _run() -> str:
        return await validator._collect_evidence(
            "как выглядит вармаржа на композите",
            pipeline,
            mode="answer",
            kb_handler=None,
        )

    assert asyncio.run(_run()) == pipeline
