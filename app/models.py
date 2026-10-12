from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class EC2Instance(BaseModel):
    """Normalised representation of a single EC2 instance."""

    id: str
    name: str
    type: str
    state: str  # running | stopped | terminated | pending | …
    region: str
    launch_time: datetime | None = None
    tags: dict[str, str] = {}


# ---------------------------------------------------------------------------
# CloudWatch metric models
# ---------------------------------------------------------------------------


class MetricStatus(str, Enum):
    """Availability status of a single metric series."""

    ok = "ok"
    insufficient_data = "insufficient_data"  # < MIN_SAMPLES threshold
    unavailable = "unavailable"  # API returned no data at all


class MetricSummary(BaseModel):
    """Aggregated statistics for one CloudWatch metric over a time window."""

    name: str  # e.g. "CPUUtilization"
    unit: str  # e.g. "Percent", "Bytes", "Count"
    period_days: int

    # Aggregates — None means the metric was not available / not enough data.
    average: float | None = None
    p95: float | None = None  # only set when sample_count >= MIN_SAMPLES_FOR_P95
    maximum: float | None = None
    sample_count: int = 0

    status: MetricStatus = MetricStatus.unavailable
    window_start: datetime | None = None
    window_end: datetime | None = None


class InstanceMetrics(BaseModel):
    """All CloudWatch metrics fetched for one EC2 instance."""

    instance_id: str
    fetched_at: datetime
    cpu: MetricSummary
    network_in: MetricSummary
    network_out: MetricSummary
    status_check_failed: MetricSummary


# ---------------------------------------------------------------------------
# Deterministic analysis models (Stage 4)
# ---------------------------------------------------------------------------


class CandidateDecision(str, Enum):
    """Outcome of the deterministic rightsizing candidate evaluation."""

    candidate = "candidate"            # Safe to send to AI for recommendation
    not_candidate = "not_candidate"    # Evidence says resource is appropriately sized
    needs_more_data = "needs_more_data"  # Not enough history to decide


class AnalysisFact(BaseModel):
    """A single evidence check performed by the evaluator."""

    label: str              # Human-readable check name
    observed: str           # What was measured (e.g. "4.2 %")
    threshold: str | None   # Threshold that was applied (e.g. "< 10 %")
    passed: bool            # True = within acceptable range for candidacy


class CandidateResult(BaseModel):
    """Full deterministic candidate evaluation result."""

    instance_id: str
    decision: CandidateDecision
    reason: str                   # Primary human-readable reason for the decision
    facts: list[AnalysisFact]     # All checks performed, with pass/fail

    # Thresholds used — stored for auditability.
    cpu_avg_threshold: float
    cpu_p95_threshold: float
    cpu_max_threshold: float

    analyzed_at: datetime

