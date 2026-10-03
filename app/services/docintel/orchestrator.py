"""Write-агент: независимые kit-subagents → склейка.

Контракт пайплайна (общий для любого обмена/фичи):

1. Снаружи уже отработал независимый ``search_agent`` → артефакт
   ``search_context`` (сырой результат search_kb).
2. Для каждого kit-tool (цель, AS IS, TO BE, integration, …) —
   **новый** LLM-вызов без истории соседей.
3. Вход каждого subagent строго:
   - бриф пользователя;
   - ``search_context`` (один и тот же документ поиска);
   - пакет methodology только этого kit-tool.
4. После всех вызовов секции склеиваются в один Markdown.
"""

from __future__ import annotations

import re

from app.prompts.loader import render_template
from app.services.docintel.client import ChatResult, ToolCallClient
from app.tools.feature_sections import (
    build_execution_plan,
    merge_section_documents,
)

# Один и тот же KB-артефакт целиком уходит в каждый subagent (лимит на размер).
_KB_CONTEXT_LIMIT = 18_000


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


def _extract_title(feature_name: str | None, first_section: str, brief: str) -> str:
    if feature_name and feature_name.strip():
        return feature_name.strip()
    match = re.search(r"^#\s+(.+)$", first_section, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    line = brief.strip().splitlines()[0] if brief.strip() else "Новая фича"
    return line[:120]


class SectionOrchestrator:
    """Независимые kit-subagents: (search_context + kit) → секция → склейка."""

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
        search_context: str = "",
    ) -> ChatResult:
        plan = build_execution_plan(feature_brief)
        if not plan:
            return ChatResult(
                text="Не удалось построить план разделов для brief.",
                tool_calls_made=0,
                model=self._client._model,
            )

        kb_context = search_context.strip()[:_KB_CONTEXT_LIMIT]
        section_outputs: list[str] = []
        tool_calls_made = 0
        active_model = self._client._model

        for index, step in enumerate(plan):
            print(
                f"  → kit-subagent {index + 1}/{len(plan)}: {step.tool_name} "
                f"({', '.join(step.section_ids)}) "
                f"[in: brief + search_context + kit only]",
                flush=True,
            )
            # Ровно то, что нужно: контекст поиска + пакет этого kit. Без чужих разделов.
            package = self._client._handlers.write_section(
                tool_name=step.tool_name,
                feature_brief=feature_brief,
                section_ids=list(step.section_ids),
                protocol=protocol,
                feature_name=feature_name,
                context_summary="",
                search_context=kb_context,
                include_document_title=index == 0,
            )
            tool_calls_made += 1

            section_text, used_model = await self._generate_section_markdown(
                package,
                step.label,
                step.tool_name,
            )
            active_model = used_model
            section_outputs.append(_normalize_section_text(section_text))

        title = _extract_title(
            feature_name,
            section_outputs[0] if section_outputs else "",
            feature_brief,
        )
        final_document = merge_section_documents(title, section_outputs)

        print("  → склейка секций независимых kit-subagents", flush=True)
        return ChatResult(
            text=final_document,
            tool_calls_made=tool_calls_made,
            model=active_model,
        )

    async def _generate_section_markdown(
        self,
        kit_package: str,
        step_label: str,
        tool_name: str,
    ) -> tuple[str, str]:
        response = await self._client._create_completion(
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Ты независимый kit-subagent `{tool_name}`.\n"
                        f"Заполни только раздел: **{step_label}**.\n"
                        "Вход: бриф + документ поиска (search_context) + kit этого шага. "
                        "Истории других разделов нет.\n\n"
                        f"{kit_package}"
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or ""
        model = response.model or self._client._model
        return content.strip(), model
