"""Общие пути для тестов."""

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
CASSETS_DIR = TESTS_DIR / "cassets"
