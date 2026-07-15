from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.llm_client import FallbackLLMClient


@pytest.fixture
def primary_client():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="primary"))])
    )
    client.close = AsyncMock()
    return client


@pytest.fixture
def fallback_client():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="deepseek"))])
    )
    client.close = AsyncMock()
    return client


async def test_uses_primary_when_available(primary_client, fallback_client):
    llm = FallbackLLMClient(
        primary_client,
        primary_model="gpt-4o-mini",
        fallback=fallback_client,
        fallback_model="deepseek-chat",
    )

    await llm.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    primary_client.chat.completions.create.assert_awaited_once()
    fallback_client.chat.completions.create.assert_not_awaited()


async def test_falls_back_to_deepseek_on_primary_error(primary_client, fallback_client):
    primary_client.chat.completions.create.side_effect = Exception("401 invalid key")
    llm = FallbackLLMClient(
        primary_client,
        primary_model="gpt-4o-mini",
        fallback=fallback_client,
        fallback_model="deepseek-chat",
    )

    await llm.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])

    primary_client.chat.completions.create.assert_awaited_once()
    fallback_client.chat.completions.create.assert_awaited_once()
    _, kwargs = fallback_client.chat.completions.create.await_args
    assert kwargs["model"] == "deepseek-chat"


async def test_raises_when_fallback_disabled(primary_client):
    primary_client.chat.completions.create.side_effect = Exception("boom")
    llm = FallbackLLMClient(
        primary_client,
        primary_model="gpt-4o-mini",
        fallback=None,
        fallback_model=None,
        enable_fallback=False,
    )

    with pytest.raises(Exception, match="boom"):
        await llm.chat.completions.create(messages=[{"role": "user", "content": "hi"}])


async def test_audio_uses_primary_when_available(primary_client, fallback_client):
    primary_client.audio.transcriptions.create = AsyncMock(
        return_value=MagicMock(text="привет"),
    )
    llm = FallbackLLMClient(
        primary_client,
        primary_model="gpt-4o-mini",
        fallback=fallback_client,
        fallback_model="deepseek-chat",
    )

    result = await llm.audio.transcriptions.create(model="whisper-1", file=MagicMock())

    assert result.text == "привет"
    primary_client.audio.transcriptions.create.assert_awaited_once()


async def test_audio_raises_voice_unavailable_when_primary_fails(
    primary_client, fallback_client,
):
    from app.core.exceptions import VoiceUnavailableError

    primary_client.audio.transcriptions.create = AsyncMock(
        side_effect=Exception("401 invalid key"),
    )
    llm = FallbackLLMClient(
        primary_client,
        primary_model="gpt-4o-mini",
        fallback=fallback_client,
        fallback_model="deepseek-chat",
    )

    with pytest.raises(VoiceUnavailableError, match="голосовые"):
        await llm.audio.transcriptions.create(model="whisper-1", file=MagicMock())
