#!/usr/bin/env python3
"""CLI: eval для POST /features/generate (sectioned-генерация по methodology examples)."""

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
from app.schemas.features import FeatureGenerateRequest
from app.services.docintel import DocIntelService, ToolCallClient
from eval.gate_checks import compute_gate_aggregates, run_item_quality_gates
from eval.run_evaluation import compute_aggregates, judge_answer, load_golden, select_golden_items

METHODOLOGY_DIR = ROOT / "feature-methodology-project"


def validate_methodology_refs(golden: dict) -> None:
    refs = (
        "methodology_ref",
        "template_ref",
        "spec_ref",
        "gate_ref",
    )
    for item in golden["items"]:
        for key in refs:
            ref = item.get(key)
            if ref and not (METHODOLOGY_DIR / ref).is_file():
                raise FileNotFoundError(f"{item['id']}: missing {key}: {ref}")
        for gate_spec in item.get("quality_gates", []):
            gate_ref = gate_spec.get("gate_ref")
            if gate_ref and not (METHODOLOGY_DIR / gate_ref).is_file():
                raise FileNotFoundError(f"{item['id']}: missing quality_gate: {gate_ref}")


async def ask_generate(item: dict) -> tuple[str, str, int]:
    settings = get_settings()
    client = ToolCallClient(settings=settings, provider="primary")
    service = DocIntelService(client=client, cache=None)
    try:
        req = FeatureGenerateRequest(
            feature_brief=item["feature_brief"],
            feature_name=item.get("feature_name"),
            protocol=item.get("protocol"),
        )
        resp = await service.generate_feature(req)
        return resp.content, resp.model, resp.tool_calls_made
    finally:
        await client.aclose()


def check_must_not_contain(answer: str, forbidden: list[str]) -> list[str]:
    violations = []
    lower = answer.lower()
    for phrase in forbidden:
        if phrase.lower() in lower:
            violations.append(phrase)
    return violations


async def run_evaluation_generate(
    golden_path: Path,
    judge_model: str,
    out_path: Path,
    *,
    limit: int | None = None,
    item_ids: list[str] | None = None,
) -> dict:
    golden = load_golden(golden_path)
    validate_methodology_refs(golden)

    settings = get_settings()
    judge_client = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        timeout=settings.llm.request_timeout,
    )

    model_under_test = settings.llm.default_model
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()
    evaluated_items: list[dict] = []
    items = select_golden_items(golden["items"], limit=limit, ids=item_ids)

    try:
        for item in items:
            label = item.get("question") or item["feature_brief"]
            print(
                f"Evaluating {item['id']} [{item.get('tool', '?')}]: "
                f"{label[:55]}…"
            )
            answer, used_model, tool_calls = await ask_generate(item)
            model_under_test = used_model

            forbidden = item.get("must_not_contain", [])
            violations = check_must_not_contain(answer, forbidden)
            gate_summary = run_item_quality_gates(item, answer)

            verdict = await judge_answer(
                judge_client,
                judge_model,
                question=label,
                expected_answer=item["expected_answer"],
                expected_keywords=item.get("expected_keywords", []),
                answer=answer,
            )

            evaluated_items.append(
                {
                    "id": item["id"],
                    "question": label,
                    "feature_brief": item["feature_brief"],
                    "methodology_ref": item.get("methodology_ref"),
                    "template_ref": item.get("template_ref"),
                    "spec_ref": item.get("spec_ref"),
                    "gate_ref": item.get("gate_ref"),
                    "gate_blocking_ids": item.get("gate_blocking_ids"),
                    "quality_gates": item.get("quality_gates"),
                    "tool": item.get("tool"),
                    "tool_calls_made": tool_calls,
                    "must_not_contain_violations": violations,
                    "gate_summary": gate_summary,
                    "gate_checks": gate_summary["checks"],
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
        "endpoint": "/features/generate",
        "model_under_test": model_under_test,
        "judge_model": judge_model,
        "golden_version": golden["version"],
        "golden_file": str(golden_path.relative_to(ROOT)),
        "items": evaluated_items,
        "aggregates": {
            **compute_aggregates(evaluated_items),
            **compute_gate_aggregates(evaluated_items),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved run to {out_path}")
    print(f"Aggregates: {result['aggregates']}")
    return result


def parse_args() -> argparse.Namespace:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    default_out = ROOT / "eval" / "runs" / f"generate-{today}.json"
    parser = argparse.ArgumentParser(
        description="Run golden dataset evaluation for /features/generate",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "eval" / "golden_dataset_generate.json",
        help="Path to generate golden dataset JSON",
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
        help="Evaluate only item(s) with this id (repeatable), e.g. --id gen_gate_async_focus",
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
            run_evaluation_generate(
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
