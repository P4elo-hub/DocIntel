"""Общие утилиты для HTTP-примеров (FastAPI-сервис)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

EXAMPLES_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXAMPLES_DIR.parent
DEFAULT_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def ensure_server_hint() -> None:
    print(f"Base URL: {DEFAULT_BASE_URL}")
    print("Сначала запустите сервер в другом терминале:")
    print(f"  cd {PROJECT_ROOT}")
    print("  uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000\n")


def pretty_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


async def get(path: str) -> httpx.Response:
    async with httpx.AsyncClient(base_url=DEFAULT_BASE_URL, timeout=60.0) as client:
        return await client.get(path)


async def post_json(path: str, payload: object, *, timeout: float = 300.0) -> httpx.Response:
    async with httpx.AsyncClient(base_url=DEFAULT_BASE_URL, timeout=timeout) as client:
        return await client.post(path, json=payload)


def check_response(response: httpx.Response, *, expect_ok: bool = True) -> None:
    if expect_ok and response.status_code >= 400:
        print(f"HTTP {response.status_code}", file=sys.stderr)
        try:
            print(pretty_json(response.json()), file=sys.stderr)
        except Exception:
            print(response.text, file=sys.stderr)
        raise SystemExit(1)
