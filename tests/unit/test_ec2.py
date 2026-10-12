"""Unit tests for app.aws.ec2 — boto3 is always mocked here."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.aws.ec2 import BotoEC2Adapter, FakeEC2Adapter, _normalise_instance

# ---------------------------------------------------------------------------
# FakeEC2Adapter
# ---------------------------------------------------------------------------


class TestFakeEC2Adapter:
    def test_list_returns_instances(self) -> None:
        adapter = FakeEC2Adapter()
        instances = adapter.list_instances()
        assert len(instances) >= 1

    def test_list_items_have_required_fields(self) -> None:
        for inst in FakeEC2Adapter().list_instances():
            assert inst.id.startswith("i-")
            assert inst.type != ""
            assert inst.state in {"running", "stopped", "terminated", "pending"}
            assert inst.region != ""

    def test_get_known_instance(self) -> None:
        adapter = FakeEC2Adapter()
        first = adapter.list_instances()[0]
        result = adapter.get_instance(first.id)
        assert result is not None
        assert result.id == first.id

    def test_get_unknown_instance_returns_none(self) -> None:
        adapter = FakeEC2Adapter()
        assert adapter.get_instance("i-does-not-exist") is None


# ---------------------------------------------------------------------------
# _normalise_instance helper
# ---------------------------------------------------------------------------


class TestNormaliseInstance:
    _REGION = "ap-south-1"

    def _raw(self, **overrides: object) -> dict:
        base: dict = {
            "InstanceId": "i-abc123",
            "InstanceType": "t3.micro",
            "State": {"Name": "running"},
            "LaunchTime": datetime(2024, 1, 1, tzinfo=UTC),
            "Tags": [{"Key": "Name", "Value": "test-box"}, {"Key": "Env", "Value": "staging"}],
        }
        base.update(overrides)
        return base

    def test_fields_are_mapped_correctly(self) -> None:
        inst = _normalise_instance(self._raw(), self._REGION)
        assert inst.id == "i-abc123"
        assert inst.type == "t3.micro"
        assert inst.state == "running"
        assert inst.name == "test-box"
        assert inst.region == self._REGION
        assert inst.tags == {"Name": "test-box", "Env": "staging"}

    def test_missing_name_tag_yields_empty_string(self) -> None:
        raw = self._raw(Tags=[{"Key": "Env", "Value": "prod"}])
        inst = _normalise_instance(raw, self._REGION)
        assert inst.name == ""

    def test_no_tags_yields_empty_dict(self) -> None:
        raw = self._raw(Tags=None)
        inst = _normalise_instance(raw, self._REGION)
        assert inst.tags == {}
        assert inst.name == ""

    def test_naive_launch_time_gets_utc(self) -> None:
        raw = self._raw(LaunchTime=datetime(2024, 5, 10, 12, 0, 0))
        inst = _normalise_instance(raw, self._REGION)
        assert inst.launch_time is not None
        assert inst.launch_time.tzinfo is not None


# ---------------------------------------------------------------------------
# BotoEC2Adapter — all AWS calls mocked
# ---------------------------------------------------------------------------


def _make_reservation(instance_id: str, state: str = "running") -> dict:
    return {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": instance_id,
                        "InstanceType": "t3.small",
                        "State": {"Name": state},
                        "LaunchTime": datetime(2024, 1, 1, tzinfo=UTC),
                        "Tags": [{"Key": "Name", "Value": "mocked-box"}],
                    }
                ]
            }
        ]
    }


def _make_client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "mocked"}}, "DescribeInstances")


@pytest.fixture()
def boto_adapter() -> BotoEC2Adapter:
    """Return a BotoEC2Adapter whose underlying boto3 client is mocked."""
    with patch("app.aws.ec2.boto3.client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        adapter = BotoEC2Adapter(region="ap-south-1")
        adapter._client = mock_client  # expose for test configuration
        yield adapter


class TestBotoEC2AdapterListInstances:
    def test_returns_normalised_instances(self, boto_adapter: BotoEC2Adapter) -> None:
        paginator = MagicMock()
        paginator.paginate.return_value = [_make_reservation("i-111aaa")]
        boto_adapter._client.get_paginator.return_value = paginator

        results = boto_adapter.list_instances()

        assert len(results) == 1
        assert results[0].id == "i-111aaa"
        assert results[0].state == "running"

    def test_handles_multiple_pages(self, boto_adapter: BotoEC2Adapter) -> None:
        paginator = MagicMock()
        paginator.paginate.return_value = [
            _make_reservation("i-page1"),
            _make_reservation("i-page2", state="stopped"),
        ]
        boto_adapter._client.get_paginator.return_value = paginator

        results = boto_adapter.list_instances()

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"i-page1", "i-page2"}

    def test_empty_result_is_ok(self, boto_adapter: BotoEC2Adapter) -> None:
        paginator = MagicMock()
        paginator.paginate.return_value = [{"Reservations": []}]
        boto_adapter._client.get_paginator.return_value = paginator

        results = boto_adapter.list_instances()
        assert results == []

    def test_client_error_raises_runtime_error(self, boto_adapter: BotoEC2Adapter) -> None:
        paginator = MagicMock()
        paginator.paginate.side_effect = _make_client_error("AccessDenied")
        boto_adapter._client.get_paginator.return_value = paginator

        with pytest.raises(RuntimeError, match="AWS error"):
            boto_adapter.list_instances()


class TestBotoEC2AdapterGetInstance:
    def test_returns_instance_when_found(self, boto_adapter: BotoEC2Adapter) -> None:
        boto_adapter._client.describe_instances.return_value = _make_reservation("i-found")

        result = boto_adapter.get_instance("i-found")

        assert result is not None
        assert result.id == "i-found"

    def test_returns_none_when_not_found(self, boto_adapter: BotoEC2Adapter) -> None:
        boto_adapter._client.describe_instances.return_value = {"Reservations": []}

        result = boto_adapter.get_instance("i-ghost")
        assert result is None

    def test_not_found_client_error_returns_none(self, boto_adapter: BotoEC2Adapter) -> None:
        boto_adapter._client.describe_instances.side_effect = _make_client_error(
            "InvalidInstanceID.NotFound"
        )

        result = boto_adapter.get_instance("i-missing")
        assert result is None

    def test_other_client_error_raises_runtime_error(self, boto_adapter: BotoEC2Adapter) -> None:
        boto_adapter._client.describe_instances.side_effect = _make_client_error("UnauthorizedOperation")

        with pytest.raises(RuntimeError, match="AWS error"):
            boto_adapter.get_instance("i-any")
