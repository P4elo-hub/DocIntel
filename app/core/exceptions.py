class LLMError(Exception):
    """Базовое доменное исключение слоя LLM."""


class LLMRateLimitError(LLMError):
    """Провайдер вернул rate limit."""


class LLMAuthError(LLMError):
    """Невалидный ключ или 401/403 от провайдера."""


class LLMTimeoutError(LLMError):
    """LLM не ответил вовремя."""


class LLMContentFilterError(LLMError):
    """Контент заблокирован модерацией."""


class SecurityValidationError(Exception):
    """Входной промпт отклонён защитным слоем."""

    def __init__(self, message: str, *, rule: str | None = None):
        super().__init__(message)
        self.rule = rule
