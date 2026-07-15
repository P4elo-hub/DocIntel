from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

MessageRole = Literal["user", "assistant", "system"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    chat_id: UUID
    role: MessageRole
    content: str
    media_refs: dict | None = None
    tokens: int | None = None
    prompt_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    owner_external_id: str
    interface: str
    system_prompt: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SystemPrompt(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    body: str
    traffic_pct: int
