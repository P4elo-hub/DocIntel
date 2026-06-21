"""Integration-тесты: eval/check_thresholds.py с cassette-фикстурами."""

from __future__ import annotations

import subprocess
import sys

from tests.helpers import CASSETS_DIR, PROJECT_ROOT


def test_check_thresholds_passes_on_good_run() -> None:
    run_file = CASSETS_DIR / "runs" / "good_run.json"
    thresholds = PROJECT_ROOT / "eval" / "thresholds.yaml"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "eval" / "check_thresholds.py"),
            "--run",
            str(run_file),
            "--thresholds",
            str(thresholds),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_check_thresholds_fails_on_low_correctness() -> None:
    run_file = CASSETS_DIR / "runs" / "bad_run.json"
    thresholds = PROJECT_ROOT / "eval" / "thresholds.yaml"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "eval" / "check_thresholds.py"),
            "--run",
            str(run_file),
            "--thresholds",
            str(thresholds),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "FAIL" in result.stdout
