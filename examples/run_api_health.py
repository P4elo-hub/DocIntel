"""Проверка /health и /ready (сервер должен быть запущен)."""

from __future__ import annotations

import asyncio

from api_common import check_response, ensure_server_hint, get, pretty_json


async def main() -> int:
    ensure_server_hint()

    health = await get("/health")
    check_response(health)
    print("GET /health")
    print(pretty_json(health.json()))

    ready = await get("/ready")
    check_response(ready)
    print("\nGET /ready")
    print(pretty_json(ready.json()))

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
