#!/usr/bin/env python3
"""Проверка агрегатов последнего eval-прогона против порогов в thresholds.yaml."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "eval" / "runs"
THRESHOLDS_PATH = ROOT / "eval" / "thresholds.yaml"


def load_thresholds(path: Path) -> dict[str, float]:
    if yaml is None:
        thresholds: dict[str, float] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition(":")
            thresholds[key.strip()] = float(value.strip())
        return thresholds
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in data.items()}


def find_latest_run(runs_dir: Path) -> Path:
    candidates = sorted(
        (p for p in runs_dir.glob("*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No run files in {runs_dir}")
    return candidates[0]


def check_thresholds(run_path: Path, thresholds: dict[str, float]) -> list[str]:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    aggregates = run.get("aggregates", {})
    failures: list[str] = []

    for key, minimum in thresholds.items():
        actual = aggregates.get(key)
        if actual is None:
            failures.append(f"{key}: missing in run aggregates")
            continue
        if actual < minimum:
            failures.append(f"{key}: {actual} < {minimum}")

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check eval run against thresholds")
    parser.add_argument(
        "--run",
        type=Path,
        default=None,
        help="Path to run JSON (default: latest in eval/runs/)",
    )
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=THRESHOLDS_PATH,
        help="Path to thresholds YAML",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_path = args.run or find_latest_run(RUNS_DIR)
    thresholds = load_thresholds(args.thresholds)
    failures = check_thresholds(run_path, thresholds)

    print(f"Checking {run_path.name} against {args.thresholds.name}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        sys.exit(1)

    print("OK: all thresholds met")
    sys.exit(0)


if __name__ == "__main__":
    main()
