# ruff: noqa: B008
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.forecast import (
    MODEL_NAMES,
    CityHour,
    GridHour,
    aggregate_basin_hours,
    aggregate_daily,
    city_daily_summary,
    find_basin_sunshine_window,
    find_city_sunshine_window,
    local_iso,
)
from app.models import ForecastHourly, ForecastLocation, ForecastRun

SUPPORTED_MODELS = tuple(MODEL_NAMES)

app = FastAPI(
    title="追晴 API",
    description="四川盆地日照预测平台 API。所有预测均关联到可追溯的气象模型批次。",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


class ModelRunStatus(BaseModel):
    model_id: str
    model_name: str
    status: str
    model_run_at: datetime | None
    retrieved_at: datetime | None
    forecast_end_at: datetime | None
    locations_count: int


class DataStatus(BaseModel):
    status: str
    provider: str
    latest_model_run: datetime | None = None
    last_checked_at: datetime
    message: str
    models: list[ModelRunStatus] = []


def _model_id(value: str) -> str:
    if value not in SUPPORTED_MODELS:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的模型。可选值：{', '.join(SUPPORTED_MODELS)}",
        )
    return value


def _latest_run(session: Session, model_id: str) -> ForecastRun | None:
    return session.scalar(
        select(ForecastRun)
        .where(ForecastRun.model_id == model_id, ForecastRun.status == "complete")
        .order_by(ForecastRun.model_run_at.desc(), ForecastRun.retrieved_at.desc())
        .limit(1)
    )


def _grid_samples(session: Session, run_id: UUID, hours: int = 168) -> list[GridHour]:
    now = datetime.now(UTC)
    rows = session.execute(
        select(
            ForecastHourly.valid_at,
            ForecastLocation.area_km2,
            ForecastHourly.sunshine_duration_seconds,
            ForecastHourly.cloud_cover_pct,
            ForecastHourly.precipitation_mm,
            ForecastHourly.is_interpolated,
        )
        .join(ForecastLocation, ForecastLocation.id == ForecastHourly.location_id)
        .where(
            ForecastHourly.run_id == run_id,
            ForecastLocation.location_type == "grid",
            ForecastLocation.is_active.is_(True),
            ForecastHourly.valid_at >= now - timedelta(hours=1),
            ForecastHourly.valid_at <= now + timedelta(hours=hours),
        )
        .order_by(ForecastHourly.valid_at)
    ).all()
    return [
        GridHour(
            valid_at=row.valid_at,
            area_km2=float(row.area_km2 or 0),
            sunshine_seconds=float(row.sunshine_duration_seconds) if row.sunshine_duration_seconds is not None else None,
            cloud_cover_pct=float(row.cloud_cover_pct) if row.cloud_cover_pct is not None else None,
            precipitation_mm=float(row.precipitation_mm) if row.precipitation_mm is not None else None,
            is_interpolated=bool(row.is_interpolated),
        )
        for row in rows
    ]


def _city_samples(session: Session, run_id: UUID, slug: str | None = None) -> list[tuple[ForecastLocation, list[CityHour]]]:
    now = datetime.now(UTC)
    statement = (
        select(
            ForecastLocation,
            ForecastHourly.valid_at,
            ForecastHourly.sunshine_duration_seconds,
            ForecastHourly.cloud_cover_pct,
            ForecastHourly.precipitation_mm,
            ForecastHourly.temperature_2m_c,
            ForecastHourly.is_interpolated,
        )
        .join(ForecastHourly, ForecastHourly.location_id == ForecastLocation.id)
        .where(
            ForecastHourly.run_id == run_id,
            ForecastHourly.valid_at >= now - timedelta(hours=1),
            ForecastHourly.valid_at <= now + timedelta(days=7),
            ForecastLocation.location_type == "city",
            ForecastLocation.is_active.is_(True),
        )
        .order_by(ForecastLocation.name_zh, ForecastHourly.valid_at)
    )
    if slug:
        statement = statement.where(ForecastLocation.location_key == f"city:{slug}")
    grouped: dict[int, tuple[ForecastLocation, list[CityHour]]] = {}
    for row in session.execute(statement):
        location = row[0]
        grouped.setdefault(location.id, (location, []))[1].append(
            CityHour(
                valid_at=row.valid_at,
                sunshine_seconds=float(row.sunshine_duration_seconds) if row.sunshine_duration_seconds is not None else None,
                cloud_cover_pct=float(row.cloud_cover_pct) if row.cloud_cover_pct is not None else None,
                precipitation_mm=float(row.precipitation_mm) if row.precipitation_mm is not None else None,
                temperature_c=float(row.temperature_2m_c) if row.temperature_2m_c is not None else None,
                is_interpolated=bool(row.is_interpolated),
            )
        )
    return list(grouped.values())


