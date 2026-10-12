"""Unit tests for deterministic candidate evaluator (Stage 4)."""
from __future__ import annotations

from datetime import UTC, datetime

from app.analysis.candidate import evaluate
from app.models import (
    CandidateDecision,
    EC2Instance,
    InstanceMetrics,
    MetricStatus,
    MetricSummary,
)


def _make_instance(state: str = "running", instance_type: str = "t3.medium") -> EC2Instance:
    return EC2Instance(
        id="i-test12345",
        name="test-server",
        state=state,
        type=instance_type,
        region="us-east-1",
        launch_time=datetime.now(UTC),
        tags={"env": "prod"},
    )


def _make_metrics(
    cpu_status: MetricStatus = MetricStatus.ok,
    cpu_avg: float | None = 4.0,
    cpu_p95: float | None = 12.0,
    cpu_max: float | None = 22.0,
    cpu_samples: int = 168,
    scf_status: MetricStatus = MetricStatus.ok,
    scf_avg: float | None = 0.0,
) -> InstanceMetrics:
    now = datetime.now(UTC)
    cpu_summary = MetricSummary(
        name="CPUUtilization",
        unit="Percent",
        period_days=7,
        average=cpu_avg,
        p95=cpu_p95,
        maximum=cpu_max,
        sample_count=cpu_samples,
        status=cpu_status,
    )
    scf_summary = MetricSummary(
        name="StatusCheckFailed",
        unit="Count",
        period_days=7,
        average=scf_avg,
        p95=0.0 if scf_avg is not None else None,
        maximum=0.0 if scf_avg is not None else None,
        sample_count=cpu_samples if scf_status != MetricStatus.unavailable else 0,
        status=scf_status,
    )
    dummy_net = MetricSummary(
        name="NetworkIn",
        unit="Bytes",
        period_days=7,
        average=100.0,
        p95=120.0,
        maximum=200.0,
        sample_count=168,
        status=MetricStatus.ok,
    )
    return InstanceMetrics(
        instance_id="i-test12345",
        fetched_at=now,
        cpu=cpu_summary,
        network_in=dummy_net,
        network_out=dummy_net,
        status_check_failed=scf_summary,
    )


def test_candidate_happy_path():
    """An underutilized running instance with sufficient samples passes all gates."""
    inst = _make_instance(state="running")
    metrics = _make_metrics(cpu_avg=4.5, cpu_p95=12.0, cpu_max=25.0)

    result = evaluate(inst, metrics)
    assert result.decision == CandidateDecision.candidate
    assert "Low CPU utilisation confirmed" in result.reason
    assert all(f.passed for f in result.facts)


def test_not_candidate_when_stopped():
    """Stopped instances must not be evaluated as candidates."""
    inst = _make_instance(state="stopped")
    metrics = _make_metrics()

    result = evaluate(inst, metrics)
    assert result.decision == CandidateDecision.not_candidate
    assert "stopped" in result.reason
    assert not result.facts[0].passed


def test_needs_more_data_when_cpu_unavailable():
    """If CloudWatch returned no CPU data, needs_more_data is returned."""
    inst = _make_instance()
    metrics = _make_metrics(cpu_status=MetricStatus.unavailable, cpu_avg=None, cpu_p95=None, cpu_max=None)

    result = evaluate(inst, metrics)
    assert result.decision == CandidateDecision.needs_more_data
    assert "No CPU utilisation data" in result.reason


def test_needs_more_data_when_insufficient_samples():
    """If CloudWatch has fewer than 24 samples (newly launched instance), needs_more_data."""
    inst = _make_instance()
    metrics = _make_metrics(
        cpu_status=MetricStatus.insufficient_data,
        cpu_avg=1.0,
        cpu_p95=None,
        cpu_max=1.5,
        cpu_samples=3,
    )

    result = evaluate(inst, metrics)
    assert result.decision == CandidateDecision.needs_more_data
    assert "Only 3 CPU sample(s)" in result.reason


def test_not_candidate_when_status_checks_failing():
    """Any status check failure blocks candidacy for stability."""
    inst = _make_instance()
    metrics = _make_metrics(scf_avg=0.5)

    result = evaluate(inst, metrics)
    assert result.decision == CandidateDecision.not_candidate
    assert "status check failures detected" in result.reason


def test_not_candidate_when_cpu_avg_exceeds_threshold():
    """CPU avg >= threshold rejects candidacy."""
    inst = _make_instance()
    metrics = _make_metrics(cpu_avg=15.0, cpu_p95=20.0, cpu_max=30.0)

    result = evaluate(inst, metrics, cpu_avg_threshold=10.0)
    assert result.decision == CandidateDecision.not_candidate
    assert "CPU average 15.0 % exceeds threshold" in result.reason


def test_not_candidate_when_p95_spike_exceeds_safety():
    """Low average but high P95 fails spike safety gate."""
    inst = _make_instance()
    metrics = _make_metrics(cpu_avg=8.0, cpu_p95=35.0, cpu_max=45.0)

    result = evaluate(inst, metrics, cpu_avg_threshold=10.0, cpu_p95_threshold=25.0)
    assert result.decision == CandidateDecision.not_candidate
    assert "CPU P95 35.0 % exceeds spike-safety threshold" in result.reason


def test_not_candidate_when_max_burst_exceeds_safety():
    """Low average and low P95 but extreme max spike fails burst safety gate."""
    inst = _make_instance()
    metrics = _make_metrics(cpu_avg=5.0, cpu_p95=15.0, cpu_max=65.0)

    result = evaluate(inst, metrics, cpu_max_threshold=50.0)
    assert result.decision == CandidateDecision.not_candidate
    assert "CPU maximum 65.0 % exceeds burst-safety threshold" in result.reason
