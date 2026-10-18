from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.ai.context import build_context
from app.ai.provider import FakeLLMProvider
from app.ai.schemas import RecommendationDecision
from app.ai.service import analyze_optimization
from app.analysis.candidate import evaluate
from app.analysis.savings import calculate_savings
from app.aws.cloudwatch import FakeCloudWatchAdapter
from app.aws.ec2 import FakeEC2Adapter
from app.models import CandidateDecision, EC2Instance


def _candidate(instance: EC2Instance, metrics) -> object:
    return evaluate(instance, metrics, 10.0, 25.0, 50.0)


def test_context_contains_only_bounded_backend_sections() -> None:
    instance = FakeEC2Adapter().list_instances()[0]
    metrics = FakeCloudWatchAdapter().get_instance_metrics(instance.id)
    candidate = _candidate(instance, metrics)
    savings = calculate_savings(instance, candidate)

    context = build_context(instance, metrics, candidate, savings)

    assert set(context.model_dump()) == {"resource", "metrics", "candidate", "savings", "generated_at", "instructions"}
    assert context.resource["id"] == instance.id
    assert "credentials" not in context.model_dump_json().lower()


def test_fake_provider_returns_valid_recommendation_for_candidate() -> None:
    instance = FakeEC2Adapter().list_instances()[0]
    metrics = FakeCloudWatchAdapter().get_instance_metrics(instance.id)
    candidate = _candidate(instance, metrics)
    savings = calculate_savings(instance, candidate)

    _, recommendation = analyze_optimization(instance, metrics, candidate, savings, FakeLLMProvider())

    assert recommendation.decision == RecommendationDecision.recommend
    assert recommendation.current_configuration["instance_type"] == instance.type
    assert recommendation.recommended_configuration["instance_type"] == savings.recommended_alternative.target_type
    assert 0.0 <= recommendation.confidence <= 1.0


def test_ai_is_not_called_for_non_candidate() -> None:
    instance = EC2Instance(
        id="i-stopped",
        name="stopped",
        type="t3.large",
        state="stopped",
        region="us-east-1",
        launch_time=datetime.now(UTC),
    )
    metrics = FakeCloudWatchAdapter().get_instance_metrics(instance.id)
    candidate = _candidate(instance, metrics)
    savings = calculate_savings(instance, candidate)

    assert candidate.decision == CandidateDecision.not_candidate
    with pytest.raises(ValueError, match="deterministic candidates"):
        analyze_optimization(instance, metrics, candidate, savings, FakeLLMProvider())


def test_backend_rejects_provider_proposing_unknown_type() -> None:
    instance = FakeEC2Adapter().list_instances()[0]
    metrics = FakeCloudWatchAdapter().get_instance_metrics(instance.id)
    candidate = _candidate(instance, metrics)
    savings = calculate_savings(instance, candidate)

    class BadProvider(FakeLLMProvider):
        def analyze_optimization(self, context):
            result = super().analyze_optimization(context)
            result.recommended_configuration["instance_type"] = "m7i.metal"
            return result

    with pytest.raises(ValueError, match="unsupported instance type"):
        analyze_optimization(instance, metrics, candidate, savings, BadProvider())

