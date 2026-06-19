"""DocIntel HTTP service — обёртка над ToolCallClient для routers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.schemas.chat import ChatDelta, ChatRequest, ChatResponse, Message, Usage
from app.schemas.features import FeatureGenerateRequest, FeatureGenerateResponse
from app.services.docintel.client import ToolCallClient


def _messages_to_user_text(messages: list[Message]) -> str:
    parts: list[str] = []
    for message in messages:
        if message.role == "system":
            parts.append(f"[system]\n{message.content}")
        elif message.role == "user":
            parts.append(message.content)
        elif message.role == "assistant":
            parts.append(f"[assistant]\n{message.content}")
    return "\n\n".join(parts).strip()


def _last_user_message(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return _messages_to_user_text(messages)


class DocIntelService:
    """DocIntel API: sectioned-генерация, tool calling, stream."""

    def __init__(self, client: ToolCallClient) -> None:
        self._client = client

    async def generate_feature(self, req: FeatureGenerateRequest) -> FeatureGenerateResponse:
        result = await self._client.chat_sectioned_json(
            req.feature_brief,
            feature_name=req.feature_name,
            protocol=req.protocol,
        )
        return FeatureGenerateResponse(
            content=result["answer"],
            model=result["model"],
            tool_calls_made=result["tool_calls_made"],
            feature_name=req.feature_name,
            protocol=req.protocol,
        )

    async def chat_with_tools(self, req: ChatRequest) -> ChatResponse:
        user_message = _last_user_message(req.messages)
        result = await self._client.chat_json(user_message)
        return ChatResponse(
            content=result["answer"],
            model=result["model"],
            usage=Usage(),
            finish_reason="stop",
            cached=False,
        )

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        prompt = _last_user_message(req.messages)
        model = req.model if req.model != "gpt-4o-mini" else None
        async for delta in self._client.stream_chat(prompt, model=model):
            yield ChatDelta(content=delta)
