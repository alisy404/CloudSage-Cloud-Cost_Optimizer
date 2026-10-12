"""Unit tests for app.aws.cloudwatch — boto3 is always mocked here."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.aws.cloudwatch import (
    MIN_SAMPLES_FOR_P95,
    BotoCloudWatchAdapter,
    FakeCloudWatchAdapter,
    _compute_summary,
)
from app.models import MetricStatus

# ---------------------------------------------------------------------------
# _compute_summary — the core aggregation helper
# ---------------------------------------------------------------------------


class TestComputeSummary:
    _NOW = datetime(2024, 7, 1, tzinfo=UTC)
    _START = _NOW - timedelta(days=7)

    def _dp(self, avg: float, maximum: float, sample_count: float = 1.0) -> dict:
        return {"Average": avg, "Maximum": maximum, "SampleCount": sample_count, "Timestamp": self._NOW}

    def test_empty_datapoints_returns_unavailable(self) -> None:
        result = _compute_summary("CPUUtilization", "Percent", 7, [], self._START, self._NOW)
        assert result.status == MetricStatus.unavailable
        assert result.average is None
        assert result.p95 is None
        assert result.maximum is None
        assert result.sample_count == 0

    def test_sufficient_samples_returns_ok_with_p95(self) -> None:
        datapoints = [self._dp(float(i), float(i) + 5) for i in range(MIN_SAMPLES_FOR_P95)]
        result = _compute_summary("CPUUtilization", "Percent", 7, datapoints, self._START, self._NOW)
        assert result.status == MetricStatus.ok
        assert result.average is not None
        assert result.p95 is not None
        assert result.maximum is not None

    def test_insufficient_samples_returns_insufficient_data(self) -> None:
        datapoints = [self._dp(10.0, 15.0) for _ in range(MIN_SAMPLES_FOR_P95 - 1)]
        result = _compute_summary("CPUUtilization", "Percent", 7, datapoints, self._START, self._NOW)
        assert result.status == MetricStatus.insufficient_data
        assert result.p95 is None
        assert result.average is not None  # average is still present

    def test_p95_is_above_median(self) -> None:
        """P95 of a sorted list of 100 values must be near the high end."""
        datapoints = [self._dp(float(i), float(i) + 1) for i in range(100)]
        result = _compute_summary("CPUUtilization", "Percent", 7, datapoints, self._START, self._NOW)
        assert result.p95 is not None
        assert result.p95 >= result.average  # type: ignore[operator]

    def test_maximum_is_correct(self) -> None:
        datapoints = [self._dp(5.0, 10.0), self._dp(3.0, 99.0), self._dp(7.0, 50.0)]
        result = _compute_summary("CPUUtilization", "Percent", 7, datapoints, self._START, self._NOW)
        assert result.maximum == 99.0

    def test_sample_count_is_summed(self) -> None:
        datapoints = [self._dp(5.0, 10.0, sample_count=60.0) for _ in range(3)]
        result = _compute_summary("CPUUtilization", "Percent", 7, datapoints, self._START, self._NOW)
        assert result.sample_count == 180

    def test_missing_data_not_treated_as_zero(self) -> None:
        result = _compute_summary("CPUUtilization", "Percent", 7, [], self._START, self._NOW)
        assert result.average is None, "empty data must NOT become 0"
        assert result.maximum is None


# ---------------------------------------------------------------------------
# FakeCloudWatchAdapter
# ---------------------------------------------------------------------------


class TestFakeCloudWatchAdapter:
    def test_running_instance_returns_ok_metrics(self) -> None:
        adapter = FakeCloudWatchAdapter()
        m = adapter.get_instance_metrics("i-0123456789abcdef0", window_days=7)
        assert m.cpu.status == MetricStatus.ok
        assert m.cpu.average is not None
        assert m.cpu.average > 0

    def test_stopped_instance_returns_unavailable(self) -> None:
        adapter = FakeCloudWatchAdapter()
        m = adapter.get_instance_metrics("i-0fedcba9876543210", window_days=7)
        assert m.cpu.status == MetricStatus.unavailable
        assert m.cpu.average is None

    def test_status_check_failed_is_zero_for_healthy_instance(self) -> None:
        adapter = FakeCloudWatchAdapter()
        m = adapter.get_instance_metrics("i-0123456789abcdef0")
        assert m.status_check_failed.average == 0.0

    def test_window_days_is_recorded(self) -> None:
        adapter = FakeCloudWatchAdapter()
        m = adapter.get_instance_metrics("i-0123456789abcdef0", window_days=30)
        assert m.cpu.period_days == 30

    def test_instance_id_is_recorded(self) -> None:
        adapter = FakeCloudWatchAdapter()
        m = adapter.get_instance_metrics("i-0123456789abcdef0")
        assert m.instance_id == "i-0123456789abcdef0"


# ---------------------------------------------------------------------------
# BotoCloudWatchAdapter — boto3 is mocked
# ---------------------------------------------------------------------------


def _make_datapoints(count: int, avg: float = 10.0, maximum: float = 20.0) -> list[dict]:
    base = datetime(2024, 7, 1, tzinfo=UTC)
    return [
        {
            "Timestamp": base + timedelta(hours=i),
            "Average": avg,
            "Maximum": maximum,
            "SampleCount": 1.0,
            "Unit": "Percent",
        }
        for i in range(count)
    ]


def _make_client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "mocked"}}, "GetMetricStatistics")


@pytest.fixture()
def boto_cw_adapter() -> BotoCloudWatchAdapter:
    with patch("app.aws.cloudwatch.boto3.client") as mock_factory:
        mock_client = MagicMock()
        mock_factory.return_value = mock_client
        adapter = BotoCloudWatchAdapter(region="ap-south-1")
        adapter._client = mock_client
        yield adapter


class TestBotoCloudWatchAdapterGetInstanceMetrics:
    def test_returns_instance_metrics_model(self, boto_cw_adapter: BotoCloudWatchAdapter) -> None:
        boto_cw_adapter._client.get_metric_statistics.return_value = {
            "Datapoints": _make_datapoints(MIN_SAMPLES_FOR_P95)
        }
        result = boto_cw_adapter.get_instance_metrics("i-abc", window_days=7)
        assert result.instance_id == "i-abc"
        assert result.cpu.status == MetricStatus.ok

    def test_empty_datapoints_mark_metric_unavailable(self, boto_cw_adapter: BotoCloudWatchAdapter) -> None:
        boto_cw_adapter._client.get_metric_statistics.return_value = {"Datapoints": []}
        result = boto_cw_adapter.get_instance_metrics("i-abc")
        assert result.cpu.status == MetricStatus.unavailable
        assert result.network_in.status == MetricStatus.unavailable

    def test_insufficient_samples_marked_correctly(self, boto_cw_adapter: BotoCloudWatchAdapter) -> None:
        boto_cw_adapter._client.get_metric_statistics.return_value = {
            "Datapoints": _make_datapoints(MIN_SAMPLES_FOR_P95 - 1)
        }
        result = boto_cw_adapter.get_instance_metrics("i-abc")
        assert result.cpu.status == MetricStatus.insufficient_data
        assert result.cpu.p95 is None

    def test_client_error_raises_runtime_error(self, boto_cw_adapter: BotoCloudWatchAdapter) -> None:
        boto_cw_adapter._client.get_metric_statistics.side_effect = _make_client_error("AccessDenied")
        with pytest.raises(RuntimeError, match="AWS error"):
            boto_cw_adapter.get_instance_metrics("i-abc")

    def test_window_days_controls_time_range(self, boto_cw_adapter: BotoCloudWatchAdapter) -> None:
        boto_cw_adapter._client.get_metric_statistics.return_value = {"Datapoints": []}
        boto_cw_adapter.get_instance_metrics("i-abc", window_days=30)
        call_kwargs = boto_cw_adapter._client.get_metric_statistics.call_args_list[0][1]
        delta = call_kwargs["EndTime"] - call_kwargs["StartTime"]
        assert delta.days == 30
