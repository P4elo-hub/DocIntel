from uuid import uuid4

from app.chat.domain import ChatMessage


async def test_create_and_get_chat(chat_repository):
    chat = await chat_repository.create_chat(
        owner_external_id="tg-12345",
        interface="telegram",
        system_prompt="Ты ассистент.",
    )
    loaded = await chat_repository.get_chat(chat.id)
    assert loaded is not None
    assert loaded.id == chat.id
    assert loaded.owner_external_id == "tg-12345"
    assert loaded.interface == "telegram"
    assert loaded.system_prompt == "Ты ассистент."


async def test_append_and_list_messages_chronological(chat_repository):
    chat = await chat_repository.create_chat(owner_external_id="u1", interface="web")
    for i in range(3):
        await chat_repository.append_message(
            chat.id,
            ChatMessage(chat_id=chat.id, role="user", content=f"msg-{i}"),
        )

    messages = await chat_repository.list_messages(chat.id)
    assert len(messages) == 3
    assert [m.content for m in messages] == ["msg-0", "msg-1", "msg-2"]


async def test_list_messages_returns_last_n(chat_repository):
    chat = await chat_repository.create_chat(owner_external_id="u1", interface="web")
    for i in range(5):
        await chat_repository.append_message(
            chat.id,
            ChatMessage(chat_id=chat.id, role="user", content=f"msg-{i}"),
        )

    messages = await chat_repository.list_messages(chat.id, limit=2)
    assert len(messages) == 2
    assert [m.content for m in messages] == ["msg-3", "msg-4"]


async def test_soft_delete_clears_history_but_keeps_new(chat_repository):
    chat = await chat_repository.create_chat(owner_external_id="u1", interface="web")
    await chat_repository.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="user", content="old"),
    )
    await chat_repository.soft_delete_messages(chat.id)
    assert await chat_repository.list_messages(chat.id) == []

    await chat_repository.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="user", content="new"),
    )
    messages = await chat_repository.list_messages(chat.id)
    assert len(messages) == 1
    assert messages[0].content == "new"


async def test_get_unknown_chat_returns_none(chat_repository):
    assert await chat_repository.get_chat(uuid4()) is None
    assert await chat_repository.list_messages(uuid4()) == []
