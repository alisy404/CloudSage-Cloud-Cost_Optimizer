"""Unit tests for deterministic pricing and savings calculation (Stage 5)."""
from __future__ import annotations

from datetime import UTC, datetime

from app.analysis.savings import calculate_savings
from app.aws.pricing import (
    HOURS_PER_MONTH,
    HOURS_PER_YEAR,
    get_downsizing_targets,
    get_instance_pricing,
)
from app.models import (
    CandidateDecision,
    CandidateResult,
    EC2Instance,
)


def _make_instance(
    instance_type: str = "t3.large",
    state: str = "running",
    region: str = "us-east-1",
) -> EC2Instance:
    return EC2Instance(
        id="i-cost123",
        name="cost-server",
        type=instance_type,
        state=state,
        region=region,
        launch_time=datetime.now(UTC),
        tags={"env": "prod"},
    )


def _make_candidate_result(decision: CandidateDecision = CandidateDecision.candidate) -> CandidateResult:
    return CandidateResult(
        instance_id="i-cost123",
        decision=decision,
        reason="Test evaluation reason",
        facts=[],
        cpu_avg_threshold=10.0,
        cpu_p95_threshold=25.0,
        cpu_max_threshold=50.0,
        analyzed_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Pricing Catalog Unit Tests
# ---------------------------------------------------------------------------


def test_get_instance_pricing_known_type():
    """Known types return exact rates, vCPU, and memory."""
    pricing = get_instance_pricing("t3.large", region="us-east-1")
    assert pricing is not None
    assert pricing.instance_type == "t3.large"
    assert pricing.hourly_rate_usd == 0.0832
    assert pricing.monthly_rate_usd == round(0.0832 * HOURS_PER_MONTH, 4)
    assert pricing.vcpu == 2
    assert pricing.memory_gib == 8.0
    assert pricing.currency == "USD"


def test_get_instance_pricing_regional_rates():
    """Regions with different rates return their specific pricing."""
    p_useast = get_instance_pricing("t3.large", region="us-east-1")
    p_apsouth = get_instance_pricing("t3.large", region="ap-south-1")
    assert p_useast is not None and p_apsouth is not None
    assert p_apsouth.hourly_rate_usd > p_useast.hourly_rate_usd


def test_get_instance_pricing_unknown_type_returns_none():
    """Unknown types return None rather than raising an exception."""
    assert get_instance_pricing("nonexistent.type") is None


def test_downsizing_targets():
    """Hierarchy returns strictly smaller instance types in order."""
    targets = get_downsizing_targets("t3.large")
    assert targets == ["t3.medium", "t3.small", "t3.micro", "t3.nano"]

    # Smallest tier in family has no further downsizing targets
    assert get_downsizing_targets("t2.nano") == []


# ---------------------------------------------------------------------------
# Savings Service Unit Tests
# ---------------------------------------------------------------------------


def test_savings_happy_path_candidate():
    """A candidate instance calculates exact monthly and annual savings and recommends immediate next tier."""
    inst = _make_instance(instance_type="t3.large", region="us-east-1")
    cand = _make_candidate_result(CandidateDecision.candidate)

    savings = calculate_savings(inst, candidate_result=cand)
    assert savings.is_candidate is True
    assert savings.current_monthly_usd == round(0.0832 * HOURS_PER_MONTH, 2)
    assert savings.current_annual_usd == round(0.0832 * HOURS_PER_YEAR, 2)
    assert len(savings.alternatives) > 0

    # Recommended alternative should be t3.medium
    rec = savings.recommended_alternative
    assert rec is not None
    assert rec.target_type == "t3.medium"
    assert rec.target_monthly_usd < savings.current_monthly_usd
    assert rec.monthly_savings_usd == round(savings.current_monthly_usd - rec.target_monthly_usd, 2)
    assert rec.annual_savings_usd == round(rec.monthly_savings_usd * 12.0, 2)
    assert rec.savings_pct > 0.0


def test_savings_when_not_candidate():
    """When deterministic analysis concludes not_candidate, alternatives exist but no recommendation is made."""
    inst = _make_instance(instance_type="t3.large")
    cand = _make_candidate_result(CandidateDecision.not_candidate)

    savings = calculate_savings(inst, candidate_result=cand)
    assert savings.is_candidate is False
    assert savings.recommended_alternative is None
    assert len(savings.alternatives) > 0  # downsize options are still calculated for info
    assert any("does not currently meet rightsizing criteria" in n for n in savings.notes)


def test_savings_when_needs_more_data():
    """When metrics need more data, savings are calculated but no definitive recommendation is made."""
    inst = _make_instance(instance_type="t2.nano")
    cand = _make_candidate_result(CandidateDecision.needs_more_data)

    savings = calculate_savings(inst, candidate_result=cand)
    assert savings.is_candidate is False
    assert savings.recommended_alternative is None
    assert any("requires more historical data" in n for n in savings.notes)


def test_savings_unknown_type():
    """Unknown instance type gracefully returns None pricing and explanatory note."""
    inst = _make_instance(instance_type="custom.supercomputer")
    savings = calculate_savings(inst)

    assert savings.current_pricing is None
    assert savings.current_monthly_usd is None
    assert any("not yet in the local pricing catalog" in n for n in savings.notes)
