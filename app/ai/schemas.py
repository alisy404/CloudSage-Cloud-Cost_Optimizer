"""Validated, provider-neutral recommendation contracts."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RecommendationDecision(str, Enum):
    recommend = "recommend"
    reject = "reject"
    needs_more_data = "needs_more_data"


class RecommendationRisk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EvidenceItem(BaseModel):
    """A claim the model attributes to a bounded backend fact."""

    source: str
    statement: str


class RecommendationDraft(BaseModel):
    """The only AI output allowed into the application workflow."""

    decision: RecommendationDecision
    optimization_type: str = "rightsizing"
    current_configuration: dict[str, str] = Field(default_factory=dict)
    recommended_configuration: dict[str, str] = Field(default_factory=dict)
    reasoning: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    required_validation: list[str] = Field(default_factory=list)
    risk: RecommendationRisk
    confidence: float = Field(ge=0.0, le=1.0)

