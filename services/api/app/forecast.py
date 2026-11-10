from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

BASIN_TIMEZONE = ZoneInfo("Asia/Shanghai")
SUNNY_HOUR_SECONDS = 1_800
BASIN_SUNNY_COVERAGE_PCT = 50.0
MIN_DATA_COMPLETENESS_PCT = 80.0
MIN_WINDOW_HOURS = 2

MODEL_NAMES = {
    "ecmwf_ifs": "ECMWF IFS HRES 9 km",
    "ecmwf_ifs025": "ECMWF IFS Open Data 0.25°",
    "ecmwf_aifs025_single": "ECMWF AIFS 0.25° Single",
}


@dataclass(frozen=True)
class GridHour:
    valid_at: datetime
    area_km2: float
    sunshine_seconds: float | None
    cloud_cover_pct: float | None
    precipitation_mm: float | None
    is_interpolated: bool


@dataclass(frozen=True)
class CityHour:
    valid_at: datetime
    sunshine_seconds: float | None
    cloud_cover_pct: float | None
    precipitation_mm: float | None
    temperature_c: float | None
    is_interpolated: bool


def local_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BASIN_TIMEZONE).isoformat()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def aggregate_basin_hours(samples: list[GridHour]) -> list[dict[str, Any]]:
    grouped: dict[datetime, list[GridHour]] = defaultdict(list)
    for sample in samples:
        grouped[_as_utc(sample.valid_at)].append(sample)

    result: list[dict[str, Any]] = []
    for valid_at, rows in sorted(grouped.items()):
        total_area = sum(max(0.0, row.area_km2) for row in rows)
        valid = [row for row in rows if row.sunshine_seconds is not None]
        valid_area = sum(max(0.0, row.area_km2) for row in valid)
        completeness = valid_area / total_area * 100 if total_area else 0.0
        if not valid_area:
            result.append({
                "valid_at": local_iso(valid_at),
                "sunshine_minutes": None,
                "sunshine_coverage_pct": None,
                "data_completeness_pct": round(completeness, 1),
                "cloud_cover_pct": None,
                "precipitation_mm": None,
                "interpolated_area_pct": None,
            })
            continue

        sunny_area = sum(
            row.area_km2 for row in valid if row.sunshine_seconds >= SUNNY_HOUR_SECONDS
        )
        sunshine_minutes = sum(
            row.area_km2 * row.sunshine_seconds / 60 for row in valid
        ) / valid_area
        cloud_rows = [row for row in valid if row.cloud_cover_pct is not None]
        cloud_area = sum(row.area_km2 for row in cloud_rows)
        cloud_cover = (
            sum(row.area_km2 * row.cloud_cover_pct for row in cloud_rows) / cloud_area
            if cloud_area else None
        )
        rain_rows = [row for row in valid if row.precipitation_mm is not None]
        rain_area = sum(row.area_km2 for row in rain_rows)
        precipitation = (
            sum(row.area_km2 * row.precipitation_mm for row in rain_rows) / rain_area
            if rain_area else None
        )
        interpolated_area = sum(row.area_km2 for row in valid if row.is_interpolated)
        result.append({
            "valid_at": local_iso(valid_at),
            "sunshine_minutes": round(sunshine_minutes, 1),
            "sunshine_coverage_pct": round(sunny_area / valid_area * 100, 1),
            "data_completeness_pct": round(completeness, 1),
            "cloud_cover_pct": round(cloud_cover, 1) if cloud_cover is not None else None,
            "precipitation_mm": round(precipitation, 2) if precipitation is not None else None,
            "interpolated_area_pct": round(interpolated_area / valid_area * 100, 1),
        })
    return result


