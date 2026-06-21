import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.deps.providers import DocIntelServiceDep
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.features import FeatureGenerateRequest, FeatureGenerateResponse
from app.services.security.guards import validate_chat_messages

router = APIRouter(prefix="/features", tags=["features"])

BATCH_SEM = asyncio.Semaphore(3)
BATCH_MAX = 5


@router.post(
    "/generate",
    response_model=FeatureGenerateResponse,
    summary="Sectioned-генерация документации фичи",
    description=(
        "DocIntel: kit-tools → LLM по секциям → склейка по корпоративному shablon.md."
    ),
    responses={
        200: {"description": "Сгенерированный markdown-документ"},
        422: {"description": "Невалидный запрос"},
        502: {"description": "Ошибка LLM-провайдера"},
    },
)
async def generate_feature(
    req: FeatureGenerateRequest,
    service: DocIntelServiceDep,
) -> FeatureGenerateResponse:
    return await service.generate_feature(req)


@router.post(
    "/generate/batch",
    summary="Batch sectioned-генерация (до 5 фич)",
)
async def generate_feature_batch(
    reqs: list[FeatureGenerateRequest],
    service: DocIntelServiceDep,
) -> list[FeatureGenerateResponse | dict]:
    if len(reqs) > BATCH_MAX:
        raise HTTPException(
            status_code=413,
            detail=f"Максимум {BATCH_MAX} запросов в batch",
        )

    async def _one(r: FeatureGenerateRequest):
        async with BATCH_SEM:
            try:
                return await service.generate_feature(r)
            except Exception as e:
                return {"error": type(e).__name__, "detail": str(e)}

    return await asyncio.gather(*(_one(r) for r in reqs))


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="DocIntel chat с tool calling",
    description=(
        "Классический цикл LLM tool calling (write_feature_doc, search_kb, kit-tools). "
        "При temperature=0 ответы без вызова tools кешируются в Redis (префикс features_chat:)."
    ),
    responses={
        200: {"description": "Успешный ответ"},
        400: {"description": "Вход отклонён защитным слоем"},
        502: {"description": "Ошибка LLM или утечка system prompt"},
    },
)
async def docintel_chat(
    req: ChatRequest,
    service: DocIntelServiceDep,
    request: Request,
) -> ChatResponse:
    validate_chat_messages(req.messages)
    canary = getattr(request.app.state, "canary", "") if get_settings().security_enabled else ""
    resp = await service.chat_with_tools(req, canary=canary)
    resp.request_id = getattr(request.state, "request_id", None)
    return resp


@router.post("/chat/stream", summary="DocIntel streaming через SSE")
async def docintel_chat_stream(
    req: ChatRequest,
    service: DocIntelServiceDep,
    request: Request,
):
    validate_chat_messages(req.messages)
    canary = getattr(request.app.state, "canary", "") if get_settings().security_enabled else ""

    async def event_source():
        async for delta in service.stream(req, canary=canary):
            yield f"data: {delta.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
