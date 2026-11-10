"""Generate static Pages artifacts from real provider model runs.

This module intentionally has no SQLAlchemy, Postgres, FastAPI or server runtime.
Model responses are never silently substituted with mock forecast data.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from sitegen.catalog import MODEL_CATALOG, get_model_spec
from sitegen.forecast import (
    CityHour,
    GridHour,
    aggregate_basin_hours,
    aggregate_daily,
    city_daily_summary,
    find_basin_sunshine_window,
    find_city_sunshine_window,
    local_iso,
)
from sitegen.geography import (
    download_usgs_boundary,
    generate_grid_cells,
    write_boundary_geojson,
    write_grid_geojson,
)
from sitegen.geonames import CITY_DEFINITIONS, download_city_catalog
from sitegen.open_meteo import OpenMeteoClient, WeatherLocation, parse_valid_time

LOG = logging.getLogger("zhuqing.sitegen")
DEFAULT_MODELS = tuple(MODEL_CATALOG)
GRID_HOURS = 72
CITY_HOURS = 168
EXPECTED_CITY_COUNT = len(CITY_DEFINITIONS)
MAX_GEOJSON_BYTES = 5_000_000


@dataclass(frozen=True)
class GeographySnapshot:
    grid_features: list[dict[str, Any]]
    cities: list[dict[str, Any]]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def empty_overview(now: datetime, message: str) -> dict[str, Any]:
    return {
        "status": "initializing",
        "region": "sichuan-basin",
        "timezone": "Asia/Shanghai",
        "generated_at": local_iso(now),
        "next_sunshine_window": None,
        "hourly": [],
        "daily_sunshine_hours": [],
        "coverage": None,
        "message": message,
        "model": None,
    }


def model_status(model_id: str) -> dict[str, Any]:
    spec = get_model_spec(model_id)
    return {
        "model_id": model_id,
        "model_name": spec.display_name,
        "status": "waiting",
        "model_run_at": None,
        "retrieved_at": None,
        "forecast_end_at": None,
        "locations_count": 0,
        "message": "尚未采集到该模型的有效预报",
    }


def bootstrap(output: Path, now: datetime, models: tuple[str, ...]) -> None:
    data_dir = output / "data"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    for model_id in models:
        write_json(
            data_dir / "overview" / f"{model_id}.json",
            empty_overview(now, "尚未采集到真实预报数据，请查看更新状态。"),
        )
        write_json(
            data_dir / "cities" / f"{model_id}.json",
            {"status": "initializing", "model": None, "cities": []},
        )
    write_json(
        data_dir / "consensus.json",
        {"status": "initializing", "generated_at": local_iso(now), "model_count": 0, "daily": [], "best_sunny_day": None},
    )
    write_json(
        data_dir / "status.json",
        {
            "status": "initializing",
            "provider": "open-meteo",
            "latest_model_run": None,
            "last_checked_at": local_iso(now),
            "message": "尚未完成第一次真实天气数据采集。",
            "models": [model_status(model_id) for model_id in models],
        },
    )
    write_json(
        data_dir / "geography" / "grid.geojson",
        {"type": "FeatureCollection", "features": []},
    )


def load_geography(cache: Path, output: Path) -> GeographySnapshot:
    geo_dir = cache / "geography"
    boundary_file = geo_dir / "sichuan_basin_boundary.geojson"
    grid_file = geo_dir / "grid_cells.geojson"
    cities_file = geo_dir / "cities.json"
    if not all(path.is_file() for path in (boundary_file, grid_file, cities_file)):
        LOG.info("Geography cache missing; downloading USGS and GeoNames sources")
        boundary, metadata = download_usgs_boundary(cache)
        cells = generate_grid_cells(boundary, 0.25)
        cities = download_city_catalog(geo_dir)
        if len(cities) != EXPECTED_CITY_COUNT or not cells:
            raise RuntimeError("Incomplete geography import; refusing to publish")
        write_boundary_geojson(boundary, metadata, boundary_file)
        write_grid_geojson(cells, grid_file)

    grid = json.loads(grid_file.read_text(encoding="utf-8"))
    cities = json.loads(cities_file.read_text(encoding="utf-8"))
    if grid.get("type") != "FeatureCollection":
        raise ValueError("Cached grid is not GeoJSON FeatureCollection")
    features = grid.get("features", [])
    if not features or not all(shape(feature["geometry"]).is_valid for feature in features):
        raise ValueError("Geography grid has invalid or empty geometries")
    if len(cities) != EXPECTED_CITY_COUNT or len({city["slug"] for city in cities}) != EXPECTED_CITY_COUNT:
        raise ValueError("Geography city catalogue is invalid")
    if grid_file.stat().st_size > MAX_GEOJSON_BYTES:
        raise ValueError("Geography grid file unexpectedly exceeds 5 MB")

    target = output / "data" / "geography"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(grid_file, target / "grid.geojson")
    shutil.copyfile(boundary_file, target / "boundary.geojson")
    write_json(target / "cities.json", cities)
    return GeographySnapshot(grid_features=features, cities=cities)


def _float(values: dict[str, Any], field: str, index: int) -> float | None:
    series = values.get(field)
    if not isinstance(series, list) or index >= len(series):
        return None
    value = series[index]
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _provider_row(hourly: dict[str, Any], index: int) -> dict[str, float | None]:
    sunshine = _float(hourly, "sunshine_duration", index)
    # Keep nulls as null; do not imply a sunny or cloudy hour when data is missing.
    is_day_value = _float(hourly, "is_day", index)
    return {
        "sunshine": sunshine,
        "cloud": _float(hourly, "cloud_cover", index),
        "low_cloud": _float(hourly, "cloud_cover_low", index),
        "mid_cloud": _float(hourly, "cloud_cover_mid", index),
        "high_cloud": _float(hourly, "cloud_cover_high", index),
        "rain": _float(hourly, "precipitation", index),
        "temp": _float(hourly, "temperature_2m", index),
        "humidity": _float(hourly, "relative_humidity_2m", index),
        "dew_point": _float(hourly, "dew_point_2m", index),
        "shortwave": _float(hourly, "shortwave_radiation", index),
        "weather_code": _float(hourly, "weather_code", index),
        "is_day": bool(is_day_value) if is_day_value is not None else None,
    }


def _utc_hour_end(value: datetime, now: datetime) -> bool:
    """A preceding-hour accumulation must cover a wholly future interval."""
    return value - timedelta(hours=1) >= now


def _timestamp_file(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%MZ") + ".json"


def produce_model(
    output: Path,
    client: OpenMeteoClient,
    model_id: str,
    geography: GeographySnapshot,
    now: datetime,
    *,
    forecast_days: int = 7,
    batch_size: int = 25,
) -> dict[str, Any]:
    spec = get_model_spec(model_id)
    metadata = client.fetch_metadata(model_id)
    run_at = metadata.model_run_at
    if run_at is None:
        raise ValueError(f"{model_id} has no published initialization timestamp")
    if metadata.available_at and now - metadata.available_at < timedelta(minutes=10):
        raise RuntimeError(f"{model_id} model run is still within provider consistency window")

    grid_features = geography.grid_features
    grid_keys = [feature["properties"]["location_key"] for feature in grid_features]
    locations = [
        WeatherLocation(
            location_id=index,
            location_key=feature["properties"]["location_key"],
            latitude=feature["properties"]["latitude"],
            longitude=feature["properties"]["longitude"],
        )
        for index, feature in enumerate(grid_features)
    ]
    locations += [
        WeatherLocation(
            location_id=len(grid_features) + index,
            location_key=f"city:{city['slug']}",
            latitude=float(city["latitude"]),
            longitude=float(city["longitude"]),
        )
        for index, city in enumerate(geography.cities)
    ]
    readings: dict[str, dict[datetime, dict[str, float | None]]] = {
        location.location_key: {} for location in locations
    }
    returned_locations = 0

    for offset in range(0, len(locations), batch_size):
        batch = locations[offset : offset + batch_size]
        results = client.fetch_forecast_batch(model_id, batch, run_at, forecast_days)
        if len(results) != len(batch):
            raise ValueError("Open-Meteo location batch count mismatch")
        for location, response in zip(batch, results, strict=True):
            series = response["hourly"]
            time_values = series["time"]
            sunshine_values = series["sunshine_duration"]
            if len(time_values) != len(sunshine_values):
                raise ValueError("sunshine_duration and time series lengths differ")
            for index, stamp in enumerate(time_values):
                valid_at = parse_valid_time(stamp)
                if _utc_hour_end(valid_at, now):
                    readings[location.location_key][valid_at] = _provider_row(series, index)
            returned_locations += 1

    # Retain the complete 7-day horizon for daily totals. Only the first
    # 72 hours require the larger per-grid map slice files.
    all_grid_times = sorted(
        {stamp for key in grid_keys for stamp in readings[key]}
    )[:CITY_HOURS]
    grid_times = all_grid_times[:GRID_HOURS]
    if len(grid_times) < 2:
        raise ValueError(f"{model_id} does not contain at least two future forecast hours")
    if not any(
        readings[key].get(stamp, {}).get("sunshine") is not None
        for key in grid_keys for stamp in grid_times
    ):
        raise ValueError(f"{model_id} has no non-null sunshine duration values")

    basin_samples: list[GridHour] = []
    grid_dir = output / "data" / "grid" / model_id
    for valid_at in all_grid_times:
        values: list[list[float | int | None]] = []
        for feature in grid_features:
            key = feature["properties"]["location_key"]
            row = readings[key].get(valid_at, {})
            lead_hours = (valid_at - run_at).total_seconds() / 3600
            interpolated = spec.native_step_seconds(max(0, lead_hours)) > 3600
            area = float(feature["properties"]["area_km2"])
            sunshine = row.get("sunshine")
            basin_samples.append(
                GridHour(
                    valid_at=valid_at,
                    area_km2=area,
                    sunshine_seconds=sunshine,
                    cloud_cover_pct=row.get("cloud"),
                    precipitation_mm=row.get("rain"),
                    is_interpolated=interpolated,
                    low_cloud_cover_pct=row.get("low_cloud"),
                    mid_cloud_cover_pct=row.get("mid_cloud"),
                    high_cloud_cover_pct=row.get("high_cloud"),
                    relative_humidity_pct=row.get("humidity"),
                    shortwave_radiation_wm2=row.get("shortwave"),
                    is_day=row.get("is_day"),
                )
            )
            if valid_at in grid_times:
                values.append([
                    round(sunshine / 60, 1) if sunshine is not None else None,
                    round(row["cloud"], 1) if row.get("cloud") is not None else None,
                    round(row["rain"], 2) if row.get("rain") is not None else None,
                    int(interpolated),
                    round(row["low_cloud"], 1) if row.get("low_cloud") is not None else None,
                    round(row["mid_cloud"], 1) if row.get("mid_cloud") is not None else None,
                    round(row["high_cloud"], 1) if row.get("high_cloud") is not None else None,
                    round(row["humidity"], 1) if row.get("humidity") is not None else None,
                    round(row["shortwave"], 1) if row.get("shortwave") is not None else None,
                ])
        if valid_at in grid_times:
            write_json(
                grid_dir / _timestamp_file(valid_at),
                {"valid_at": local_iso(valid_at), "values": values},
            )

    basin_hourly = aggregate_basin_hours(basin_samples)
    for hour, stamp in zip(basin_hourly[:GRID_HOURS], grid_times, strict=True):
        hour["grid_file"] = f"grid/{model_id}/{_timestamp_file(stamp)}"

    basin_window = find_basin_sunshine_window(basin_hourly[:GRID_HOURS])
    if basin_window:
        basin_window["source_model"] = spec.display_name

    retrieved_at = datetime.now(UTC)
    source = {
        "model_id": model_id,
        "model_name": spec.display_name,
        "model_run_at": local_iso(run_at),
        "retrieved_at": local_iso(retrieved_at),
        "available_at": local_iso(metadata.available_at),
        "forecast_end_at": local_iso(max(all_grid_times)),
        "spatial_resolution_km": spec.spatial_resolution_km,
        "source": "Open-Meteo ECMWF Single Runs API",
        "source_url": "https://open-meteo.com/en/docs/single-runs-api",
        "license": "CC BY 4.0",
        "request_metadata": {
            "models": model_id,
            "run": run_at.strftime("%Y-%m-%dT%H:%M"),
            "hourly_variables": list(spec.hourly_variables),
            "timezone": "UTC",
            "forecast_days": forecast_days,
            "interval_semantics": "preceding_hour_timestamp_is_end",
            "native_step_schedule": [
                {"max_lead_hours": lead, "seconds": seconds}
                for lead, seconds in spec.native_steps
            ],
        },
    }
    overview = {
        "status": "available",
        "region": "sichuan-basin",
        "timezone": "Asia/Shanghai",
        "generated_at": local_iso(retrieved_at),
        "next_sunshine_window": basin_window,
        "hourly": basin_hourly[:GRID_HOURS],
        "daily_sunshine_hours": aggregate_daily(basin_hourly)[:7],
        "coverage": basin_hourly[0]["sunshine_coverage_pct"],
        "message": "数值天气模型预报；日照时长按盆地网格实际面积加权，不代表地面实况。",
        "model": source,
    }
    write_json(output / "data" / "overview" / f"{model_id}.json", overview)

    city_results = []
    for city in geography.cities:
        slug = str(city["slug"])
        rows = readings[f"city:{slug}"]
        city_times = sorted(rows)[:CITY_HOURS]
        city_samples: list[CityHour] = []
        for valid_at in city_times:
            item = rows[valid_at]
            lead_hours = (valid_at - run_at).total_seconds() / 3600
            city_samples.append(
                CityHour(
                    valid_at=valid_at,
                    sunshine_seconds=item.get("sunshine"),
                    cloud_cover_pct=item.get("cloud"),
                    precipitation_mm=item.get("rain"),
                    temperature_c=item.get("temp"),
                    is_interpolated=spec.native_step_seconds(max(0, lead_hours)) > 3600,
                    low_cloud_cover_pct=item.get("low_cloud"),
                    mid_cloud_cover_pct=item.get("mid_cloud"),
                    high_cloud_cover_pct=item.get("high_cloud"),
                    relative_humidity_pct=item.get("humidity"),
                    dew_point_c=item.get("dew_point"),
                    shortwave_radiation_wm2=item.get("shortwave"),
                    weather_code=item.get("weather_code"),
                    is_day=item.get("is_day"),
                )
            )
        city_window = find_city_sunshine_window(city_samples)
        daily = city_daily_summary(city_samples)[:7]
        public_city = {
            "slug": slug,
            "name": city["name_zh"],
            "latitude": city["latitude"],
            "longitude": city["longitude"],
            "next_sunshine_window": city_window,
            "daily": daily,
            "status": "available" if any(x.sunshine_seconds is not None for x in city_samples) else "pending",
        }
        city_results.append(public_city)
        write_json(
            output / "data" / "city" / model_id / f"{slug}.json",
            {
                "status": public_city["status"],
                "city": {
                    **public_city,
                    "hourly": [
                        {
                            "valid_at": local_iso(row.valid_at),
                            "sunshine_minutes": (
                                round(row.sunshine_seconds / 60, 1)
                                if row.sunshine_seconds is not None else None
                            ),
                            "cloud_cover_pct": row.cloud_cover_pct,
                            "precipitation_mm": row.precipitation_mm,
                            "temperature_c": row.temperature_c,
                            "low_cloud_cover_pct": row.low_cloud_cover_pct,
                            "mid_cloud_cover_pct": row.mid_cloud_cover_pct,
                            "high_cloud_cover_pct": row.high_cloud_cover_pct,
                            "relative_humidity_pct": row.relative_humidity_pct,
                            "dew_point_c": row.dew_point_c,
                            "shortwave_radiation_wm2": row.shortwave_radiation_wm2,
                            "weather_code": row.weather_code,
                            "is_day": row.is_day,
                            "is_interpolated": row.is_interpolated,
                        }
                        for row in city_samples
                    ],
                },
                "model": source,
            },
        )

    write_json(
        output / "data" / "cities" / f"{model_id}.json",
        {"status": "available", "model": source, "cities": city_results},
    )
    return {
        "model_id": model_id,
        "model_name": spec.display_name,
        "status": "available",
        "model_run_at": local_iso(run_at),
        "retrieved_at": local_iso(retrieved_at),
        "forecast_end_at": local_iso(max(all_grid_times)),
        "locations_count": returned_locations,
        "message": "模型数据已采集",
    }


def generate(
    output: Path,
    cache: Path,
    models: tuple[str, ...] = DEFAULT_MODELS,
    *,
    mode: str = "live",
    client: OpenMeteoClient | None = None,
    now: datetime | None = None,
    geography: GeographySnapshot | None = None,
    batch_size: int = 25,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    bootstrap(output, now, models)
    if mode == "placeholder":
        LOG.info("Created an explicit empty-data site shell (no simulated forecasts)")
        return json.loads((output / "data" / "status.json").read_text(encoding="utf-8"))
    if mode != "live":
        raise ValueError("mode must be live or placeholder")

    geography = geography or load_geography(cache, output)
    # Store geometry only once, separate from every per-hour values snapshot.
    write_json(
        output / "data" / "geography" / "grid.geojson",
        {"type": "FeatureCollection", "features": geography.grid_features},
    )

    usage = os.getenv("OPEN_METEO_USAGE", "non_commercial")
    if usage not in {"commercial", "non_commercial"}:
        raise ValueError("OPEN_METEO_USAGE must be commercial or non_commercial")
    key = os.getenv("OPEN_METEO_API_KEY")
    if usage == "commercial" and not key:
        raise ValueError("Commercial usage requires OPEN_METEO_API_KEY")
    metadata_base = (
        "https://customer-api.open-meteo.com" if usage == "commercial"
        else "https://api.open-meteo.com"
    )
    single_base = (
        "https://customer-single-runs-api.open-meteo.com" if usage == "commercial"
        else "https://single-runs-api.open-meteo.com"
    )
    own_client = client is None
    client = client or OpenMeteoClient(
        base_url=metadata_base,
        single_runs_base_url=single_base,
        api_key=key,
        timeout_seconds=45,
        max_attempts=5,
    )
    statuses = []
    try:
        for model_id in models:
            try:
                statuses.append(
                    produce_model(
                        output=output,
                        client=client,
                        model_id=model_id,
                        geography=geography,
                        now=now,
                        batch_size=batch_size,
                    )
                )
            except Exception:
                # Per-model isolation: failure cannot publish partial grid results.
                LOG.exception("Forecast ingest failed for %s", model_id)
                shutil.rmtree(output / "data" / "grid" / model_id, ignore_errors=True)
                shutil.rmtree(output / "data" / "city" / model_id, ignore_errors=True)
                write_json(
                    output / "data" / "overview" / f"{model_id}.json",
                    empty_overview(now, "该模型预报暂时不可用，请查看自动更新状态。"),
                )
                write_json(
                    output / "data" / "cities" / f"{model_id}.json",
                    {"status": "initializing", "model": None, "cities": []},
                )
                fallback = model_status(model_id)
                fallback["message"] = "模型采集失败，等待下一次自动更新"
                statuses.append(fallback)
    finally:
        if own_client:
            client.close()
    available = [row for row in statuses if row["status"] == "available"]
    if not available:
        state = "initializing"
        message = "本轮天气模型均未成功采集。网站暂不展示预测数值。"
    elif len(available) != len(statuses):
        state = "degraded"
        message = "部分模型暂不可用，仅展示成功采集的模型。"
    else:
        state = "available"
        message = "所有已配置模型预报快照已更新。"
    status = {
        "status": state,
        "provider": "open-meteo",
        "latest_model_run": max(
            (row["model_run_at"] for row in available if row["model_run_at"]),
            default=None,
        ),
        "last_checked_at": local_iso(datetime.now(UTC)),
        "message": message,
        "models": statuses,
    }
    write_json(output / "data" / "status.json", status)
    from sitegen.consensus import build_consensus
    build_consensus(output, statuses, local_iso(datetime.now(UTC)))
    LOG.info(
        "Static data published: %s, %s grid cells, %s cities, %s active model(s)",
        state,
        len(geography.grid_features),
        len(geography.cities),
        len(available),
    )
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real, database-free sunshine snapshots")
    parser.add_argument("--output", type=Path, default=Path("apps/web/public"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/zhuqing"))
    parser.add_argument("--mode", choices=("live", "placeholder"), default="live")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument(
        "--require-live", action="store_true",
        help="Exit nonzero when every model fails, preventing stale/empty deployment",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    models = tuple(model.strip() for model in args.models.split(",") if model.strip())
    if not models:
        parser.error("At least one weather model is required")
    for model in models:
        get_model_spec(model)
    result = generate(
        args.output, args.cache_dir, models,
        mode=args.mode,
        batch_size=max(1, min(50, args.batch_size)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_live and not any(
        model["status"] == "available" for model in result["models"]
    ):
        raise SystemExit("No live models available; refusing to replace last good Pages site")


if __name__ == "__main__":
    main()
