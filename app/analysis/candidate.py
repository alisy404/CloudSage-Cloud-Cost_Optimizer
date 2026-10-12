"""Deterministic rightsizing candidate evaluator.

This module contains pure, testable Python logic with no AWS calls,
no LLM calls, and no side effects. It takes an EC2Instance and its
InstanceMetrics and returns a CandidateResult.

Decision flow (fail-fast, ordered)
------------------------------------
1. Instance not running          → not_candidate
2. CPU data unavailable          → needs_more_data
3. CPU insufficient history      → needs_more_data
4. Status check failed > 0       → not_candidate  (health gate)
5. CPU average ≥ avg_threshold   → not_candidate
6. CPU P95 ≥ p95_threshold       → not_candidate  (spike safety)
7. CPU max ≥ max_threshold       → not_candidate  (burst safety)
8. All checks pass               → candidate

Rules from task.md §8
-----------------------
- Do not select a final instance type using only the LLM.
- Return candidate / not_candidate / needs_more_data.
- Include the facts and thresholds that produced the decision.
- Do not silently treat missing metrics as zero.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.models import (
    AnalysisFact,
    CandidateDecision,
    CandidateResult,
    EC2Instance,
    InstanceMetrics,
    MetricStatus,
)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f} %"


def _fmt_count(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def evaluate(
    instance: EC2Instance,
    metrics: InstanceMetrics,
    cpu_avg_threshold: float = 10.0,
    cpu_p95_threshold: float = 25.0,
    cpu_max_threshold: float = 50.0,
) -> CandidateResult:
    """Run the deterministic candidate evaluation.

    Parameters
    ----------
    instance:
        The EC2 instance to evaluate.
    metrics:
        CloudWatch metric summaries for the same instance.
    cpu_avg_threshold:
        CPU average must be **below** this to be a candidate.
    cpu_p95_threshold:
        CPU P95 must be **below** this (spike safety gate).
    cpu_max_threshold:
        CPU maximum must be **below** this (burst safety gate).

    Returns
    -------
    CandidateResult with the decision, human-readable reason, and all facts.
    """
    facts: list[AnalysisFact] = []
    cpu = metrics.cpu
    scf = metrics.status_check_failed

    # ── 1. Instance state ────────────────────────────────────────────────────
    state_ok = instance.state == "running"
    facts.append(
        AnalysisFact(
            label="Instance state",
            observed=instance.state,
            threshold="running",
            passed=state_ok,
        )
    )
    if not state_ok:
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.not_candidate,
            reason=f"Instance is {instance.state!r}, not running.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )

    # ── 2. CPU data availability ──────────────────────────────────────────────
    cpu_available = cpu.status != MetricStatus.unavailable
    facts.append(
        AnalysisFact(
            label="CPU data available",
            observed=cpu.status.value,
            threshold="not unavailable",
            passed=cpu_available,
        )
    )
    if not cpu_available:
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.needs_more_data,
            reason="No CPU utilisation data returned by CloudWatch.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )

    # ── 3. Sufficient CPU history ─────────────────────────────────────────────
    cpu_sufficient = cpu.status == MetricStatus.ok
    facts.append(
        AnalysisFact(
            label="CPU history sufficient for P95",
            observed=f"{cpu.sample_count} samples",
            threshold="≥ 24 samples",
            passed=cpu_sufficient,
        )
    )
    if not cpu_sufficient:
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.needs_more_data,
            reason=f"Only {cpu.sample_count} CPU sample(s) — need at least 24 (1 day) for P95.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )

    # ── 4. Status check health gate ───────────────────────────────────────────
    # If CloudWatch returned no status-check data, assume healthy (no failures = no datapoints).
    # Only block if there is explicit evidence of failures (average > 0).
    if scf.status == MetricStatus.ok and scf.average is not None and scf.average > 0:
        facts.append(
            AnalysisFact(
                label="Status check failures",
                observed=_fmt_count(scf.average),
                threshold="0",
                passed=False,
            )
        )
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.not_candidate,
            reason=f"Recent status check failures detected (avg {scf.average:.2f}). Instance health must be stable.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )
    facts.append(
        AnalysisFact(
            label="Status check failures",
            observed="none detected" if scf.status == MetricStatus.unavailable else _fmt_count(scf.average),
            threshold="0",
            passed=True,
        )
    )

    # ── 5. CPU average threshold ──────────────────────────────────────────────
    cpu_avg_ok = cpu.average is not None and cpu.average < cpu_avg_threshold
    facts.append(
        AnalysisFact(
            label="CPU average",
            observed=_fmt_pct(cpu.average),
            threshold=f"< {cpu_avg_threshold:.0f} %",
            passed=cpu_avg_ok,
        )
    )
    if not cpu_avg_ok:
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.not_candidate,
            reason=f"CPU average {_fmt_pct(cpu.average)} exceeds threshold {cpu_avg_threshold:.0f} %.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )

    # ── 6. CPU P95 spike safety ───────────────────────────────────────────────
    cpu_p95_ok = cpu.p95 is not None and cpu.p95 < cpu_p95_threshold
    facts.append(
        AnalysisFact(
            label="CPU P95 (spike safety)",
            observed=_fmt_pct(cpu.p95),
            threshold=f"< {cpu_p95_threshold:.0f} %",
            passed=cpu_p95_ok,
        )
    )
    if not cpu_p95_ok:
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.not_candidate,
            reason=f"CPU P95 {_fmt_pct(cpu.p95)} exceeds spike-safety threshold {cpu_p95_threshold:.0f} %.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )

    # ── 7. CPU maximum burst safety ───────────────────────────────────────────
    cpu_max_ok = cpu.maximum is not None and cpu.maximum < cpu_max_threshold
    facts.append(
        AnalysisFact(
            label="CPU maximum (burst safety)",
            observed=_fmt_pct(cpu.maximum),
            threshold=f"< {cpu_max_threshold:.0f} %",
            passed=cpu_max_ok,
        )
    )
    if not cpu_max_ok:
        return _result(
            instance_id=instance.id,
            decision=CandidateDecision.not_candidate,
            reason=f"CPU maximum {_fmt_pct(cpu.maximum)} exceeds burst-safety threshold {cpu_max_threshold:.0f} %.",
            facts=facts,
            cpu_avg_threshold=cpu_avg_threshold,
            cpu_p95_threshold=cpu_p95_threshold,
            cpu_max_threshold=cpu_max_threshold,
        )

    # ── 8. All checks passed → candidate ─────────────────────────────────────
    return _result(
        instance_id=instance.id,
        decision=CandidateDecision.candidate,
        reason=(
            f"Low CPU utilisation confirmed: avg {_fmt_pct(cpu.average)}, "
            f"P95 {_fmt_pct(cpu.p95)}, max {_fmt_pct(cpu.maximum)}. "
            "No health issues detected. Safe to request AI analysis."
        ),
        facts=facts,
        cpu_avg_threshold=cpu_avg_threshold,
        cpu_p95_threshold=cpu_p95_threshold,
        cpu_max_threshold=cpu_max_threshold,
    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _result(
    *,
    instance_id: str,
    decision: CandidateDecision,
    reason: str,
    facts: list[AnalysisFact],
    cpu_avg_threshold: float,
    cpu_p95_threshold: float,
    cpu_max_threshold: float,
) -> CandidateResult:
    return CandidateResult(
        instance_id=instance_id,
        decision=decision,
        reason=reason,
        facts=facts,
        cpu_avg_threshold=cpu_avg_threshold,
        cpu_p95_threshold=cpu_p95_threshold,
        cpu_max_threshold=cpu_max_threshold,
        analyzed_at=datetime.now(UTC),
    )
