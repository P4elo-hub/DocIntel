import asyncio
import os
import sys

import httpx

BASE = os.environ.get("LOAD_TEST_BASE", "http://localhost:8000")
LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        payload = {"messages": [{"role": "user", "content": "ping"}]}
        headers = {"X-User-Id": "load-test-user"}

        statuses: list[int] = []
        for i in range(LIMIT + 1):
            resp = await client.post("/chat", json=payload, headers=headers)
            statuses.append(resp.status_code)
            print(f"request {i + 1}: {resp.status_code}")

        if statuses[-1] != 429:
            print(f"FAIL: expected 429 on request {LIMIT + 1}, got {statuses[-1]}")
            return 1

        if not all(s == 200 for s in statuses[:-1]):
            print(f"FAIL: expected 200 for first {LIMIT} requests, got {statuses[:-1]}")
            return 1

    print("OK: rate limit enforced")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
