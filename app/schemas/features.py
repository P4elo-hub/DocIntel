"""Pydantic-схемы для DocIntel API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeatureGenerateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "feature_brief": "Перевести уведомления о переводах на Kafka...",
                    "feature_name": "Асинхронные уведомления по переводам",
                    "protocol": "Async",
                }
            ]
        }
    )

    feature_brief: str = Field(..., min_length=1, max_length=100_000)
    feature_name: str | None = Field(default=None, max_length=500)
    protocol: Literal["REST", "Kafka", "Async", "gRPC", "GraphQL", "SOAP"] | None = None


class FeatureGenerateResponse(BaseModel):
    content: str
    model: str
    tool_calls_made: int = 0
    feature_name: str | None = None
    protocol: str | None = None
