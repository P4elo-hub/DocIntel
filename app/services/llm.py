import time
from collections.abc import AsyncIterator

import structlog
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.exceptions import (
    LLMAuthError,
    LLMContentFilterError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.observability.pii import redact_pii_for_log
from app.schemas.chat import ChatDelta, ChatRequest, ChatResponse, Usage
from app.services.cache import CHAT_CACHE_PREFIX, chat_cache_key

try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )
except ImportError:
    APIConnectionError = APITimeoutError = AuthenticationError = BadRequestError = RateLimitError = ()  # type: ignore

logger = structlog.get_logger("llm-service")


def _prompt_text(req: ChatRequest) -> str:
    return "\n".join(m.content for m in req.messages if m.content)


class LLMService:
    def __init__(self, llm, cache, ttl: int = 3600):
        self.llm = llm
        self.cache = cache
        self.ttl = ttl

    async def _log_llm_completion(
        self,
        req: ChatRequest,
        resp: ChatResponse,
        latency_ms: float,
        *,
        cached: bool = False,
    ) -> None:
        raw_prompt = _prompt_text(req)
        prompt_digest, prompt_preview = await redact_pii_for_log(raw_prompt)
        logger.info(
            "llm_request_completed",
            model=resp.model,
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
            latency_ms=round(latency_ms, 2),
            finish_reason=resp.finish_reason,
            prompt_hash=prompt_digest,
            prompt_preview=prompt_preview,
            cached=cached,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_not_exception_type(
            (LLMAuthError, LLMContentFilterError, LLMRateLimitError, LLMTimeoutError),
        ),
    )
    async def _call(self, req: ChatRequest) -> ChatResponse:
        t0 = time.perf_counter()
        try:
            raw = await self.llm.chat.completions.create(
                model=req.model,
                messages=[m.model_dump() for m in req.messages],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            )
            resp = ChatResponse.from_openai(raw)
        except RateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except BadRequestError as e:
            msg = str(e).lower()
            if "content" in msg and ("filter" in msg or "policy" in msg):
                raise LLMContentFilterError(str(e)) from e
            raise LLMError(str(e)) from e
        except APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e

        await self._log_llm_completion(req, resp, (time.perf_counter() - t0) * 1000)
        return resp

    async def complete(self, req: ChatRequest) -> ChatResponse:
        if req.temperature > 0 or self.cache is None:
            resp = await self._call(req)
            resp.cached = False
            return resp

        key = chat_cache_key(CHAT_CACHE_PREFIX, req)
        blob = await self.cache.get(key)
        if blob:
            resp = ChatResponse.model_validate_json(blob)
            resp.cached = True
            await self._log_llm_completion(req, resp, 0.0, cached=True)
            return resp

        resp = await self._call(req)
        resp.cached = False
        await self.cache.setex(key, self.ttl, resp.model_dump_json())
        return resp

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        t0 = time.perf_counter()
        stream = await self.llm.chat.completions.create(
            model=req.model,
            messages=[m.model_dump() for m in req.messages],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        finish_reason: str | None = None
        model = req.model
        usage: Usage | None = None

        async for chunk in stream:
            if getattr(chunk, "choices", None):
                choice = chunk.choices[0]
                reason = getattr(choice, "finish_reason", None)
                if isinstance(reason, str):
                    finish_reason = reason
                delta = choice.delta
                if getattr(delta, "content", None):
                    yield ChatDelta(content=delta.content)
            if getattr(chunk, "usage", None):
                usage = Usage.from_openai(chunk.usage)
                yield ChatDelta(usage=usage)
            chunk_model = getattr(chunk, "model", None)
            if isinstance(chunk_model, str):
                model = chunk_model

        if usage is not None:
            resp = ChatResponse(
                content="",
                model=model,
                usage=usage,
                finish_reason=finish_reason,
            )
            await self._log_llm_completion(req, resp, (time.perf_counter() - t0) * 1000)
