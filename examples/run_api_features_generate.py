"""Проверка DocIntel API: POST /features/generate (sectioned-генерация)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from api_common import check_response, ensure_server_hint, post_json, pretty_json
from demo_common import FEATURE_BRIEF, FEATURE_NAME, FEATURE_PROTOCOL, normalize_markdown_answer

ANSWERS_DIR = Path(__file__).resolve().parent / "answers"


async def main() -> int:
    ensure_server_hint()

    payload = {
        "feature_brief": FEATURE_BRIEF,
        "feature_name": FEATURE_NAME,
        "protocol": FEATURE_PROTOCOL,
    }

    print("POST /features/generate")
    print("Генерация может занять 3–8 минут...\n")

    response = await post_json("/features/generate", payload, timeout=600.0)
    check_response(response)

    data = response.json()
    print(f"Модель: {data.get('model')} | tool_calls_made: {data.get('tool_calls_made')}")

    ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ANSWERS_DIR / "api-features-generate-latest.md"
    output_path.write_text(normalize_markdown_answer(data["content"]), encoding="utf-8")
    print(f"Сохранено: {output_path}\n")

    preview = data["content"][:800]
    print(f"Превью ответа:\n{preview}\n...")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nПрервано.", file=sys.stderr)
        raise SystemExit(130) from None
