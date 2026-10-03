#!/usr/bin/env python3
"""Короткий HTTP-smoke пути бота: POST /chats → multipart SSE messages.

Проверяет 1–2 кейса без Telegram: ответ + sources на живом app.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_multipart_sse(
    url: str,
    content: str,
    *,
    owner: str,
    timeout: int = 300,
) -> tuple[str, list[dict], list[dict]]:
    """Возвращает (answer_text, sources, events)."""
    boundary = "----DocIntelSmokeBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="content"\r\n\r\n'
        f"{content}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Owner-External-Id": owner,
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    answer_parts: list[str] = []
    sources: list[dict] = []
    events: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = ""
        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                events.append(event)
                et = event.get("type")
                if et == "token":
                    answer_parts.append(event.get("delta") or "")
                elif et == "sources":
                    sources = list(event.get("sources") or [])
                elif et == "error":
                    raise RuntimeError(
                        f"SSE error: {event.get('code')} {event.get('message')}"
                    )
    return "".join(answer_parts), sources, events


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument(
        "--query",
        action="append",
        dest="queries",
        default=None,
        help="User query (repeatable). Defaults to 2 smoke queries.",
    )
    args = p.parse_args()
    queries = args.queries or [
        "Приведи пример ответа GetTradeOrders из Order Gateway.",
        "Приведи пример операции по обмену GET_LINKED_EVENTS из БПХ.",
    ]
    owner = "http-agent-smoke"
    base = args.base.rstrip("/")

    created = _post_json(
        f"{base}/chats",
        {
            "owner_external_id": owner,
            "interface": "cli",
            "system_prompt": None,
        },
    )
    chat_id = created["chat_id"]
    print(f"chat_id={chat_id}")

    # Чистый чат на всякий случай.
    try:
        req = urllib.request.Request(
            f"{base}/chats/{chat_id}/messages",
            method="DELETE",
            headers={"X-Owner-External-Id": owner},
        )
        urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError:
        pass

    failed = 0
    for q in queries:
        print(f"\n--- query: {q[:100]} ---")
        answer, sources, events = "", [], []
        for attempt in range(1, 4):
            answer, sources, events = _post_multipart_sse(
                f"{base}/chats/{chat_id}/messages",
                q,
                owner=owner,
            )
            if "ещё не готова" not in answer:
                break
            print(f"  retry {attempt}: RAG not ready yet")
            import time

            time.sleep(5)
        types = [e.get("type") for e in events]
        has_sources_hdr = bool(re.search(r"(?im)^#{1,3}\s*Источники\b", answer))
        ok = (
            bool(answer.strip())
            and "ещё не готова" not in answer
            and (bool(sources) or has_sources_hdr)
        )
        print(f"events={types}")
        print(f"answer_chars={len(answer)} sources={len(sources)} hdr={has_sources_hdr}")
        if sources:
            print("files:", [s.get("file_name") for s in sources[:5]])
        print("preview:", answer[:400].replace("\n", " "))
        if not ok:
            print("FAIL")
            failed += 1
        else:
            print("PASS")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
