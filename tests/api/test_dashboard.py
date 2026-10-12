"""API-level tests for the dashboard and instance routes.

Settings are overridden so tests always use fake adapters, regardless of
any .env or environment variables present on the machine.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _force_fake_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure every test in this module uses offline fake adapters."""
    monkeypatch.setattr(settings, "aws_mode", False)
    monkeypatch.setattr(settings, "aws_region", "ap-south-1")


client = TestClient(app)


def test_dashboard_lists_fake_instances() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "api-server" in response.text
    assert "worker-server" in response.text


def test_instance_detail() -> None:
    response = client.get("/instances/i-0123456789abcdef0")

    assert response.status_code == 200
    assert "t3.large" in response.text


def test_instance_detail_shows_metrics() -> None:
    response = client.get("/instances/i-0123456789abcdef0")

    assert response.status_code == 200
    # Metric cards should appear for the running instance.
    assert "CPU utilisation" in response.text
    assert "Network in" in response.text


def test_unknown_instance_returns_not_found() -> None:
    response = client.get("/instances/i-does-not-exist")

    assert response.status_code == 404


def test_instance_list_partial() -> None:
    response = client.get("/instances")

    assert response.status_code == 200
    assert "Refresh instances" not in response.text
    assert "api-server" in response.text


def test_instance_detail_shows_analysis_result() -> None:
    response = client.get("/instances/i-0123456789abcdef0")

    assert response.status_code == 200
    assert "Rightsizing analysis" in response.text
    assert "Fact checks &amp; safety gates" in response.text or "Fact checks & safety gates" in response.text