def _run_payload(run: ForecastRun) -> dict[str, Any]:
    return {
        "model_id": run.model_id,
        "model_name": run.model_name,
        "model_run_at": local_iso(run.model_run_at),
        "retrieved_at": local_iso(run.retrieved_at),
        "forecast_end_at": local_iso(run.forecast_end_at),
        "spatial_resolution_km": run.spatial_resolution_km,
        "source": "Open-Meteo ECMWF Single Runs API",
        "source_url": run.source_url,
        "license": run.source_license,
        "request_metadata": run.request_metadata,
    }


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/ready", tags=["system"])
def readiness(session: Session = Depends(get_session)) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="数据库暂不可用") from exc
    return {"status": "ready", "database": "connected"}


@app.get("/api/v1/data-status", response_model=DataStatus, tags=["data"])
def data_status(session: Session = Depends(get_session)) -> DataStatus:
    checked_at = datetime.now(UTC)
    try:
        runs = session.scalars(
            select(ForecastRun)
            .where(ForecastRun.status == "complete")
            .order_by(ForecastRun.model_id, ForecastRun.model_run_at.desc())
        ).all()
        latest_by_model: dict[str, ForecastRun] = {}
        for run in runs:
            latest_by_model.setdefault(run.model_id, run)
        models: list[ModelRunStatus] = []
        for model_id in SUPPORTED_MODELS:
            run = latest_by_model.get(model_id)
            locations_count = 0
            if run:
                locations_count = session.scalar(
                    select(func.count()).select_from(
                        select(ForecastHourly.location_id)
                        .where(ForecastHourly.run_id == run.id)
                        .distinct()
                        .subquery()
                    )
                ) or 0
            models.append(ModelRunStatus(
                model_id=model_id,
                model_name=MODEL_NAMES[model_id],
                status="available" if run else "waiting",
                model_run_at=run.model_run_at if run else None,
                retrieved_at=run.retrieved_at if run else None,
                forecast_end_at=run.forecast_end_at if run else None,
                locations_count=locations_count,
            ))
        available = [item for item in models if item.status == "available"]
        latest = max((item.model_run_at for item in available if item.model_run_at), default=None)
        stale = any(
            item.retrieved_at and checked_at - item.retrieved_at > timedelta(hours=12)
            for item in available
        )
        status = "initializing" if not available else "degraded" if stale or len(available) < len(SUPPORTED_MODELS) else "available"
        message = (
            "尚未采集到完整的模型预报批次。"
            if not available else
            "部分模型数据缺失或已超过 12 小时未更新，请谨慎参考。"
            if status == "degraded" else
            "模型预报数据已接入。"
        )
        return DataStatus(
            status=status,
            provider="open-meteo",
            latest_model_run=latest,
            last_checked_at=checked_at,
            message=message,
            models=models,
        )
    except SQLAlchemyError:
        return DataStatus(
            status="initializing",
            provider="open-meteo",
            last_checked_at=checked_at,
            message="数据库暂不可用，尚不能读取真实预报数据。",
            models=[],
        )


@app.get("/api/v1/models", tags=["data"])
def models(session: Session = Depends(get_session)) -> dict[str, Any]:
    return data_status(session).model_dump(mode="json")


