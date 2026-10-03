import hashlib
import json

from app.schemas.chat import ChatRequest

CHAT_CACHE_PREFIX = "chat"
FEATURES_CHAT_CACHE_PREFIX = "features_chat"
# Версия префикса: поднимай при смене формата ответа агентов (kits/UML и т.п.),
# чтобы не отдавать устаревшие документы из Redis.
AGENT_CHAT_CACHE_PREFIX = "agent_chat:v12"


def chat_cache_key(prefix: str, req: ChatRequest) -> str:
    payload = req.model_dump(exclude={"user_id", "stream"})
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return f"{prefix}:{hashlib.sha256(blob.encode()).hexdigest()}"


def agent_query_cache_key(query: str) -> str:
    """Exact-match ключ для Telegram/web agent-пайплайна (слово в слово после strip)."""
    normalized = (query or "").strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{AGENT_CHAT_CACHE_PREFIX}:{digest}"
