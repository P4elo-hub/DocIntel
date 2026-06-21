import re
from typing import Final

from app.observability.pii import redact_pii

EMAIL_RE: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RU_RE: Final = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
)
PASSPORT_RU_RE: Final = re.compile(r"\b\d{4}\s?\d{6}\b")


def filter_output(answer: str, system_prompt: str, canary: str) -> str:
    """Режет утечку системного промпта и маскирует персональные данные в ответе."""
    if canary and canary in answer:
        raise ValueError("system_prompt leakage: canary detected")

    head = " ".join(system_prompt.split())[:80]
    if head and head.lower() in " ".join(answer.split()).lower():
        raise ValueError("system_prompt leakage: prefix detected")

    masked = EMAIL_RE.sub("[EMAIL]", answer)
    masked = PHONE_RU_RE.sub("[PHONE_RU]", masked)
    masked = PASSPORT_RU_RE.sub("[PASSPORT]", masked)
    return redact_pii(masked)
