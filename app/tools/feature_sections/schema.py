"""JSON Schema kit-tools для пошаговой генерации документации."""

from __future__ import annotations

from app.prompts.loader import load_tool_description
from app.tools.feature_sections.kits import KIT_TOOL_STEPS

_COMMON_PARAMS = {
    "feature_brief": {
        "type": "string",
        "description": "Краткое описание фичи от пользователя.",
    },
    "feature_name": {
        "type": "string",
        "description": "Название фичи для заголовка документа.",
    },
    "protocol": {
        "type": "string",
        "description": "Протокол интеграции: REST, gRPC, GraphQL, SOAP, Async.",
    },
}

_SHORT_DESCRIPTIONS: dict[str, str] = {
    "write_requirements": "Раздел 1.1 и 2 — requirements-standard-kit.",
    "write_use_case_as_is": "Раздел 1.2 AS IS — use-case-standard-kit.",
    "write_use_case_to_be": "Раздел 1.3 TO BE — use-case-standard-kit.",
    "write_integration": "Раздел 4.x интеграция — integration-standard-kit.",
    "write_data_model": "Раздел 4.2.3 модель данных — data-standard-kit.",
    "write_nfr": "Раздел 5 NFR (кроме observability) — nfr-standard-kit.",
    "write_observability": "Разделы 5.3.1 и 5.3.2 — observability-standard-kit.",
}


def _build_tool(name: str, kit_id: str, label: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": _SHORT_DESCRIPTIONS[name],
            "parameters": {
                "type": "object",
                "properties": dict(_COMMON_PARAMS),
                "required": ["feature_brief"],
                "additionalProperties": False,
            },
        },
    }


KIT_TOOLS: dict[str, dict] = {
    step.tool_name: _build_tool(step.tool_name, step.kit_id, step.label)
    for step in KIT_TOOL_STEPS
}


def get_openai_tool(tool_name: str, service_name: str = "DocIntel") -> dict:
    tool = dict(KIT_TOOLS[tool_name])
    tool["function"] = dict(tool["function"])
    try:
        description = load_tool_description(tool_name).replace("{{ service_name }}", service_name)
    except OSError:
        description = _SHORT_DESCRIPTIONS[tool_name]
    tool["function"]["description"] = description
    return tool


def get_all_section_tools(service_name: str = "DocIntel") -> list[dict]:
    return [get_openai_tool(step.tool_name, service_name) for step in KIT_TOOL_STEPS]
