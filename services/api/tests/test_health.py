from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_data_status_is_initializing() -> None:
    response = client.get("/api/v1/data-status")
    assert response.status_code == 200
    assert response.json()["status"] == "initializing"
    assert response.json()["provider"] == "open-meteo"


def test_overview_does_not_invent_forecast_values() -> None:
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "initializing"
    assert payload["next_sunshine_window"] is None
    assert payload["coverage"] is None
