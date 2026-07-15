import re

import pytest

from app.observability.pii import mask_pii, prompt_hash, redact_pii

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


def test_mask_email():
    assert mask_pii("write to user@example.com") == "write to [EMAIL]"


def test_mask_phone_ru_format():
    assert "[PHONE]" in mask_pii("звоните +7 (495) 123-45-67")


def test_mask_card_number():
    assert mask_pii("card 1234567812345678 ok") == "card [CARD] ok"


def test_mask_passthrough_clean_text():
    assert mask_pii("обычный текст") == "обычный текст"


def test_mask_empty_string():
    assert mask_pii("") == ""


def test_mask_multiple_pii_in_one_string():
    res = mask_pii("a@b.com, +7 495 111-22-33, 1111222233334444")
    assert "[EMAIL]" in res
    assert "[PHONE]" in res
    assert "[CARD]" in res
