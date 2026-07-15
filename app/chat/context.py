from uuid import UUID

from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository


def message_content_for_llm(message: ChatMessage) -> str | list[dict]:
    media_part = None
    if message.media_refs and isinstance(message.media_refs, dict):
        media_part = message.media_refs.get("part")
    if media_part is None:
        return message.content
    parts: list[dict] = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    parts.append(media_part)
    return parts


async def build_sliding_context(
    repo: ChatRepository,
    chat: Chat,
    chat_id: UUID,
    *,
    context_window: int,
    system_prompt_body: str | None = None,
) -> list[dict]:
    """Sliding window: system_prompt + последние N сообщений."""
    messages: list[dict] = []
    effective_prompt = system_prompt_body or chat.system_prompt
    if effective_prompt:
        messages.append({"role": "system", "content": effective_prompt})

    history = await repo.list_messages(chat_id, limit=context_window)
    for msg in history:
        messages.append({"role": msg.role, "content": message_content_for_llm(msg)})

    return messages
