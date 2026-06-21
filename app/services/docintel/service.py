"""DocIntel HTTP service — обёртка над ToolCallClient для routers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.exceptions import LLMError
from app.schemas.chat import ChatDelta, ChatRequest, ChatResponse, Message, Usage
from app.schemas.features import FeatureGenerateRequest, FeatureGenerateResponse
from app.services.cache import FEATURES_CHAT_CACHE_PREFIX, chat_cache_key
from app.services.docintel.client import ToolCallClient
from app.services.security.output_filter import filter_output


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

    def __init__(
        self,
        client: ToolCallClient,
        cache=None,
        ttl: int = 3600,
    ) -> None:
        self._client = client
        self._cache = cache
        self._ttl = ttl

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

    async def chat_with_tools(self, req: ChatRequest, *, canary: str = "") -> ChatResponse:
        cache_key: str | None = None
        if req.temperature == 0 and self._cache is not None:
            cache_key = chat_cache_key(FEATURES_CHAT_CACHE_PREFIX, req)
            blob = await self._cache.get(cache_key)
            if blob:
                resp = ChatResponse.model_validate_json(blob)
                resp.cached = True
                return resp

        user_message = _last_user_message(req.messages)
        result = await self._client.chat_json(user_message, canary=canary)
        content = result["answer"]
        if canary:
            try:
                content = filter_output(
                    content,
                    self._client.system_prompt_text(canary=canary),
                    canary,
                )
            except ValueError as e:
                raise LLMError(str(e)) from e

        resp = ChatResponse(
            content=content,
            model=result["model"],
            usage=Usage(),
            finish_reason="stop",
            cached=False,
        )

        if (
            cache_key is not None
            and result["tool_calls_made"] == 0
        ):
            await self._cache.setex(cache_key, self._ttl, resp.model_dump_json())

        return resp

    async def stream(self, req: ChatRequest, *, canary: str = "") -> AsyncIterator[ChatDelta]:
        prompt = _last_user_message(req.messages)
        model = req.model if req.model != "gpt-4o-mini" else None
        async for delta in self._client.stream_chat(prompt, model=model, canary=canary):
            yield ChatDelta(content=delta)
