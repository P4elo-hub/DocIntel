#!/usr/bin/env python3
"""Автопрогон сценариев DocIntel-агентов (Qdrant + LangGraph) с generic-проверками.

Запуск (из корня репо, с доступным Qdrant/.env):
  uv run python scripts/run_agent_scenarios.py
  uv run python scripts/run_agent_scenarios.py --ids ans_order_gateway_fresh
  docker compose exec -T app python scripts/run_agent_scenarios.py

Проверки НЕ содержат имён конкретных обменов — только то, что извлекается
из текста запроса / ответа / rag_context.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.agent_graph import run_docintel_pipeline, set_rag_service
from app.services.rag import RAGService
from app.tools.search_kb.handler import extract_api_ids

_JSONISH_RE = re.compile(r"\{[\s\S]{40,}\}")
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b")
_SOURCES_HDR_RE = re.compile(r"(?im)^#{1,3}\s*Источники\b")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class TurnResult:
    user: str
    intent: str | None = None
    use_history: bool = False
    agents: list[str] = field(default_factory=list)
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    rag_context: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        if self.error:
            return False
        return all(c.ok for c in self.checks)


@dataclass
class ScenarioResult:
    id: str
    category: str
    expect_intent: str | None
    turns: list[TurnResult] = field(default_factory=list)
    status: str = "fail"  # pass | fail | gap_in_kb

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def _load_scenarios(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            json_fallback = path.with_suffix(".json")
            if json_fallback.is_file():
                path = json_fallback
                raw = path.read_text(encoding="utf-8")
                data = json.loads(raw)
            else:
                raise SystemExit(
                    "PyYAML required for .yaml, or provide .json twin"
                ) from exc
        else:
            data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    items = list(data.get("scenarios") or [])
    if not items:
        raise ValueError(f"no scenarios in {path}")
    return items


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "", (text or "").lower())


def _compact(text: str) -> str:
    """Нормализация для substring-match: латиница + кириллица + цифры."""
    return re.sub(r"[^a-z0-9а-яё]+", "", (text or "").lower().replace("ё", "е"))


def _camel_parts(token: str) -> list[str]:
    """ScreenApi → [Screen, Api]; GET_LINKED_EVENTS → [GET, LINKED, EVENTS]."""
    if not token:
        return []
    if "_" in token or " " in token:
        return [p for p in re.split(r"[\s_]+", token) if p]
    parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+", token)
    return parts or [token]


def _json_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for m in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]{2,})"\s*:', text or ""):
        keys.add(m.group(1).lower())
    return keys


def _looks_like_json_example(answer: str) -> bool:
    body = re.sub(r"(?im)^#{1,3}\s*Источники\b[\s\S]*$", "", answer or "").strip()
    return bool(_JSONISH_RE.search(body))


_STOP_COMPACT = {
    "приведи",
    "пример",
    "пожалуйста",
    "ответ",
    "ответа",
    "операци",
    "операции",
    "операция",
    "которая",
    "приходит",
    "приходят",
    "нужен",
    "нужно",
    "сделай",
    "документац",
    "документации",
    "обмен",
    "сервис",
    "сервиса",
    "сегодня",
    "погода",
    "москве",
    "привет",
    "пришли",
    "интересует",
    "мобильного",
    "приложения",
    "какой",
    "нибудь",
}


def _anchor_tokens(user_message: str) -> list[str]:
    """Якоря запроса: API ids + значимые идентификаторы из текста пользователя."""
    apis = extract_api_ids(user_message)
    extras: list[str] = []
    for tok in _IDENT_RE.findall(user_message or ""):
        if len(tok) >= 4:
            extras.append(tok)
            extras.extend(_camel_parts(tok))
    for w in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", user_message or ""):
        extras.append(w)
    out: list[str] = []
    seen: set[str] = set()
    for a in [*apis, *extras]:
        key = _compact(a)
        if len(key) < 4 or key in seen or key in _STOP_COMPACT:
            continue
        seen.add(key)
        out.append(a)
    return out[:24]


def _anchors_in_text(anchors: list[str], text: str) -> list[str]:
    blob = _compact(text)
    hit: list[str] = []
    for a in anchors:
        variants = [_compact(a), *(_compact(p) for p in _camel_parts(a))]
        if any(v and len(v) >= 3 and v in blob for v in variants):
            hit.append(a)
    return hit


def _grounding_overlap(answer: str, rag_context: str) -> float:
    """Доля JSON-ключей / idents ответа, встречающихся в rag_context."""
    body = re.sub(r"(?im)^#{1,3}\s*Источники\b[\s\S]*$", "", answer or "")
    keys = _json_keys(body)
    if not keys:
        idents = {t.lower() for t in _IDENT_RE.findall(body) if len(t) >= 5}
        keys = idents
    if not keys:
        return 1.0  # нечего проверять
    ctx = _compact(rag_context)
    if not ctx:
        return 0.0
    hit = sum(1 for k in keys if _compact(k) in ctx)
    return hit / max(len(keys), 1)


def _format_history(prior: list[tuple[str, str]]) -> str:
    """user/assistant пары → кандидат истории для classify."""
    chunks: list[str] = []
    for role, text in prior[-6:]:
        label = "User" if role == "user" else "Assistant"
        limit = 1_200 if role == "user" else 8_000
        chunks.append(f"{label}: {(text or '')[:limit]}")
    return "\n\n".join(chunks)


def check_turn(
    *,
    user_message: str,
    result: dict[str, Any],
    expect_intent: str | None,
    category: str,
) -> tuple[list[CheckResult], str | None]:
    """Возвращает (checks, gap_reason). gap_reason → scenario status gap_in_kb."""
    checks: list[CheckResult] = []
    intent = result.get("intent")
    answer = (result.get("answer") or "").strip()
    sources = list(result.get("sources") or [])
    rag_ctx = (result.get("rag_context") or result.get("search_context") or "").strip()
    working = intent in {"answer", "write", "search"}

    # 1) ответ есть
    if working:
        checks.append(
            CheckResult(
                "non_empty_answer",
                bool(answer),
                f"chars={len(answer)}",
            )
        )
    else:
        checks.append(
            CheckResult(
                "control_answer",
                bool(answer),
                f"intent={intent} chars={len(answer)}",
            )
        )

    # 2) intent (soft — warning в detail, но fail если expect задан и сильно мимо)
    if expect_intent:
        ok_intent = intent == expect_intent
        checks.append(
            CheckResult(
                "expect_intent",
                ok_intent,
                f"got={intent} expected={expect_intent}",
            )
        )

    # 3) sources
    if working:
        has_hdr = bool(_SOURCES_HDR_RE.search(answer))
        checks.append(
            CheckResult(
                "sources_non_empty",
                bool(sources),
                f"n={len(sources)}",
            )
        )
        checks.append(
            CheckResult(
                "sources_section",
                has_hdr,
                "header present" if has_hdr else "missing ## Источники",
            )
        )
    else:
        checks.append(
            CheckResult(
                "sources_absent_for_control",
                not sources,
                f"n={len(sources)}",
            )
        )

    gap_reason: str | None = None

    if intent in {"answer", "write"}:
        if not rag_ctx:
            checks.append(
                CheckResult("rag_context_present", False, "empty rag_context")
            )
            gap_reason = "Qdrant miss / empty rag_context"
        else:
            checks.append(
                CheckResult("rag_context_present", True, f"chars={len(rag_ctx)}")
            )

        anchors = _anchor_tokens(user_message)
        if anchors:
            in_rag = _anchors_in_text(anchors, rag_ctx)
            in_sources = _anchors_in_text(
                anchors,
                " ".join(
                    str(s.get("file_name") or "") + " " + str(s.get("snippet") or "")
                    for s in sources
                ),
            )
            # Хотя бы один якорь запроса должен попасть в retrieve.
            anchor_ok = bool(in_rag or in_sources)
            checks.append(
                CheckResult(
                    "query_anchors_in_retrieve",
                    anchor_ok,
                    f"anchors={anchors[:8]} in_rag={in_rag[:6]} in_sources={in_sources[:6]}",
                )
            )
            if not anchor_ok and not rag_ctx:
                gap_reason = "Qdrant miss for query anchors"

        if _looks_like_json_example(answer):
            overlap = _grounding_overlap(answer, rag_ctx)
            # Порог: хотя бы 25% ключей/idents ответа встречаются в Qdrant-контексте.
            ok = overlap >= 0.25
            checks.append(
                CheckResult(
                    "json_grounded_in_rag",
                    ok,
                    f"overlap={overlap:.2f}",
                )
            )
        else:
            # Не JSON — мягкая проверка: ответ не должен быть совсем оторван
            # (хотя бы 1 якорь запроса или sources).
            if anchors:
                in_ans = _anchors_in_text(anchors, answer)
                checks.append(
                    CheckResult(
                        "answer_mentions_query_anchor",
                        bool(in_ans) or bool(sources),
                        f"in_answer={in_ans[:6]}",
                    )
                )

    if category == "answer_history" and intent == "answer" and rag_ctx:
        # Follow-up: ответ должен быть ближе к текущему rag_context, чем «пустой».
        overlap = _grounding_overlap(answer, rag_ctx)
        checks.append(
            CheckResult(
                "followup_grounded",
                overlap >= 0.25 or not _looks_like_json_example(answer),
                f"overlap={overlap:.2f}",
            )
        )

    return checks, gap_reason


async def run_scenario(
    scenario: dict,
    *,
    rag: RAGService,
) -> ScenarioResult:
    sid = scenario["id"]
    category = scenario.get("category") or ""
    expect_intent = scenario.get("expect_intent")
    turns_spec = list(scenario.get("turns") or [])
    out = ScenarioResult(
        id=sid,
        category=category,
        expect_intent=expect_intent,
    )
    prior: list[tuple[str, str]] = []
    gap: str | None = None

    for i, turn in enumerate(turns_spec):
        if turn.get("role") != "user":
            continue
        user = (turn.get("content") or "").strip()
        history = _format_history(prior) if prior else ""
        tr = TurnResult(user=user)
        try:
            result = await run_docintel_pipeline(
                user,
                chat_history=history,
                original_user_message=user,
                thread_id=f"scenario-{sid}-{i}",
                rag_service=rag,
            )
        except Exception as exc:  # noqa: BLE001
            tr.error = str(exc)
            out.turns.append(tr)
            out.status = "fail"
            return out

        tr.intent = result.get("intent")
        tr.use_history = bool(result.get("use_history"))
        tr.agents = list(result.get("agents_called") or [])
        tr.answer = result.get("answer") or ""
        tr.sources = list(result.get("sources") or [])
        tr.rag_context = result.get("rag_context") or ""
        # Проверяем только последний user-turn сценария (и единственный для single-turn).
        is_last = i == len(turns_spec) - 1 or all(
            t.get("role") != "user" for t in turns_spec[i + 1 :]
        )
        if is_last:
            checks, gap_reason = check_turn(
                user_message=user,
                result=result,
                expect_intent=expect_intent,
                category=category,
            )
            tr.checks = checks
            if gap_reason:
                gap = gap_reason
        else:
            tr.checks = [
                CheckResult("intermediate_turn", True, f"intent={tr.intent}")
            ]

        prior.append(("user", user))
        prior.append(("assistant", tr.answer))
        out.turns.append(tr)

    if gap and all(
        c.name == "query_anchors_in_retrieve" and not c.ok
        for t in out.turns
        for c in t.checks
        if not c.ok
    ):
        out.status = "gap_in_kb"
    elif all(t.passed for t in out.turns):
        out.status = "pass"
    else:
        out.status = "fail"
    return out


async def amain(args: argparse.Namespace) -> int:
    scenarios_path = Path(args.scenarios)
    if not scenarios_path.is_absolute():
        scenarios_path = ROOT / scenarios_path
    scenarios = _load_scenarios(scenarios_path)
    if args.ids:
        want = set(args.ids)
        scenarios = [s for s in scenarios if s.get("id") in want]
        missing = want - {s.get("id") for s in scenarios}
        if missing:
            raise SystemExit(f"unknown scenario ids: {sorted(missing)}")

    settings = get_settings()
    print(f"RAG collection={settings.rag_collection} qdrant={settings.qdrant_url}")
    rag = RAGService(settings)
    await asyncio.to_thread(rag.build)
    set_rag_service(rag)
    print("RAG ready")

    results: list[ScenarioResult] = []
    for sc in scenarios:
        print(f"\n=== {sc['id']} ({sc.get('category')}) ===")
        res = await run_scenario(sc, rag=rag)
        results.append(res)
        print(f"  status={res.status}")
        for tr in res.turns:
            if tr.error:
                print(f"  ERROR: {tr.error}")
            print(
                f"  intent={tr.intent} agents={tr.agents} "
                f"sources={len(tr.sources)} answer_chars={len(tr.answer)}"
            )
            for c in tr.checks:
                mark = "OK" if c.ok else "FAIL"
                print(f"    [{mark}] {c.name}: {c.detail}")

    out_dir = ROOT / "eval" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = {
        "version": 1,
        "generated_at": ts,
        "scenarios_path": str(scenarios_path),
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r.status == "pass"),
            "fail": sum(1 for r in results if r.status == "fail"),
            "gap_in_kb": sum(1 for r in results if r.status == "gap_in_kb"),
        },
        "results": [
            {
                "id": r.id,
                "category": r.category,
                "expect_intent": r.expect_intent,
                "status": r.status,
                "turns": [
                    {
                        "user": t.user[:500],
                        "intent": t.intent,
                        "use_history": t.use_history,
                        "agents": t.agents,
                        "sources": [
                            {
                                "id": s.get("id"),
                                "file_name": s.get("file_name"),
                                "score": s.get("score"),
                            }
                            for s in t.sources
                        ],
                        "answer_preview": (t.answer or "")[:1200],
                        "rag_context_chars": len(t.rag_context or ""),
                        "checks": [asdict(c) for c in t.checks],
                        "error": t.error,
                    }
                    for t in r.turns
                ],
            }
            for r in results
        ],
    }
    json_path = out_dir / f"agent_scenarios_{ts}.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    md_lines = [
        f"# Agent scenarios {ts}",
        "",
        f"- pass: {report['summary']['pass']}",
        f"- fail: {report['summary']['fail']}",
        f"- gap_in_kb: {report['summary']['gap_in_kb']}",
        "",
    ]
    for r in results:
        md_lines.append(f"## {r.id} — **{r.status}**")
        for t in r.turns:
            fails = [c for c in t.checks if not c.ok]
            if fails:
                for c in fails:
                    md_lines.append(f"- FAIL `{c.name}`: {c.detail}")
            elif t.error:
                md_lines.append(f"- ERROR: {t.error}")
            else:
                md_lines.append(
                    f"- ok intent={t.intent} sources={len(t.sources)} "
                    f"chars={len(t.answer)}"
                )
        md_lines.append("")
    md_path = out_dir / f"agent_scenarios_{ts}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")

    # gap_in_kb не валит exit code как fail продукта — но для CI считаем fail,
    # пока suite не зелёный. Plan: pass или честный gap. Exit 0 только если
    # нет fail; gap печатаем отдельно.
    n_fail = report["summary"]["fail"]
    return 1 if n_fail else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--scenarios",
        default="eval/agent_scenarios.json",
        help="Path to scenarios YAML/JSON",
    )
    p.add_argument(
        "--ids",
        nargs="*",
        default=None,
        help="Subset of scenario ids",
    )
    args = p.parse_args()
    raise SystemExit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
