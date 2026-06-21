import hashlib
import json

from app.schemas.chat import ChatRequest

CHAT_CACHE_PREFIX = "chat"
FEATURES_CHAT_CACHE_PREFIX = "features_chat"


def chat_cache_key(prefix: str, req: ChatRequest) -> str:
    payload = req.model_dump(exclude={"user_id", "stream"})
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return f"{prefix}:{hashlib.sha256(blob.encode()).hexdigest()}"
