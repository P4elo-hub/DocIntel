"""DocIntel: tool calling, sectioned docs, HTTP service layer."""

from app.services.docintel.client import ChatResult, SyncLLMClient, ToolCallClient
from app.services.docintel.providers import FallbackBackend, LlmCredentials, ProviderKind
from app.services.docintel.service import DocIntelService

__all__ = [
    "ChatResult",
    "DocIntelService",
    "FallbackBackend",
    "LlmCredentials",
    "ProviderKind",
    "SyncLLMClient",
    "ToolCallClient",
]
