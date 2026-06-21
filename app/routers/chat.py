import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from structlog.contextvars import bind_contextvars

from app.core.config import get_settings
from app.core.exceptions import SecurityValidationError
from app.deps.providers import LLMServiceDep
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.security.guards import validate_chat_messages

router = APIRouter(prefix="/chat", tags=["chat"])

BATCH_SEM = asyncio.Semaphore(5)
BATCH_MAX = 20


@router.post(
    "",
    response_model=ChatResponse,
    summary="Синхронный чат",
    description="Отправляет сообщения в LLM и возвращает полный ответ.",
    responses={
        200: {"description": "Успешный ответ"},
        400: {"description": "Вход отклонён защитным слоем"},
        422: {"description": "Невалидный запрос"},
        429: {"description": "Rate limit провайдера"},
    },
)
async def chat_completions(
    req: ChatRequest,
    service: LLMServiceDep,
    request: Request,
) -> ChatResponse:
    validate_chat_messages(req.messages)
    if req.user_id:
        bind_contextvars(user_id=req.user_id)
    canary = getattr(request.app.state, "canary", "") if get_settings().security_enabled else ""
    resp = await service.complete(req, canary=canary)
    resp.request_id = getattr(request.state, "request_id", None)
    return resp


@router.post("/stream", summary="Streaming чат через SSE")
async def chat_stream(req: ChatRequest, service: LLMServiceDep, request: Request):
    validate_chat_messages(req.messages)

    async def event_source():
        canary = getattr(request.app.state, "canary", "") if get_settings().security_enabled else ""
        async for delta in service.stream(req, canary=canary):
            yield f"data: {delta.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/batch", summary="Batch чат: несколько запросов за раз")
async def chat_batch(
    reqs: list[ChatRequest],
    service: LLMServiceDep,
    request: Request,
) -> list[ChatResponse | dict]:
    if len(reqs) > BATCH_MAX:
        raise HTTPException(
            status_code=413,
            detail=f"Максимум {BATCH_MAX} запросов в batch",
        )

    canary = getattr(request.app.state, "canary", "") if get_settings().security_enabled else ""

    async def _one(r: ChatRequest):
        async with BATCH_SEM:
            try:
                validate_chat_messages(r.messages)
                return await service.complete(r, canary=canary)
            except SecurityValidationError as e:
                return {
                    "error": {
                        "code": "input_rejected",
                        "message": str(e),
                        "rule": e.rule,
                    }
                }
            except Exception as e:
                return {"error": type(e).__name__, "detail": str(e)}

    return await asyncio.gather(*(_one(r) for r in reqs))
