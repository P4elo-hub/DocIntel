"""Kit-tools: соответствие tool → standard kit → разделы shablon."""

from __future__ import annotations

from dataclasses import dataclass

from app.tools.write_feature_doc.shablon_loader import infer_sections

ALL_SECTION_TOOL_NAMES = frozenset({
    "write_requirements",
    "write_use_case_as_is",
    "write_use_case_to_be",
    "write_integration",
    "write_data_model",
    "write_nfr",
    "write_observability",
})


@dataclass(frozen=True)
class KitToolStep:
    tool_name: str
    kit_id: str
    section_ids: tuple[str, ...]
    label: str


KIT_TOOL_STEPS: tuple[KitToolStep, ...] = (
    KitToolStep(
        "write_requirements",
        "requirements-standard-kit",
        ("1.1", "2"),
        "Бизнес-требования и ограничения",
    ),
    KitToolStep(
        "write_use_case_as_is",
        "use-case-standard-kit",
        ("1.2-usecase",),
        "Use Case AS IS",
    ),
    KitToolStep(
        "write_use_case_to_be",
        "use-case-standard-kit",
        ("1.3-usecase",),
        "Use Case TO BE",
    ),
    KitToolStep(
        "write_integration",
        "integration-standard-kit",
        ("4.1.1", "4.1.2"),
        "Интеграции",
    ),
    KitToolStep(
        "write_data_model",
        "data-standard-kit",
        ("4.2.3",),
        "Модель данных",
    ),
    KitToolStep(
        "write_nfr",
        "nfr-standard-kit",
        ("5.1", "5.2-performance", "5.2-reliability", "5.4", "5.5"),
        "Нефункциональные требования",
    ),
    KitToolStep(
        "write_observability",
        "observability-standard-kit",
        ("5.3.1", "5.3.2"),
        "Логирование и мониторинг",
    ),
)


def build_execution_plan(feature_brief: str) -> list[KitToolStep]:
    """План генерации: только kit-tools, релевантные brief."""
    inferred = set(infer_sections(feature_brief, "full"))
    plan: list[KitToolStep] = []
    for step in KIT_TOOL_STEPS:
        active = [sid for sid in step.section_ids if sid in inferred]
        if not active:
            continue
        plan.append(
            KitToolStep(
                tool_name=step.tool_name,
                kit_id=step.kit_id,
                section_ids=tuple(active),
                label=step.label,
            )
        )
    return plan


def merge_section_documents(title: str, sections: list[str]) -> str:
    """Склеивает секции в финальный Markdown-документ."""
    parts = [part.strip() for part in sections if part and part.strip()]
    if not parts:
        return f"# {title}\n"

    if parts[0].startswith("# "):
        if len(parts) == 1:
            return parts[0] + "\n"
        return parts[0] + "\n\n" + "\n\n".join(parts[1:]) + "\n"

    return f"# {title}\n\n" + "\n\n".join(parts) + "\n"
