from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProcessingCapability(StrEnum):
    TEXT = "text"
    VISION = "vision"


class ProcessingStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class VisualCoverage(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"


class ProcessingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)

    text: str = ""
    image_refs: list[str] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProcessingStatus
    provider_id: str
    capability: ProcessingCapability

    output: dict[str, Any] = Field(default_factory=dict)

    visual_coverage: VisualCoverage = VisualCoverage.NOT_APPLICABLE

    warnings: list[str] = Field(default_factory=list)
