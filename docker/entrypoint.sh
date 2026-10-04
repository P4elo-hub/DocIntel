#!/bin/sh
# Named volume hf_cache часто создаётся как root:root и перекрывает
# /home/appuser/.cache/huggingface — тогда appuser не может скачать веса
# bge-reranker и RAG тихо уходит в dense-only.
set -e

mkdir -p /home/appuser/.cache/huggingface /app/var/chats
chown -R appuser:appuser /home/appuser/.cache /app/var/chats

# Контейнер стартует как root → HOME=/root. После drop privileges asyncpg/HF
# иначе лезут в /root/.* и получают Permission denied.
export HOME=/home/appuser
export USER=appuser
export LOGNAME=appuser

exec setpriv --reuid=appuser --regid=appuser --init-groups -- "$@"
