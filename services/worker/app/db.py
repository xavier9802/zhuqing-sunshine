from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models import Base


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)
    migrations = (
        """
        ALTER TABLE forecast_locations
        ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
        """,
        """
        ALTER TABLE forecast_run_locations
        ADD COLUMN IF NOT EXISTS requested_latitude DOUBLE PRECISION
        """,
        """
        ALTER TABLE forecast_run_locations
        ADD COLUMN IF NOT EXISTS requested_longitude DOUBLE PRECISION
        """,
        """
        UPDATE forecast_run_locations AS run_location
        SET requested_latitude = location.latitude,
            requested_longitude = location.longitude
        FROM forecast_locations AS location
        WHERE run_location.location_id = location.id
          AND (
            run_location.requested_latitude IS NULL
            OR run_location.requested_longitude IS NULL
          )
        """,
        """
        ALTER TABLE forecast_run_locations
        ALTER COLUMN requested_latitude SET NOT NULL
        """,
        """
        ALTER TABLE forecast_run_locations
        ALTER COLUMN requested_longitude SET NOT NULL
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_forecast_locations_active
        ON forecast_locations (is_active)
        """,
    )
    with engine.begin() as connection:
        for statement in migrations:
            connection.execute(text(statement))


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
