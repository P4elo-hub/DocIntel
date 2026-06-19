"""Проверка DocIntel API: POST /features/chat (tool calling)."""

from __future__ import annotations

import asyncio

from api_common import check_response, ensure_server_hint, post_json, pretty_json


async def main() -> int:
    ensure_server_hint()

    payload = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Найди в проектной документации информацию про Confluence import "
                    "и кратко опиши, что это такое."
                ),
            }
        ],
    }

    response = await post_json("/features/chat", payload, timeout=120.0)
    check_response(response)

    print("POST /features/chat")
    print(pretty_json(response.json()))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
