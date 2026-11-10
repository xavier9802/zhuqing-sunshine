from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from sqlalchemy import select

from app.catalog import get_model_spec
from app.models import (
    ForecastHourly,
    ForecastLocation,
    ForecastRun,
    ForecastRunLocation,
    RawForecastPayload,
)
from app.providers.open_meteo import (
    OpenMeteoClient,
    WeatherLocation,
    parse_valid_time,
    response_items,
)


OPEN_METEO_ECMWF_URL = "https://open-meteo.com/en/docs/ecmwf-api"


def _float_at(values: dict[str, Any], key: str, index: int) -> float | None:
    array = values.get(key)
    if not isinstance(array, list) or index >= len(array):
        return None
    value = array[index]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_forecast_locations(session_factory) -> list[WeatherLocation]:
    with session_factory() as session:
        rows = session.scalars(
            select(ForecastLocation).order_by(ForecastLocation.location_key)
        ).all()
        return [
            WeatherLocation(
                location_id=row.id,
                location_key=row.location_key,
                latitude=row.latitude,
                longitude=row.longitude,
            )
            for row in rows
        ]


def _persist_batch(
    session_factory,
    run: ForecastRun,
    batch_no: int,
    locations: list[WeatherLocation],
    response: Any,
    model_run_at: datetime | None,
    spec,
    request_metadata: dict[str, Any],
) -> tuple[datetime | None, datetime | None]:
    items = response_items(response)
    if len(items) != len(locations):
        raise ValueError("Provider response count does not match requested locations")

    starts: list[datetime] = []
    ends: list[datetime] = []
    received_at = datetime.now(UTC)

    with session_factory() as session:
        session.add(
            RawForecastPayload(
                run_id=run.id,
                batch_no=batch_no,
                location_keys=[item.location_key for item in locations],
                request_params=request_metadata,
                response_sha256=_sha256(response),
                response_payload=response,
                received_at=received_at,
            )
        )

        for location, item in zip(locations, items, strict=True):
            hourly = item["hourly"]
            times = hourly.get("time", [])
            units = item.get("hourly_units", {})
            session.add(
                ForecastRunLocation(
                    run_id=run.id,
                    location_id=location.location_id,
                    resolved_latitude=_as_float(item.get("latitude")),
                    resolved_longitude=_as_float(item.get("longitude")),
                    elevation_m=_as_float(item.get("elevation")),
                    timezone=item.get("timezone"),
                    utc_offset_seconds=_as_int(item.get("utc_offset_seconds")),
                )
            )

            for index, timestamp in enumerate(times):
                valid_at = parse_valid_time(timestamp)
                starts.append(valid_at)
                ends.append(valid_at)
                lead_hours = (
                    (valid_at - model_run_at).total_seconds() / 3600
                    if model_run_at is not None
                    else None
                )
                native_step = (
                    spec.native_step_seconds(max(0.0, lead_hours))
                    if lead_hours is not None
                    else None
                )
                session.add(
                    ForecastHourly(
                        run_id=run.id,
                        location_id=location.location_id,
                        valid_at=valid_at,
                        lead_hours=lead_hours,
                        native_step_seconds=native_step,
                        is_interpolated=(native_step > 3600) if native_step else None,
                        sunshine_duration_seconds=_float_at(hourly, "sunshine_duration", index),
                        shortwave_radiation_wm2=_float_at(hourly, "shortwave_radiation", index),
                        direct_normal_irradiance_wm2=_float_at(hourly, "direct_normal_irradiance", index),
                        cloud_cover_pct=_float_at(hourly, "cloud_cover", index),
                        precipitation_mm=_float_at(hourly, "precipitation", index),
                        temperature_2m_c=_float_at(hourly, "temperature_2m", index),
                        relative_humidity_2m_pct=_float_at(hourly, "relative_humidity_2m", index),
                        dew_point_2m_c=_float_at(hourly, "dew_point_2m", index),
                        wind_speed_10m_kmh=_float_at(hourly, "wind_speed_10m", index),
                        wind_direction_10m_deg=_float_at(hourly, "wind_direction_10m", index),
                        visibility_m=_float_at(hourly, "visibility", index),
                    )
                )
        session.commit()

    return (min(starts) if starts else None, max(ends) if ends else None)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def ingest_model(
    session_factory,
    client: OpenMeteoClient,
    model_id: str,
    locations: list[WeatherLocation],
    forecast_days: int,
    batch_size: int,
) -> dict[str, Any]:
    spec = get_model_spec(model_id)
    if not locations:
        raise ValueError("No forecast locations found. Run import-geography first.")

    metadata = client.fetch_metadata(model_id)
    retrieved_at = datetime.now(UTC)
    request_metadata = {
        "forecast_days": forecast_days,
        "timezone": "UTC",
        "cell_selection": "land",
        "hourly_variables": list(spec.hourly_variables),
        "models": model_id,
        "dni_method": spec.dni_method,
    }

    with session_factory() as session:
        run = ForecastRun(
            provider="open-meteo",
            model_id=model_id,
            model_name=spec.display_name,
            model_run_at=metadata.model_run_at,
            retrieved_at=retrieved_at,
            available_at=metadata.available_at,
            modified_at=metadata.modified_at,
            data_end_time=metadata.data_end_time,
            temporal_resolution_seconds=metadata.temporal_resolution_seconds,
            update_interval_seconds=metadata.update_interval_seconds,
            spatial_resolution_km=spec.spatial_resolution_km,
            forecast_days=forecast_days,
            status="running",
            source_url=OPEN_METEO_ECMWF_URL,
            source_license="CC BY 4.0",
            source_metadata={
                **metadata.raw,
                "dni_method": spec.dni_method,
                "native_step_schedule": [
                    {"max_lead_hours": end, "step_seconds": seconds}
                    for end, seconds in spec.native_steps
                ],
            },
            request_metadata=request_metadata,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    start_at: datetime | None = None
    end_at: datetime | None = None
    batch_count = 0

    try:
        for batch_no, offset in enumerate(range(0, len(locations), batch_size), start=1):
            batch = locations[offset : offset + batch_size]
            response = client.fetch_forecast_batch(
                model_id=model_id,
                locations=batch,
                forecast_days=forecast_days,
            )
            batch_start, batch_end = _persist_batch(
                session_factory=session_factory,
                run=run,
                batch_no=batch_no,
                locations=batch,
                response=response,
                model_run_at=metadata.model_run_at,
                spec=spec,
                request_metadata=request_metadata,
            )
            if batch_start and (start_at is None or batch_start < start_at):
                start_at = batch_start
            if batch_end and (end_at is None or batch_end > end_at):
                end_at = batch_end
            batch_count += 1

        with session_factory() as session:
            stored_run = session.get(ForecastRun, run_id)
            stored_run.status = "complete"
            stored_run.forecast_start_at = start_at
            stored_run.forecast_end_at = end_at
            session.commit()
    except Exception as exc:
        with session_factory() as session:
            stored_run = session.get(ForecastRun, run_id)
            if stored_run:
                stored_run.status = "failed"
                stored_run.error_message = str(exc)[:4000]
                session.commit()
        raise

    return {
        "run_id": str(run_id),
        "model_id": model_id,
        "status": "complete",
        "locations": len(locations),
        "batches": batch_count,
        "forecast_start_at": start_at.isoformat() if start_at else None,
        "forecast_end_at": end_at.isoformat() if end_at else None,
    }


def ingest_all(
    session_factory,
    client: OpenMeteoClient,
    model_ids: tuple[str, ...],
    forecast_days: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    locations = load_forecast_locations(session_factory)
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for model_id in model_ids:
        try:
            results.append(
                ingest_model(
                    session_factory,
                    client,
                    model_id,
                    locations,
                    forecast_days,
                    batch_size,
                )
            )
        except Exception as exc:
            errors.append(f"{model_id}: {exc}")

    if errors:
        raise RuntimeError(
            "One or more model ingestions failed. Successful runs were retained. "
            + " | ".join(errors)
        )
    return results
