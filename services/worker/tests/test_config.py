import pytest

from app.config import Settings


def test_blank_base_url_values_use_environment_appropriate_defaults(monkeypatch) -> None:
    monkeypatch.delenv("OPEN_METEO_USAGE", raising=False)
    monkeypatch.delenv("OPEN_METEO_API_KEY", raising=False)
    monkeypatch.setenv("OPEN_METEO_BASE_URL", "")
    monkeypatch.setenv("OPEN_METEO_SINGLE_RUNS_BASE_URL", "")

    settings = Settings.from_env()

    assert settings.open_meteo_base_url == "https://api.open-meteo.com"
    assert settings.open_meteo_single_runs_base_url == "https://single-runs-api.open-meteo.com"


def test_commercial_usage_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_METEO_USAGE", "commercial")
    monkeypatch.delenv("OPEN_METEO_API_KEY", raising=False)

    with pytest.raises(ValueError, match="requires OPEN_METEO_API_KEY"):
        Settings.from_env()


def test_database_url_normalizes_render_postgres_connection_strings() -> None:
    from app.db import normalize_database_url

    assert normalize_database_url("postgres://user:pass@host:5432/db") == (
        "postgresql+psycopg://user:pass@host:5432/db"
    )
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == (
        "postgresql+psycopg://user:pass@host:5432/db"
    )
