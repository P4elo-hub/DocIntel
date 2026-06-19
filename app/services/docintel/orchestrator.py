"""Пошаговая async-генерация документа: kit-tool → секция → склейка."""

from __future__ import annotations

import re

from app.prompts.loader import render_template
from app.services.docintel.client import ChatResult, ToolCallClient
from app.tools.feature_sections import (
    build_execution_plan,
    merge_section_documents,
)


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _normalize_section_text(text: str) -> str:
    text = text.strip()
    for prefix in (
        "Вот полная документация",
        "Вот документация",
        "Ниже документация",
        "# INTERNAL:",
        "# Пакет методологии",
    ):
        if text.lower().startswith(prefix.lower()):
            lines = text.splitlines()
            for index, line in enumerate(lines):
                if line.startswith("#") and "пакет" not in line.lower() and "internal" not in line.lower():
                    text = "\n".join(lines[index:]).strip()
                    break
    return _strip_code_fence(text)


def _update_context_summary(summary: str, new_section: str, *, max_chars: int = 2500) -> str:
    combined = f"{summary}\n\n---\n\n{new_section}".strip()
    if len(combined) <= max_chars:
        return combined
    return combined[-max_chars:]


def _extract_title(feature_name: str | None, first_section: str, brief: str) -> str:
    if feature_name and feature_name.strip():
        return feature_name.strip()
    match = re.search(r"^#\s+(.+)$", first_section, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    line = brief.strip().splitlines()[0] if brief.strip() else "Новая фича"
    return line[:120]


class SectionOrchestrator:
    """Async-оркестратор: каждый kit-tool → отдельный LLM-вызов → склейка."""

    def __init__(self, client: ToolCallClient) -> None:
        self._client = client
        self._system_prompt = render_template(
            "section_writer_v1.j2",
            service_name=client.settings.docintel.service_name,
        )

    async def generate(
        self,
        feature_brief: str,
        *,
        feature_name: str | None = None,
        protocol: str | None = None,
    ) -> ChatResult:
        plan = build_execution_plan(feature_brief)
        if not plan:
            return ChatResult(
                text="Не удалось построить план разделов для brief.",
                tool_calls_made=0,
                model=self._client._model,
            )

        context_summary = ""
        section_outputs: list[str] = []
        tool_calls_made = 0
        active_model = self._client._model

        for index, step in enumerate(plan):
            print(
                f"  → kit-tool {index + 1}/{len(plan)}: {step.tool_name} "
                f"({', '.join(step.section_ids)})",
                flush=True,
            )
            package = self._client._handlers.write_section(
                tool_name=step.tool_name,
                feature_brief=feature_brief,
                section_ids=list(step.section_ids),
                protocol=protocol,
                feature_name=feature_name,
                context_summary=context_summary,
                include_document_title=index == 0,
            )
            tool_calls_made += 1

            section_text, used_model = await self._generate_section_markdown(package, step.label)
            active_model = used_model
            section_text = _normalize_section_text(section_text)
            section_outputs.append(section_text)
            context_summary = _update_context_summary(context_summary, section_text)

        title = _extract_title(
            feature_name,
            section_outputs[0] if section_outputs else "",
            feature_brief,
        )
        final_document = merge_section_documents(title, section_outputs)

        print("  → склейка секций в финальный документ", flush=True)
        return ChatResult(
            text=final_document,
            tool_calls_made=tool_calls_made,
            model=active_model,
        )

    async def _generate_section_markdown(self, kit_package: str, step_label: str) -> tuple[str, str]:
        response = await self._client._create_completion(
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Заполни раздел: **{step_label}**.\n\n"
                        f"{kit_package}"
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or ""
        model = response.model or self._client._model
        return content.strip(), model
