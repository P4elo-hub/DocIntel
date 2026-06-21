import re

import pytest

from app.observability.pii import prompt_hash, redact_pii

PII_SAMPLE = (
    "Мой email ivan@mail.ru, тел +7 (999) 123-45-67, карта 4111 1111 1111 1111"
)

RAW_PII_FRAGMENTS = [
    "ivan@mail.ru",
    "+7 (999) 123-45-67",
    "4111 1111 1111 1111",
]

EXPECTED_PLACEHOLDERS = ["[EMAIL]", "[PHONE_RU]", "[CARD]"]


def test_redact_pii_replaces_all_sensitive_fragments():
    preview = redact_pii(PII_SAMPLE)[:120]

    for fragment in RAW_PII_FRAGMENTS:
        assert fragment not in preview, f"PII fragment leaked: {fragment!r}"

    for placeholder in EXPECTED_PLACEHOLDERS:
        assert placeholder in preview, f"Missing placeholder: {placeholder}"


def test_redact_pii_inn_and_passport():
    text = "ИНН 7707083893, паспорт 4510 123456"
    redacted = redact_pii(text)
    assert "7707083893" not in redacted
    assert "4510 123456" not in redacted
    assert "[INN]" in redacted
    assert "[PASSPORT]" in redacted


def test_prompt_hash_is_stable():
    assert prompt_hash("hello") == prompt_hash("hello")
    assert prompt_hash("hello") != prompt_hash("world")


def test_redact_pii_fails_if_masking_removed():
    """Guard: если убрать маскирование, тест должен падать."""
    preview = redact_pii(PII_SAMPLE)[:120]
    assert not re.search(r"ivan@mail\.ru", preview)
    assert not re.search(r"4111\s+1111\s+1111\s+1111", preview)
