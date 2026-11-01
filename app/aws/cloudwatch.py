"""AWS CloudWatch client interface and adapters.

Two concrete adapters are provided:
- FakeCloudWatchAdapter — returns deterministic synthetic data; used offline.
- BotoCloudWatchAdapter — calls the real CloudWatch API via boto3.

Both implement CloudWatchClient so the rest of the app is decoupled from AWS.

Metric resolution strategy
---------------------------
We request data at 1-hour granularity (3600 s) for the configured window.
Statistics fetched per metric: Average, Maximum, SampleCount.

P95 is derived from the raw datapoints list when sample_count >= MIN_SAMPLES_FOR_P95.
Missing data is never silently treated as zero — the MetricStatus will be set
to ``insufficient_data`` or ``unavailable`` instead.
"""
from __future__ import annotations

import logging
import math
import statistics
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models import InstanceMetrics, MetricStatus, MetricSummary

logger = logging.getLogger(__name__)

# Minimum number of 1-hour datapoints required to report a P95 value.
MIN_SAMPLES_FOR_P95 = 24  # 1 day worth of hourly data

# CloudWatch metric definitions: (MetricName, Namespace, Unit, field_name)
_METRIC_DEFS: list[tuple[str, str, str, str]] = [
    ("CPUUtilization", "AWS/EC2", "Percent", "cpu"),
    ("NetworkIn", "AWS/EC2", "Bytes", "network_in"),
    ("NetworkOut", "AWS/EC2", "Bytes", "network_out"),
    ("StatusCheckFailed", "AWS/EC2", "Count", "status_check_failed"),
]


# ---------------------------------------------------------------------------
# Shared aggregation logic
# ---------------------------------------------------------------------------


