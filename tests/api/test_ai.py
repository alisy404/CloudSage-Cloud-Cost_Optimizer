from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import _recommendations, app


@pytest.fixture(autouse=True)
def _force_fake_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "aws_mode", False)
    monkeypatch.setattr(settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(settings, "llm_provider", "fake")
    _recommendations.clear()


client = TestClient(app)


def test_analyze_candidate_returns_recommendation_ui() -> None:
    response = client.post("/instances/i-0123456789abcdef0/analyze")

    assert response.status_code == 200
    assert "AI recommendation" not in response.text
    assert "Recommendation" in response.text
    assert "Current configuration" in response.text
    assert "Proposed configuration" in response.text
    assert "Required validation" in response.text


def test_analyze_non_candidate_is_safe() -> None:
    response = client.post("/instances/i-0fedcba9876543210/analyze")

    assert response.status_code == 200
    assert "AI analysis unavailable" in response.text
    assert "deterministic candidate" in response.text


def test_analyze_unknown_instance_returns_not_found() -> None:
    response = client.post("/instances/i-does-not-exist/analyze")

    assert response.status_code == 404


def test_approval_records_workflow_state_and_actor() -> None:
    client.post("/instances/i-0123456789abcdef0/analyze")

    response = client.post(
        "/instances/i-0123456789abcdef0/recommendation/approve",
        headers={"X-User": "bob"},
    )

    assert response.status_code == 200
    assert "Approved by bob" in response.text
    assert _recommendations["i-0123456789abcdef0"]["status"] == "approved"


def test_rejection_is_terminal_and_blocks_repeat_decision() -> None:
    client.post("/instances/i-0123456789abcdef0/analyze")
    rejected = client.post("/instances/i-0123456789abcdef0/recommendation/reject")

    assert rejected.status_code == 200
    assert "Rejected by local-user" in rejected.text
    assert "Terraform changes are blocked" in rejected.text

    repeated = client.post("/instances/i-0123456789abcdef0/recommendation/approve")
    assert repeated.status_code == 200
    assert "Rejected by local-user" in repeated.text
    assert _recommendations["i-0123456789abcdef0"]["status"] == "rejected"