@app.get("/api/v1/overview", tags=["forecast"])
def overview(
    model: str = Query("ecmwf_ifs"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    model_id = _model_id(model)
    try:
        run = _latest_run(session, model_id)
        if run is None:
            return {
                "status": "initializing",
                "region": "sichuan-basin",
                "timezone": "Asia/Shanghai",
                "generated_at": local_iso(datetime.now(UTC)),
                "next_sunshine_window": None,
                "hourly": [],
                "daily_sunshine_hours": [],
                "coverage": None,
                "message": "尚未采集到该模型的完整预报批次，请先运行天气采集任务。",
                "model": None,
            }
        samples = _grid_samples(session, run.id)
        hourly = aggregate_basin_hours(samples)
        daily = aggregate_daily(hourly)
        window = find_basin_sunshine_window(hourly)
        if window:
            window["source_model"] = run.model_name
        coverage_values = [
            item["sunshine_coverage_pct"] for item in hourly
            if item["sunshine_coverage_pct"] is not None
        ]
        latest_coverage = coverage_values[0] if coverage_values else None
        return {
            "status": "available" if hourly else "degraded",
            "region": "sichuan-basin",
            "timezone": "Asia/Shanghai",
            "generated_at": local_iso(datetime.now(UTC)),
            "next_sunshine_window": window,
            "hourly": hourly[:72],
            "daily_sunshine_hours": daily[:7],
            "coverage": latest_coverage,
            "message": (
                "日照窗口按盆地有效日照覆盖率计算，属于模型预报推算，不代表地面实测。"
                if hourly else "该模型批次暂未包含可用的盆地网格日照数据。"
            ),
            "model": _run_payload(run),
        }
    except SQLAlchemyError:
        return {
            "status": "initializing",
            "region": "sichuan-basin",
            "timezone": "Asia/Shanghai",
            "generated_at": local_iso(datetime.now(UTC)),
            "next_sunshine_window": None,
            "hourly": [],
            "daily_sunshine_hours": [],
            "coverage": None,
            "message": "数据库暂不可用，尚不能读取真实预测。",
            "model": None,
        }


@app.get("/api/v1/cities", tags=["forecast"])
def cities(
    model: str = Query("ecmwf_ifs"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    model_id = _model_id(model)
    try:
        run = _latest_run(session, model_id)
        if run is None:
            return {"status": "initializing", "model": None, "cities": []}
        result = []
        for location, samples in _city_samples(session, run.id):
            window = find_city_sunshine_window(samples)
            daily = city_daily_summary(samples)
            result.append({
                "slug": location.location_key.removeprefix("city:"),
                "name": location.name_zh,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "next_sunshine_window": window,
                "daily": daily[:7],
                "status": "available" if samples else "pending",
            })
        return {"status": "available", "model": _run_payload(run), "cities": result}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="暂时无法读取城市预报") from exc


@app.get("/api/v1/cities/{slug}", tags=["forecast"])
def city_detail(
    slug: str,
    model: str = Query("ecmwf_ifs"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    model_id = _model_id(model)
    try:
        run = _latest_run(session, model_id)
        if run is None:
            raise HTTPException(status_code=404, detail="当前没有可用的城市预报数据")
        matches = _city_samples(session, run.id, slug)
        if not matches:
            raise HTTPException(status_code=404, detail="未找到该城市的预报数据")
        location, samples = matches[0]
        return {
            "status": "available",
            "city": {
                "slug": slug,
                "name": location.name_zh,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "next_sunshine_window": find_city_sunshine_window(samples),
                "daily": city_daily_summary(samples),
                "hourly": [
                    {
                        "valid_at": local_iso(row.valid_at),
                        "sunshine_minutes": round(row.sunshine_seconds / 60, 1) if row.sunshine_seconds is not None else None,
                        "cloud_cover_pct": row.cloud_cover_pct,
                        "precipitation_mm": row.precipitation_mm,
                        "temperature_c": row.temperature_c,
                        "is_interpolated": row.is_interpolated,
                    }
                    for row in samples
                ],
            },
            "model": _run_payload(run),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="暂时无法读取城市预报") from exc


@app.get("/api/v1/grid", tags=["forecast"])
def grid(
    model: str = Query("ecmwf_ifs"),
    valid_at: datetime | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    model_id = _model_id(model)
    try:
        run = _latest_run(session, model_id)
        if run is None:
            return {
                "status": "initializing",
                "model": None,
                "valid_at": None,
                "geojson": {"type": "FeatureCollection", "features": []},
            }

        target = valid_at
        if target is None:
            target = session.scalar(
                select(func.min(ForecastHourly.valid_at)).where(
                    ForecastHourly.run_id == run.id,
                    ForecastHourly.valid_at >= datetime.now(UTC),
                )
            )
            if target is None:
                target = session.scalar(
                    select(func.min(ForecastHourly.valid_at)).where(ForecastHourly.run_id == run.id)
                )
        if target is None:
            return {
                "status": "degraded",
                "model": _run_payload(run),
                "valid_at": None,
                "geojson": {"type": "FeatureCollection", "features": []},
            }
        target = target.astimezone(UTC) if target.tzinfo else target.replace(tzinfo=UTC)
        statement = (
            select(
                ForecastLocation.id,
                ForecastLocation.location_key,
                ForecastLocation.area_km2,
                ForecastHourly.valid_at,
                ForecastHourly.sunshine_duration_seconds,
                ForecastHourly.cloud_cover_pct,
                ForecastHourly.precipitation_mm,
                ForecastHourly.is_interpolated,
                func.ST_AsGeoJSON(ForecastLocation.cell_geometry).label("geometry_json"),
            )
            .join(ForecastHourly, ForecastHourly.location_id == ForecastLocation.id)
            .where(
                ForecastHourly.run_id == run.id,
                ForecastHourly.valid_at == target,
                ForecastLocation.location_type == "grid",
                ForecastLocation.is_active.is_(True),
                ForecastLocation.cell_geometry.is_not(None),
            )
        )
        rows = session.execute(statement).all()
        features = []
        for row in rows:
            if not row.geometry_json:
                continue
            features.append({
                "type": "Feature",
                "id": row.id,
                "geometry": json.loads(row.geometry_json),
                "properties": {
                    "location_key": row.location_key,
                    "area_km2": row.area_km2,
                    "sunshine_minutes": round(float(row.sunshine_duration_seconds) / 60, 1) if row.sunshine_duration_seconds is not None else None,
                    "cloud_cover_pct": row.cloud_cover_pct,
                    "precipitation_mm": row.precipitation_mm,
                    "is_interpolated": bool(row.is_interpolated),
                },
            })
        return {
            "status": "available" if features else "degraded",
            "model": _run_payload(run),
            "valid_at": local_iso(target),
            "geojson": {"type": "FeatureCollection", "features": features},
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="暂时无法读取日照网格") from exc
