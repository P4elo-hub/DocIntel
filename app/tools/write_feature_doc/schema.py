"""JSON Schema для tool write_feature_doc."""

from __future__ import annotations

from app.prompts.loader import load_tool_description

NAME = "write_feature_doc"

SHORT_DESCRIPTION = (
    "Написание документации новой фичи по shablon.md и standard kits "
    "(requirements, use case, integration, data model, NFR, observability)."
)

TOOL = {
    "type": "function",
    "function": {
        "name": NAME,
        "description": SHORT_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "feature_brief": {
                    "type": "string",
                    "description": (
                        "Краткое описание фичи от пользователя: что сделать, "
                        "какие системы, входы/выходы, ограничения."
                    ),
                },
                "section_id": {
                    "type": "string",
                    "description": (
                        "Разделы shablon: full (автовыбор), или через запятую: "
                        "1.1, 1.3-usecase, 4.1.1, 4.2.3, 5.3.1 и т.д."
                    ),
                },
                "protocol": {
                    "type": "string",
                    "description": "Протокол интеграции: REST, gRPC, GraphQL, SOAP, Async.",
                },
                "feature_name": {
                    "type": "string",
                    "description": "Slug названия фичи, например get-product-info.",
                },
            },
            "required": ["feature_brief"],
            "additionalProperties": False,
        },
    },
}


def get_openai_tool(service_name: str = "DocIntel") -> dict:
    tool = dict(TOOL)
    tool["function"] = dict(tool["function"])
    description = load_tool_description(NAME).replace("{{ service_name }}", service_name)
    tool["function"]["description"] = description
    return tool
