import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import aiofiles

from app.chat.domain import Chat, ChatMessage


class JsonChatRepository:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _chat_dir(self, chat_id: UUID) -> Path:
        return self.base_dir / "chats" / str(chat_id)

    def _messages_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "messages.jsonl"

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        chat = Chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )
        chat_dir = self._chat_dir(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(chat_dir / "chat.json", "w", encoding="utf-8") as f:
            await f.write(chat.model_dump_json())
        return chat

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        chats_root = self.base_dir / "chats"
        if chats_root.exists():
            for chat_dir in chats_root.iterdir():
                meta = chat_dir / "chat.json"
                if not meta.exists():
                    continue
                async with aiofiles.open(meta, encoding="utf-8") as f:
                    content = await f.read()
                chat = Chat.model_validate_json(content)
                if (
                    chat.owner_external_id == owner_external_id
                    and chat.interface == interface
                ):
                    return chat
        return await self.create_chat(owner_external_id, interface, system_prompt)

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        path = self._chat_dir(chat_id) / "chat.json"
        if not path.exists():
            return None
        async with aiofiles.open(path, encoding="utf-8") as f:
            content = await f.read()
        return Chat.model_validate_json(content)

    async def append_message(self, chat_id: UUID, message: ChatMessage) -> ChatMessage:
        path = self._messages_path(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(path, "a", encoding="utf-8") as f:
            await f.write(message.model_dump_json() + "\n")
        return message

    async def list_messages(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]:
        path = self._messages_path(chat_id)
        if not path.exists():
            return []

        async with aiofiles.open(path, encoding="utf-8") as f:
            lines = await f.readlines()

        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "soft_delete":
                start_idx = i + 1

        messages: list[ChatMessage] = []
        for line in lines[start_idx:]:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "soft_delete":
                continue
            messages.append(ChatMessage.model_validate_json(stripped))

        return messages[-limit:]

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        path = self._messages_path(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        marker = json.dumps(
            {"type": "soft_delete", "at": datetime.now(UTC).isoformat()},
            ensure_ascii=False,
        )
        async with aiofiles.open(path, "a", encoding="utf-8") as f:
            await f.write(marker + "\n")
