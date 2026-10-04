# syntax=docker/dockerfile:1.7

# ========== STAGE 1: BUILDER ==========
FROM python:3.13-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /uvx /bin/

WORKDIR /app

# extra `retrieval` (реранкер + гибридный поиск) ставится в образ, т.к. включены
# RAG_USE_RERANKER / RAG_USE_HYBRID. Тянет torch+sentence-transformers (~2 ГБ).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --extra retrieval

COPY app/ ./app/
COPY bot/ ./bot/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY feature-methodology-project/ ./feature-methodology-project/
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra retrieval

# ========== STAGE 2: RUNTIME ==========
FROM python:3.13-slim-bookworm

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /home/appuser/.cache/huggingface /app/var/chats \
    && chown -R appuser:appuser /home/appuser/.cache /app/var/chats

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app
COPY --chown=appuser:appuser .env.example ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/appuser/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/appuser/.cache/huggingface/sentence_transformers

# ENTRYPOINT стартует от root, чинит права на named volume hf_cache и
# дропает привилегии на appuser (см. docker/entrypoint.sh).
USER root
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/ready', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
