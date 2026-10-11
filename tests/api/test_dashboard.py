from fastapi.testclient import TestClient

from app.main import app

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


def test_unknown_instance_returns_not_found() -> None:
    response = client.get("/instances/i-does-not-exist")

    assert response.status_code == 404


def test_instance_list_partial() -> None:
    response = client.get("/instances")

    assert response.status_code == 200
    assert "Refresh instances" not in response.text
    assert "api-server" in response.text
