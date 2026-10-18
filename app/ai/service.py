"""Orchestration for deterministic evidence plus one LLM recommendation."""
from __future__ import annotations

from app.ai.context import OptimizationContext, build_context
from app.ai.provider import FakeLLMProvider, LLMProvider
from app.ai.schemas import RecommendationDraft
from app.models import (
    CandidateDecision,
    CandidateResult,
    EC2Instance,
    InstanceMetrics,
    SavingsResult,
)


def analyze_optimization(
    instance: EC2Instance,
    metrics: InstanceMetrics,
    candidate: CandidateResult,
    savings: SavingsResult,
    provider: LLMProvider | None = None,
) -> tuple[OptimizationContext, RecommendationDraft]:
    """Build bounded context, call one provider, and validate its output."""

    context = build_context(instance, metrics, candidate, savings)
    if candidate.decision != CandidateDecision.candidate:
        raise ValueError("AI analysis is allowed only for deterministic candidates")

    draft = (provider or FakeLLMProvider()).analyze_optimization(context)
    _validate_against_backend(draft, instance, savings)
    return context, draft


def _validate_against_backend(
    draft: RecommendationDraft,
    instance: EC2Instance,
    savings: SavingsResult,
) -> None:
    """Reject model output that conflicts with backend facts."""

    current = draft.current_configuration.get("instance_type")
    if current != instance.type:
        raise ValueError("AI recommendation current instance type does not match AWS data")

    proposed = draft.recommended_configuration.get("instance_type")
    allowed = {alternative.target_type for alternative in savings.alternatives}
    if draft.decision.value == "recommend" and proposed not in allowed:
        raise ValueError("AI recommendation proposes an unsupported instance type")

    for item in draft.evidence:
        if not item.source or not item.statement:
            raise ValueError("AI evidence items must contain a source and statement")

