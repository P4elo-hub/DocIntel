import tiktoken

_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("o200k_base")
    return _encoding


def _content_to_text(content: str | list | dict | None) -> str:
    """Приводит OpenAI content (str или list[parts]) к тексту для оценки токенов."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                chunks.append(str(part.get("text", "")))
            elif part.get("type") == "image_url":
                chunks.append("[image]")
        return "\n".join(chunks)
    return str(content)


def count_tokens(messages: list[dict]) -> int:
    """Подсчёт токенов с поправкой ChatML: +4 на сообщение, +2 итого."""
    enc = _get_encoding()
    total = 2
    for msg in messages:
        total += 4
        total += len(enc.encode(msg.get("role", "")))
        total += len(enc.encode(_content_to_text(msg.get("content"))))
    return total


def fit_to_budget(messages: list[dict], budget: int) -> list[dict]:
    """Обрезает historic-часть с начала, сохраняя system-сообщения."""
    if not messages:
        return messages

    system_msgs = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    while rest and count_tokens(system_msgs + rest) > budget:
        rest.pop(0)

    return system_msgs + rest
