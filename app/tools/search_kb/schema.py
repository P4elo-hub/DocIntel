"""JSON Schema для tool search_kb."""

from __future__ import annotations

from app.prompts.loader import load_tool_description

NAME = "search_kb"

SHORT_DESCRIPTION = "Поиск по существующей проектной документации в app/data/docs/."

TOOL = {
    "type": "function",
    "function": {
        "name": NAME,
        "description": SHORT_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Короткий поисковый запрос по существующей документации.",
                },
            },
            "required": ["query"],
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
