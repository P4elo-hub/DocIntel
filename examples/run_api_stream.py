"""Проверка SSE: POST /chat/stream и POST /features/chat/stream."""

from __future__ import annotations

import asyncio
import json

import httpx

from api_common import DEFAULT_BASE_URL, ensure_server_hint


def _parse_sse(body: str) -> list[dict]:
    events: list[dict] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        data = line.removeprefix("data: ").strip()
        if data == "[DONE]":
            events.append({"done": True})
            continue
        try:
            events.append(json.loads(data))
        except json.JSONDecodeError:
            events.append({"raw": data})
    return events


async def _stream(path: str, payload: dict) -> str:
    async with httpx.AsyncClient(base_url=DEFAULT_BASE_URL, timeout=120.0) as client:
        async with client.stream("POST", path, json=payload) as response:
            if response.status_code >= 400:
                text = await response.aread()
                raise RuntimeError(f"{path} → HTTP {response.status_code}: {text.decode()}")
            chunks: list[str] = []
            async for chunk in response.aiter_text():
                chunks.append(chunk)
            return "".join(chunks)


async def main() -> int:
    ensure_server_hint()

    generic_body = await _stream(
        "/chat/stream",
        {"messages": [{"role": "user", "content": "Считай от 1 до 3 через запятую."}]},
    )
    print("POST /chat/stream")
    print(_parse_sse(generic_body))

    docintel_body = await _stream(
        "/features/chat/stream",
        {"messages": [{"role": "user", "content": "Что такое event loop в asyncio?"}]},
    )
    print("\nPOST /features/chat/stream")
    print(_parse_sse(docintel_body))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
