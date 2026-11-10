from __future__ import annotations

from datetime import datetime
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ForecastLocation(Base):
    __tablename__ = "forecast_locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    location_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    location_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name_zh: Mapped[str | None] = mapped_column(String(80))
    name_en: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    area_km2: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    geometry = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    cell_geometry = mapped_column(Geometry("MULTIPOLYGON", srid=4326))


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (
        Index("ix_forecast_runs_model_init", "model_id", "model_run_at"),
        Index("ix_forecast_runs_retrieved_at", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    temporal_resolution_seconds: Mapped[int | None] = mapped_column(Integer)
    update_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    spatial_resolution_km: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_days: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    forecast_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_license: Mapped[str] = mapped_column(String(80), nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ForecastRunLocation(Base):
    __tablename__ = "forecast_run_locations"

    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("forecast_runs.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("forecast_locations.id"), primary_key=True)
    requested_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    requested_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    resolved_latitude: Mapped[float | None] = mapped_column(Float)
    resolved_longitude: Mapped[float | None] = mapped_column(Float)


class ForecastHourly(Base):
    __tablename__ = "forecast_hourly"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "location_id"],
            ["forecast_run_locations.run_id", "forecast_run_locations.location_id"],
            ondelete="CASCADE",
        ),
        Index("ix_forecast_hourly_valid_at", "valid_at"),
    )

    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    location_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    lead_hours: Mapped[float | None] = mapped_column(Float)
    native_step_seconds: Mapped[int | None] = mapped_column(Integer)
    is_interpolated: Mapped[bool | None] = mapped_column(Boolean)
    sunshine_duration_seconds: Mapped[float | None] = mapped_column(Float)
    shortwave_radiation_wm2: Mapped[float | None] = mapped_column(Float)
    direct_normal_irradiance_wm2: Mapped[float | None] = mapped_column(Float)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float)
    precipitation_mm: Mapped[float | None] = mapped_column(Float)
    temperature_2m_c: Mapped[float | None] = mapped_column(Float)
    relative_humidity_2m_pct: Mapped[float | None] = mapped_column(Float)
    dew_point_2m_c: Mapped[float | None] = mapped_column(Float)
    wind_speed_10m_kmh: Mapped[float | None] = mapped_column(Float)
    wind_direction_10m_deg: Mapped[float | None] = mapped_column(Float)
    visibility_m: Mapped[float | None] = mapped_column(Float)
