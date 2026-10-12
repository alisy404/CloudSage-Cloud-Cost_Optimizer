"""AWS EC2 client interface and adapters.

Two concrete adapters are provided:
- FakeEC2Adapter   — returns hard-coded instances; used when AWS_MODE=false.
- BotoEC2Adapter   — calls the real AWS EC2 API via boto3; used when AWS_MODE=true.

Both implement EC2Client so the rest of the application never needs to know
which one is active.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models import EC2Instance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class EC2Client(ABC):
    """Abstract interface for EC2 instance discovery."""

    @abstractmethod
    def list_instances(self) -> list[EC2Instance]:
        """Return all EC2 instances visible to the configured credentials."""

    @abstractmethod
    def get_instance(self, instance_id: str) -> EC2Instance | None:
        """Return a single instance by ID, or None if not found."""


# ---------------------------------------------------------------------------
# Fake adapter (offline / development)
# ---------------------------------------------------------------------------

_FAKE_INSTANCES: list[EC2Instance] = [
    EC2Instance(
        id="i-0123456789abcdef0",
        name="api-server",
        type="t3.large",
        state="running",
        region="ap-south-1",
        launch_time=datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC),
        tags={"Environment": "dev", "Team": "platform"},
    ),
    EC2Instance(
        id="i-0fedcba9876543210",
        name="worker-server",
        type="t3.medium",
        state="stopped",
        region="ap-south-1",
        launch_time=datetime(2024, 3, 15, 8, 30, 0, tzinfo=UTC),
        tags={"Environment": "dev", "Team": "platform"},
    ),
]


class FakeEC2Adapter(EC2Client):
    """Returns static fake instances. Safe to use without AWS credentials."""

    def list_instances(self) -> list[EC2Instance]:
        return list(_FAKE_INSTANCES)

    def get_instance(self, instance_id: str) -> EC2Instance | None:
        return next((i for i in _FAKE_INSTANCES if i.id == instance_id), None)


# ---------------------------------------------------------------------------
# Boto3 adapter (real AWS)
# ---------------------------------------------------------------------------


def _extract_name(tags: list[dict] | None) -> str:
    """Pull the 'Name' tag value, or return an empty string."""
    if not tags:
        return ""
    return next((t["Value"] for t in tags if t["Key"] == "Name"), "")


def _normalise_tags(tags: list[dict] | None) -> dict[str, str]:
    if not tags:
        return {}
    return {t["Key"]: t["Value"] for t in tags}


def _normalise_instance(raw: dict, region: str) -> EC2Instance:
    """Convert a raw boto3 instance dict into an EC2Instance model."""
    tags = raw.get("Tags")
    launch_time: datetime | None = raw.get("LaunchTime")
    if launch_time and launch_time.tzinfo is None:
        launch_time = launch_time.replace(tzinfo=UTC)

    return EC2Instance(
        id=raw["InstanceId"],
        name=_extract_name(tags),
        type=raw["InstanceType"],
        state=raw["State"]["Name"],
        region=region,
        launch_time=launch_time,
        tags=_normalise_tags(tags),
    )


class BotoEC2Adapter(EC2Client):
    """Calls the real AWS EC2 API using boto3.

    Raises ``RuntimeError`` for AWS credential / permission errors so callers
    can handle them in one place without the rest of the app crashing.
    """

    def __init__(self, region: str) -> None:
        self._region = region
        self._client = boto3.client("ec2", region_name=region)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_instances(self) -> list[EC2Instance]:
        """Return all instances across all states via paginated DescribeInstances."""
        try:
            instances: list[EC2Instance] = []
            paginator = self._client.get_paginator("describe_instances")
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for raw in reservation.get("Instances", []):
                        instances.append(_normalise_instance(raw, self._region))
            logger.info("EC2 list_instances returned %d instances", len(instances))
            return instances
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            logger.error("AWS ClientError in list_instances: %s", code)
            raise RuntimeError(f"AWS error ({code}): unable to list EC2 instances") from exc
        except BotoCoreError as exc:
            logger.error("BotoCoreError in list_instances: %s", exc)
            raise RuntimeError("AWS connection error: unable to list EC2 instances") from exc

    def get_instance(self, instance_id: str) -> EC2Instance | None:
        """Fetch a specific instance by ID. Returns None if not found."""
        try:
            response = self._client.describe_instances(InstanceIds=[instance_id])
            reservations = response.get("Reservations", [])
            if not reservations:
                return None
            raw = reservations[0]["Instances"][0]
            return _normalise_instance(raw, self._region)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            # AWS returns InvalidInstanceID.NotFound when the ID does not exist.
            if code == "InvalidInstanceID.NotFound":
                return None
            logger.error("AWS ClientError in get_instance(%s): %s", instance_id, code)
            raise RuntimeError(f"AWS error ({code}): unable to fetch instance {instance_id}") from exc
        except BotoCoreError as exc:
            logger.error("BotoCoreError in get_instance(%s): %s", instance_id, exc)
            raise RuntimeError(f"AWS connection error: unable to fetch instance {instance_id}") from exc
