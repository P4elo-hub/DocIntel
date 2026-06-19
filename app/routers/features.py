import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.deps.providers import DocIntelServiceDep
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.features import FeatureGenerateRequest, FeatureGenerateResponse

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
    description="Классический цикл LLM tool calling (write_feature_doc, search_kb, kit-tools).",
)
async def docintel_chat(req: ChatRequest, service: DocIntelServiceDep) -> ChatResponse:
    return await service.chat_with_tools(req)


@router.post("/chat/stream", summary="DocIntel streaming через SSE")
async def docintel_chat_stream(req: ChatRequest, service: DocIntelServiceDep):
    async def event_source():
        async for delta in service.stream(req):
            yield f"data: {delta.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
