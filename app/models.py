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
