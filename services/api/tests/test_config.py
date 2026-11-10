from app.config import Settings


def test_render_postgres_connection_string_uses_psycopg3_driver() -> None:
    settings = Settings(database_url="postgresql://user:pass@host:5432/zhuqing")
    assert settings.database_url == "postgresql+psycopg://user:pass@host:5432/zhuqing"


def test_legacy_postgres_connection_string_is_normalized() -> None:
    settings = Settings(database_url="postgres://user:pass@host:5432/zhuqing")
    assert settings.database_url == "postgresql+psycopg://user:pass@host:5432/zhuqing"
