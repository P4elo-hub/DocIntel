import asyncio
import hashlib
import re
import time
from typing import Callable

import structlog

logger = structlog.get_logger("llm-service.pii")

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    (
        "PHONE_RU",
        re.compile(r"\+7[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"),
    ),
    ("CARD", re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b")),
    ("INN", re.compile(r"\b\d{10}(?:\d{2})?\b")),
    ("PASSPORT", re.compile(r"\b\d{4}[\s\-]?\d{6}\b")),
]

_PRESIDIO_LONG_PROMPT_THRESHOLD = 500
_presidio_anonymizer: Callable[[str], str] | None = None


def prompt_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def redact_pii(text: str) -> str:
    result = text
    for label, pattern in _PII_PATTERNS:
        result = pattern.sub(f"[{label}]", result)
    return result


def _init_presidio() -> Callable[[str], str] | None:
    global _presidio_anonymizer
    if _presidio_anonymizer is not None:
        return _presidio_anonymizer

    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine
    except ImportError:
        return None

    try:
        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        def _redact_with_presidio(value: str) -> str:
            results = analyzer.analyze(text=value, language="ru")
            return anonymizer.anonymize(text=value, analyzer_results=results).text

        _presidio_anonymizer = _redact_with_presidio
        return _presidio_anonymizer
    except Exception as exc:
        logger.debug("presidio_unavailable", error=str(exc))
        return None


def _redact_with_presidio(text: str) -> str:
    presidio = _init_presidio()
    if presidio is None:
        return redact_pii(text)
    regex_result = redact_pii(text)
    try:
        return presidio(regex_result)
    except Exception as exc:
        logger.debug("presidio_redact_failed", error=str(exc))
        return regex_result


async def redact_pii_for_log(raw: str) -> tuple[str, str]:
    """Return (prompt_hash, prompt_preview) without blocking on Presidio for long text."""
    digest = prompt_hash(raw)
    preview = redact_pii(raw)[:120]

    if len(raw) > _PRESIDIO_LONG_PROMPT_THRESHOLD:
        asyncio.create_task(_presidio_background(raw, digest))

    return digest, preview


async def _presidio_background(raw: str, digest: str) -> None:
    t0 = time.perf_counter()
    try:
        result = await asyncio.to_thread(_redact_with_presidio, raw)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "presidio_redact_completed",
            prompt_hash=digest,
            prompt_length=len(raw),
            presidio_latency_ms=elapsed_ms,
            preview=result[:120],
        )
    except Exception as exc:
        logger.debug("presidio_background_failed", prompt_hash=digest, error=str(exc))
