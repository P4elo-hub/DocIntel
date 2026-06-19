"""Проверка generic LLM API: POST /chat."""

from __future__ import annotations

import asyncio

from api_common import check_response, ensure_server_hint, post_json, pretty_json


async def main() -> int:
    ensure_server_hint()

    payload = {
        "messages": [
            {"role": "system", "content": "Ты лаконичный ассистент."},
            {"role": "user", "content": "Скажи привет одним словом."},
        ],
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 50,
    }

    response = await post_json("/chat", payload, timeout=60.0)
    check_response(response)

    print("POST /chat")
    print(f"X-Request-ID: {response.headers.get('x-request-id')}")
    print(f"X-LLM-Cost-USD: {response.headers.get('x-llm-cost-usd')}")
    print(pretty_json(response.json()))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
