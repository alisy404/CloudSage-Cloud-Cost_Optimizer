"""Deterministic savings calculation service.

Rules:
- The LLM is never allowed to calculate authoritative financial figures.
- All numbers are strictly deterministic, reproducible, and verifiable.
- Savings are calculated using standard 730 hours/month and 8760 hours/year.
- Missing pricing or stopped instances are handled explicitly without silent zeroes.
"""
from __future__ import annotations

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
    RightsizingAlternative,
    SavingsResult,
)


def calculate_savings(
    instance: EC2Instance,
    candidate_result: CandidateResult | None = None,
) -> SavingsResult:
    """Calculate deterministic cost and prospective savings for an EC2 instance.

    Parameters
    ----------
    instance:
        The target EC2 instance.
    candidate_result:
        Optional CandidateResult from Stage 4 deterministic analysis.

    Returns
    -------
    SavingsResult with current spend and evaluated rightsizing alternatives.
    """
    pricing = get_instance_pricing(instance.type, region=instance.region)
    is_candidate = (
        candidate_result is not None
        and candidate_result.decision == CandidateDecision.candidate
    )

    notes: list[str] = []

    # If instance type is unknown in catalog
    if pricing is None:
        notes.append(f"Instance type '{instance.type}' is not yet in the local pricing catalog.")
        return SavingsResult(
            instance_id=instance.id,
            instance_type=instance.type,
            region=instance.region,
            current_pricing=None,
            is_candidate=is_candidate,
            status_state=instance.state,
            notes=notes,
        )

    # Compute current baseline cost
    current_hourly = pricing.hourly_rate_usd
    current_monthly = round(current_hourly * HOURS_PER_MONTH, 2)
    current_annual = round(current_hourly * HOURS_PER_YEAR, 2)

    if instance.state != "running":
        notes.append(f"Instance is currently '{instance.state}'. Projected spend assumes 730 running hours/month.")

    # Find alternatives
    alternatives: list[RightsizingAlternative] = []
    downsizing_candidates = get_downsizing_targets(instance.type)

    for target_type in downsizing_candidates:
        target_pricing = get_instance_pricing(target_type, region=instance.region)
        if target_pricing is None:
            continue

        target_hourly = target_pricing.hourly_rate_usd
        target_monthly = round(target_hourly * HOURS_PER_MONTH, 2)

        monthly_diff = round(current_monthly - target_monthly, 2)
        annual_diff = round(monthly_diff * 12.0, 2)
        pct_savings = round((monthly_diff / current_monthly) * 100.0, 1) if current_monthly > 0 else 0.0

        if monthly_diff > 0:
            alternatives.append(
                RightsizingAlternative(
                    target_type=target_type,
                    target_vcpu=target_pricing.vcpu,
                    target_memory_gib=target_pricing.memory_gib,
                    target_hourly_usd=target_hourly,
                    target_monthly_usd=target_monthly,
                    monthly_savings_usd=monthly_diff,
                    annual_savings_usd=annual_diff,
                    savings_pct=pct_savings,
                )
            )

    # Select the recommended alternative
    # Default strategy: the immediate next downsized tier (first in alternative chain)
    recommended: RightsizingAlternative | None = None
    if alternatives and is_candidate:
        recommended = alternatives[0]
        notes.append(
            f"Recommended target is {recommended.target_type} saving ~${recommended.monthly_savings_usd:.2f}/mo ({recommended.savings_pct:.0f}%)."
        )
    elif not is_candidate:
        if candidate_result and candidate_result.decision == CandidateDecision.needs_more_data:
            notes.append("Instance requires more historical data before an authoritative rightsizing tier is recommended.")
        elif candidate_result and candidate_result.decision == CandidateDecision.not_candidate:
            notes.append("Instance does not currently meet rightsizing criteria.")

    return SavingsResult(
        instance_id=instance.id,
        instance_type=instance.type,
        region=instance.region,
        current_pricing=pricing,
        is_candidate=is_candidate,
        status_state=instance.state,
        current_hourly_usd=current_hourly,
        current_monthly_usd=current_monthly,
        current_annual_usd=current_annual,
        alternatives=alternatives,
        recommended_alternative=recommended,
        notes=notes,
    )