def _compute_summary(
    name: str,
    unit: str,
    period_days: int,
    datapoints: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> MetricSummary:
    """Build a MetricSummary from a raw list of CloudWatch datapoints.

    Rules
    -----
    - If datapoints is empty → status=unavailable, all aggregates None.
    - If sample_count < MIN_SAMPLES_FOR_P95 → status=insufficient_data, p95=None.
    - Otherwise → status=ok with all aggregates populated.
    """
    if not datapoints:
        return MetricSummary(
            name=name,
            unit=unit,
            period_days=period_days,
            status=MetricStatus.unavailable,
            window_start=window_start,
            window_end=window_end,
        )

    averages = [dp["Average"] for dp in datapoints if "Average" in dp]
    maximums = [dp["Maximum"] for dp in datapoints if "Maximum" in dp]
    total_samples = sum(dp.get("SampleCount", 0) for dp in datapoints)

    overall_avg = statistics.mean(averages) if averages else None
    overall_max = max(maximums) if maximums else None

    # P95 from the per-datapoint averages (best proxy without raw samples).
    p95: float | None = None
    status = MetricStatus.ok
    if len(averages) < MIN_SAMPLES_FOR_P95:
        status = MetricStatus.insufficient_data
    else:
        sorted_vals = sorted(averages)
        idx = math.ceil(0.95 * len(sorted_vals)) - 1
        p95 = sorted_vals[max(idx, 0)]

    return MetricSummary(
        name=name,
        unit=unit,
        period_days=period_days,
        average=overall_avg,
        p95=p95,
        maximum=overall_max,
        sample_count=int(total_samples),
        status=status,
        window_start=window_start,
        window_end=window_end,
    )


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class CloudWatchClient(ABC):
    """Abstract interface for CloudWatch metric retrieval."""

    @abstractmethod
    def get_instance_metrics(
        self,
        instance_id: str,
        window_days: int = 7,
    ) -> InstanceMetrics:
        """Return metric summaries for the given EC2 instance."""


# ---------------------------------------------------------------------------
# Fake adapter (offline / development)
# ---------------------------------------------------------------------------


def _fake_summary(
    name: str,
    unit: str,
    period_days: int,
    avg: float,
    p95: float,
    maximum: float,
    samples: int,
    window_start: datetime,
    window_end: datetime,
) -> MetricSummary:
    return MetricSummary(
        name=name,
        unit=unit,
        period_days=period_days,
        average=avg,
        p95=p95,
        maximum=maximum,
        sample_count=samples,
        status=MetricStatus.ok,
        window_start=window_start,
        window_end=window_end,
    )


class FakeCloudWatchAdapter(CloudWatchClient):
    """Returns synthetic but realistic metric data. No AWS credentials needed."""

    def get_instance_metrics(
        self,
        instance_id: str,
        window_days: int = 7,
    ) -> InstanceMetrics:
        now = datetime.now(UTC)
        start = now - timedelta(days=window_days)

        # api-server (running) — looks like a plausible rightsizing candidate.
        if instance_id == "i-0123456789abcdef0":
            return InstanceMetrics(
                instance_id=instance_id,
                fetched_at=now,
                cpu=_fake_summary("CPUUtilization", "Percent", window_days, 4.2, 11.3, 22.8, 168, start, now),
                network_in=_fake_summary("NetworkIn", "Bytes", window_days, 1_450_000, 3_200_000, 8_900_000, 168, start, now),
                network_out=_fake_summary("NetworkOut", "Bytes", window_days, 980_000, 2_100_000, 5_600_000, 168, start, now),
                status_check_failed=_fake_summary("StatusCheckFailed", "Count", window_days, 0.0, 0.0, 0.0, 168, start, now),
            )

        # worker-server (stopped) — not enough history.
        return InstanceMetrics(
            instance_id=instance_id,
            fetched_at=now,
            cpu=MetricSummary(name="CPUUtilization", unit="Percent", period_days=window_days, status=MetricStatus.unavailable, window_start=start, window_end=now),
            network_in=MetricSummary(name="NetworkIn", unit="Bytes", period_days=window_days, status=MetricStatus.unavailable, window_start=start, window_end=now),
            network_out=MetricSummary(name="NetworkOut", unit="Bytes", period_days=window_days, status=MetricStatus.unavailable, window_start=start, window_end=now),
            status_check_failed=MetricSummary(name="StatusCheckFailed", unit="Count", period_days=window_days, status=MetricStatus.unavailable, window_start=start, window_end=now),
        )


# ---------------------------------------------------------------------------
# Boto3 adapter (real AWS)
# ---------------------------------------------------------------------------


class BotoCloudWatchAdapter(CloudWatchClient):
    """Calls the real AWS CloudWatch API using boto3.

    All AWS errors are wrapped as ``RuntimeError`` so the caller never sees
    raw boto3 exceptions.
    """

    _PERIOD_SECONDS = 3600  # 1-hour granularity

    def __init__(self, region: str) -> None:
        self._region = region
        self._client = boto3.client("cloudwatch", region_name=region)

    def get_instance_metrics(
        self,
        instance_id: str,
        window_days: int = 7,
    ) -> InstanceMetrics:
        now = datetime.now(UTC)
        window_start = now - timedelta(days=window_days)

        summaries: dict[str, MetricSummary] = {}
        for metric_name, namespace, unit, field in _METRIC_DEFS:
            summaries[field] = self._fetch_metric(
                instance_id=instance_id,
                metric_name=metric_name,
                namespace=namespace,
                unit=unit,
                window_start=window_start,
                window_end=now,
                window_days=window_days,
            )

        return InstanceMetrics(
            instance_id=instance_id,
            fetched_at=now,
            cpu=summaries["cpu"],
            network_in=summaries["network_in"],
            network_out=summaries["network_out"],
            status_check_failed=summaries["status_check_failed"],
        )

    def _fetch_metric(
        self,
        instance_id: str,
        metric_name: str,
        namespace: str,
        unit: str,
        window_start: datetime,
        window_end: datetime,
        window_days: int,
    ) -> MetricSummary:
        try:
            response = self._client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=window_start,
                EndTime=window_end,
                Period=self._PERIOD_SECONDS,
                Statistics=["Average", "Maximum", "SampleCount"],
                Unit=unit,
            )
            datapoints: list[dict] = response.get("Datapoints", [])
            # Sort chronologically for consistent P95 calculation.
            datapoints.sort(key=lambda dp: dp["Timestamp"])

            return _compute_summary(
                name=metric_name,
                unit=unit,
                period_days=window_days,
                datapoints=datapoints,
                window_start=window_start,
                window_end=window_end,
            )
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.error("AWS ClientError fetching %s for %s: %s", metric_name, instance_id, code)
            raise RuntimeError(f"AWS error ({code}): unable to fetch {metric_name}") from exc
        except BotoCoreError as exc:
            logger.error("BotoCoreError fetching %s for %s: %s", metric_name, instance_id, exc)
            raise RuntimeError(f"AWS connection error: unable to fetch {metric_name}") from exc
