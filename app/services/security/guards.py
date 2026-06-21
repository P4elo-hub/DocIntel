from app.core.config import get_settings
from app.core.exceptions import SecurityValidationError
from app.services.security.input_validator import validate_input


def validate_chat_messages(messages) -> None:
    if not get_settings().security_enabled:
        return
    for msg in messages:
        if msg.role != "user":
            continue
        result = validate_input(msg.content)
        if not result.ok:
            raise SecurityValidationError(result.reason or "input rejected", rule=result.rule)
