#!/usr/bin/env python3
"""CLI: прогон golden dataset через DocIntel и LLM-as-judge (G-Eval)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.schemas.chat import ChatRequest, Message
from app.services.docintel import DocIntelService, ToolCallClient
from app.utils.json_parse import parse_json_object

JUDGE_PROMPT = """Ты — независимый оценщик качества ответов AI-ассистента DocIntel для системных аналитиков.

Сравни ответ кандидата с эталоном по вопросу пользователя.

Вопрос: {question}

Эталонный ответ:
{expected_answer}

Ключевые слова/синонимы (любое совпадение повышает оценку): {keywords}

Ответ кандидата:
{answer}

Оцени по шкале 1–5:
- relevance — насколько ответ относится к вопросу
- correctness — фактическая точность относительно эталона
- completeness — полнота покрытия ключевых аспектов

Сначала проанализируй (reasoning), затем выставь scores, затем однострочное explanation.

Верни ТОЛЬКО JSON с полями в порядке: reasoning, relevance, correctness, completeness, explanation.
"""


def load_golden(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "version" not in data or "items" not in data:
        raise ValueError("golden dataset must contain version and items")
    return data


def select_golden_items(
    items: list[dict],
    *,
    limit: int | None = None,
    ids: list[str] | None = None,
) -> list[dict]:
    """Выбирает подмножество golden items по id или limit."""
    if ids:
        by_id = {item["id"]: item for item in items}
        missing = [item_id for item_id in ids if item_id not in by_id]
        if missing:
            available = ", ".join(by_id)
            raise ValueError(
                f"Unknown golden item id(s): {', '.join(missing)}. Available: {available}"
            )
        return [by_id[item_id] for item_id in ids]
    if limit is not None:
        return items[:limit]
    return items


async def ask_app(question: str, *, temperature: float = 0.0) -> tuple[str, str]:
    settings = get_settings()
    client = ToolCallClient(settings=settings, provider="primary")
    service = DocIntelService(client=client, cache=None)
    try:
        req = ChatRequest(
            messages=[Message(role="user", content=question)],
            temperature=temperature,
        )
        resp = await service.chat_with_tools(req)
        return resp.content, resp.model
    finally:
        await client.aclose()


async def judge_answer(
    judge_client: AsyncOpenAI,
    judge_model: str,
    *,
    question: str,
    expected_answer: str,
    expected_keywords: list[str],
    answer: str,
) -> dict:
    prompt = JUDGE_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        keywords=", ".join(expected_keywords),
        answer=answer,
    )
    response = await judge_client.chat.completions.create(
        model=judge_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    parsed = parse_json_object(raw)
    return {
        "reasoning": parsed.get("reasoning", ""),
        "scores": {
            "relevance": float(parsed.get("relevance", 0)),
            "correctness": float(parsed.get("correctness", 0)),
            "completeness": float(parsed.get("completeness", 0)),
        },
        "explanation": parsed.get("explanation", ""),
    }


def compute_aggregates(items: list[dict]) -> dict:
    if not items:
        return {
            "relevance_avg": 0.0,
            "correctness_avg": 0.0,
            "completeness_avg": 0.0,
            "min_correctness": 0.0,
        }
    relevances = [i["scores"]["relevance"] for i in items]
    correctnesses = [i["scores"]["correctness"] for i in items]
    completenesses = [i["scores"]["completeness"] for i in items]
    return {
        "relevance_avg": round(sum(relevances) / len(relevances), 4),
        "correctness_avg": round(sum(correctnesses) / len(correctnesses), 4),
        "completeness_avg": round(sum(completenesses) / len(completenesses), 4),
        "min_correctness": round(min(correctnesses), 4),
    }


async def run_evaluation(
    golden_path: Path,
    judge_model: str,
    out_path: Path,
    *,
    limit: int | None = None,
    item_ids: list[str] | None = None,
) -> dict:
    golden = load_golden(golden_path)
    items = select_golden_items(golden["items"], limit=limit, ids=item_ids)
    settings = get_settings()
    judge_client = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        timeout=settings.llm.request_timeout,
    )

    model_under_test = settings.llm.default_model
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()
    evaluated_items: list[dict] = []

    try:
        for item in items:
            question = item["question"]
            print(f"Evaluating {item['id']}: {question[:60]}…")
            answer, used_model = await ask_app(question, temperature=0.0)
            model_under_test = used_model
            verdict = await judge_answer(
                judge_client,
                judge_model,
                question=question,
                expected_answer=item["expected_answer"],
                expected_keywords=item.get("expected_keywords", []),
                answer=answer,
            )
            evaluated_items.append(
                {
                    "id": item["id"],
                    "question": question,
                    "answer": answer,
                    "scores": verdict["scores"],
                    "reasoning": verdict["reasoning"],
                    "explanation": verdict["explanation"],
                }
            )
    finally:
        await judge_client.close()

    result = {
        "run_id": run_id,
        "timestamp": timestamp,
        "model_under_test": model_under_test,
        "judge_model": judge_model,
        "golden_version": golden["version"],
        "items": evaluated_items,
        "aggregates": compute_aggregates(evaluated_items),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved run to {out_path}")
    print(f"Aggregates: {result['aggregates']}")
    return result


def parse_args() -> argparse.Namespace:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    default_out = ROOT / "eval" / "runs" / f"{today}.json"
    parser = argparse.ArgumentParser(description="Run golden dataset evaluation")
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "eval" / "golden_dataset.json",
        help="Path to golden dataset JSON",
    )
    parser.add_argument(
        "--judge",
        default="gpt-5.2",
        help="Judge model (gpt-5.2 or gpt-5)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help="Output path for run results",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only first N items (for smoke runs)",
    )
    parser.add_argument(
        "--id",
        dest="item_ids",
        action="append",
        default=None,
        metavar="ITEM_ID",
        help="Evaluate only item(s) with this id (repeatable)",
    )
    return parser.parse_args()


def main() -> None:
    try:
        get_settings()
    except ValidationError:
        print("ERROR: OPENAI_API_KEY or LLM__OPENAI_API_KEY required", file=sys.stderr)
        sys.exit(2)
    args = parse_args()
    try:
        asyncio.run(
            run_evaluation(
                args.golden,
                args.judge,
                args.out,
                limit=args.limit,
                item_ids=args.item_ids,
            )
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
