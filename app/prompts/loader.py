"""Загрузка промптов: read_text + jinja2.Template."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

PROMPTS_DIR = Path(__file__).resolve().parent


def read_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def render_template(template_name: str, **context: str) -> str:
    source = read_text(PROMPTS_DIR / template_name)
    return Template(source).render(**context).strip()


def load_tool_description(tool_name: str) -> str:
    return read_text(PROMPTS_DIR / "tools" / f"{tool_name}.md").strip()


def build_system_prompt(service_name: str, template_name: str = "system_v1.j2") -> str:
    return render_template(template_name, service_name=service_name)