def aggregate_daily(hours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for hour in hours:
        if not hour.get("valid_at"):
            continue
        local_time = datetime.fromisoformat(hour["valid_at"])
        grouped[local_time.date()].append(hour)

    daily: list[dict[str, Any]] = []
    for day, rows in sorted(grouped.items()):
        valid = [
            row for row in rows
            if row["sunshine_minutes"] is not None
            and row.get("data_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT
        ]
        sunshine_hours = sum(row["sunshine_minutes"] for row in valid) / 60
        coverage_values = [row["sunshine_coverage_pct"] for row in valid if row["sunshine_coverage_pct"] is not None]
        completeness_values = [row["data_completeness_pct"] for row in rows]
        mean_coverage = sum(coverage_values) / len(coverage_values) if coverage_values else None
        if sunshine_hours >= 5:
            status = "high"
        elif sunshine_hours >= 2:
            status = "moderate"
        elif sunshine_hours > 0:
            status = "low"
        else:
            status = "low"
        daily.append({
            "date": day.isoformat(),
            "sunshine_hours": round(sunshine_hours, 1) if valid else None,
            "mean_sunshine_coverage_pct": round(mean_coverage, 1) if mean_coverage is not None else None,
            "data_completeness_pct": round(sum(completeness_values) / len(completeness_values), 1) if completeness_values else 0,
            "status": status if valid else "pending",
        })
    return daily


def find_basin_sunshine_window(hours: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row for row in hours
        if row.get("sunshine_coverage_pct") is not None
        and row["sunshine_coverage_pct"] >= BASIN_SUNNY_COVERAGE_PCT
        and row.get("data_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT
    ]
    candidates.sort(key=lambda row: row["valid_at"])
    streak: list[dict[str, Any]] = []

    def build_window(rows: list[dict[str, Any]]) -> dict[str, Any]:
        last_time = datetime.fromisoformat(rows[-1]["valid_at"])
        return {
            "starts_at": rows[0]["valid_at"],
            "ends_at": (last_time + timedelta(hours=1)).isoformat(),
            "expected_sunshine_minutes": round(
                sum(item["sunshine_minutes"] or 0 for item in rows), 1
            ),
            "coverage_pct": round(
                sum(item["sunshine_coverage_pct"] for item in rows) / len(rows), 1
            ),
            "source_model": None,
            "basis": "连续至少 2 个小时，盆地有效日照覆盖率达到 50%",
        }

    for row in candidates:
        current = datetime.fromisoformat(row["valid_at"])
        previous = datetime.fromisoformat(streak[-1]["valid_at"]) if streak else None
        if previous is not None and current - previous != timedelta(hours=1):
            if len(streak) >= MIN_WINDOW_HOURS:
                return build_window(streak)
            streak = []
        streak.append(row)

    return build_window(streak) if len(streak) >= MIN_WINDOW_HOURS else None


def find_city_sunshine_window(samples: list[CityHour]) -> dict[str, Any] | None:
    rows = sorted(samples, key=lambda row: _as_utc(row.valid_at))
    streak: list[CityHour] = []

    def build_window(items: list[CityHour]) -> dict[str, Any]:
        return {
            "starts_at": local_iso(items[0].valid_at),
            "ends_at": local_iso(_as_utc(items[-1].valid_at) + timedelta(hours=1)),
            "expected_sunshine_minutes": round(
                sum(item.sunshine_seconds or 0 for item in items) / 60, 1
            ),
            "basis": "连续至少 2 个小时，每小时预计有效日照不少于 30 分钟",
        }

    for row in rows:
        current = _as_utc(row.valid_at)
        previous = _as_utc(streak[-1].valid_at) if streak else None
        sunny = row.sunshine_seconds is not None and row.sunshine_seconds >= SUNNY_HOUR_SECONDS
        if not sunny or (previous is not None and current - previous != timedelta(hours=1)):
            if len(streak) >= MIN_WINDOW_HOURS:
                return build_window(streak)
            streak = []
        if sunny:
            streak.append(row)

    return build_window(streak) if len(streak) >= MIN_WINDOW_HOURS else None


def city_daily_summary(samples: list[CityHour]) -> list[dict[str, Any]]:
    grouped: dict[date, list[CityHour]] = defaultdict(list)
    for row in samples:
        grouped[_as_utc(row.valid_at).astimezone(BASIN_TIMEZONE).date()].append(row)
    result: list[dict[str, Any]] = []
    for day, rows in sorted(grouped.items()):
        values = [row.sunshine_seconds for row in rows if row.sunshine_seconds is not None]
        result.append({
            "date": day.isoformat(),
            "sunshine_hours": round(sum(values) / 3600, 1) if values else None,
            "max_cloud_cover_pct": max(
                (row.cloud_cover_pct for row in rows if row.cloud_cover_pct is not None),
                default=None,
            ),
            "status": "pending" if not values else (
                "high" if sum(values) / 3600 >= 5 else "moderate" if sum(values) / 3600 >= 2 else "low"
            ),
        })
    return result
