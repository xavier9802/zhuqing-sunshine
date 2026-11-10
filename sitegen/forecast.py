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
MIN_WINDOW_HOURS = 3
RAIN_HOURLY_MM = 0.1

# Transparent, rule-based display thresholds. These are not calibrated
# probabilities and must be revised only after station verification.
CLEAR_TOTAL_CLOUD_MAX = 30.0
CLEAR_LOW_CLOUD_MAX = 25.0
BRIGHT_TOTAL_CLOUD_MAX = 85.0
BRIGHT_LOW_CLOUD_MAX = 50.0

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
    low_cloud_cover_pct: float | None = None
    mid_cloud_cover_pct: float | None = None
    high_cloud_cover_pct: float | None = None
    relative_humidity_pct: float | None = None
    shortwave_radiation_wm2: float | None = None
    visibility_m: float | None = None
    is_day: bool | None = None


@dataclass(frozen=True)
class CityHour:
    valid_at: datetime
    sunshine_seconds: float | None
    cloud_cover_pct: float | None
    precipitation_mm: float | None
    temperature_c: float | None
    is_interpolated: bool
    low_cloud_cover_pct: float | None = None
    mid_cloud_cover_pct: float | None = None
    high_cloud_cover_pct: float | None = None
    relative_humidity_pct: float | None = None
    dew_point_c: float | None = None
    shortwave_radiation_wm2: float | None = None
    visibility_m: float | None = None
    weather_code: float | None = None
    is_day: bool | None = None


def local_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(BASIN_TIMEZONE).isoformat()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _weighted_mean(rows: list[GridHour], field: str) -> float | None:
    valid = [row for row in rows if getattr(row, field) is not None and row.area_km2 > 0]
    area = sum(row.area_km2 for row in valid)
    if not area:
        return None
    return sum(row.area_km2 * float(getattr(row, field)) for row in valid) / area


def _coverage_pct(rows: list[GridHour], predicate) -> float | None:
    valid = [row for row in rows if row.area_km2 > 0 and row.sunshine_seconds is not None]
    area = sum(row.area_km2 for row in valid)
    if not area:
        return None
    return sum(row.area_km2 for row in valid if predicate(row)) / area * 100


def aggregate_basin_hours(samples: list[GridHour]) -> list[dict[str, Any]]:
    grouped: dict[datetime, list[GridHour]] = defaultdict(list)
    for sample in samples:
        grouped[_as_utc(sample.valid_at)].append(sample)

    result: list[dict[str, Any]] = []
    for valid_at, rows in sorted(grouped.items()):
        total_area = sum(max(0.0, row.area_km2) for row in rows)
        valid = [row for row in rows if row.sunshine_seconds is not None and row.area_km2 > 0]
        valid_area = sum(row.area_km2 for row in valid)
        completeness = valid_area / total_area * 100 if total_area else 0.0
        condition_valid = [
            row for row in rows
            if row.cloud_cover_pct is not None
            and row.low_cloud_cover_pct is not None
            and row.precipitation_mm is not None
            and row.area_km2 > 0
        ]
        diagnostic_area = sum(row.area_km2 for row in condition_valid)
        rain_valid = [row for row in rows if row.precipitation_mm is not None and row.area_km2 > 0]
        rain_area = sum(row.area_km2 for row in rain_valid)

        if not valid_area:
            result.append({
                "valid_at": local_iso(valid_at),
                "sunshine_minutes": None,
                "sunshine_coverage_pct": None,
                "clear_sky_coverage_pct": None,
                "bright_sky_coverage_pct": None,
                "rain_coverage_pct": None,
                "data_completeness_pct": round(completeness, 1),
                "cloud_diagnostic_completeness_pct": round(diagnostic_area / total_area * 100, 1) if total_area else 0,
                "cloud_cover_pct": None,
                "low_cloud_cover_pct": None,
                "mid_cloud_cover_pct": None,
                "high_cloud_cover_pct": None,
                "relative_humidity_pct": None,
                "precipitation_mm": None,
                "shortwave_radiation_wm2": None,
                "interpolated_area_pct": None,
            })
            continue

        sunshine_minutes = sum(row.area_km2 * row.sunshine_seconds / 60 for row in valid) / valid_area
        sunny_area = sum(row.area_km2 for row in valid if row.sunshine_seconds >= SUNNY_HOUR_SECONDS)
        # Low cloud is a stronger discriminator of gloomy basin weather than
        # raw sunshine-duration alone. Missing diagnostics never count as clear.
        clear_rows = [
            row for row in valid
            if row.cloud_cover_pct is not None
            and row.low_cloud_cover_pct is not None
            and row.precipitation_mm is not None
            and row.sunshine_seconds >= SUNNY_HOUR_SECONDS
            and row.cloud_cover_pct <= CLEAR_TOTAL_CLOUD_MAX
            and row.low_cloud_cover_pct <= CLEAR_LOW_CLOUD_MAX
            and row.precipitation_mm < RAIN_HOURLY_MM
        ]
        bright_rows = [
            row for row in valid
            if row.cloud_cover_pct is not None
            and row.low_cloud_cover_pct is not None
            and row.precipitation_mm is not None
            and row.sunshine_seconds >= SUNNY_HOUR_SECONDS
            and row.low_cloud_cover_pct <= BRIGHT_LOW_CLOUD_MAX
            and row.precipitation_mm < RAIN_HOURLY_MM
        ]
        clear_area = sum(row.area_km2 for row in clear_rows)
        bright_area = sum(row.area_km2 for row in bright_rows)
        rainy_area = sum(row.area_km2 for row in rain_valid if row.precipitation_mm >= RAIN_HOURLY_MM)
        visibility_valid = [row for row in rows if row.visibility_m is not None and row.area_km2 > 0]
        visibility_area = sum(row.area_km2 for row in visibility_valid)
        low_visibility_area = sum(row.area_km2 for row in visibility_valid if row.visibility_m < 1000)
        interpolated_area = sum(row.area_km2 for row in valid if row.is_interpolated)
        result.append({
            "valid_at": local_iso(valid_at),
            "sunshine_minutes": round(sunshine_minutes, 1),
            "sunshine_coverage_pct": round(sunny_area / valid_area * 100, 1),
            "clear_sky_coverage_pct": round(clear_area / valid_area * 100, 1),
            "bright_sky_coverage_pct": round(bright_area / valid_area * 100, 1),
            "rain_coverage_pct": round(rainy_area / rain_area * 100, 1) if rain_area else 0.0,
            "data_completeness_pct": round(completeness, 1),
            "cloud_diagnostic_completeness_pct": round(diagnostic_area / total_area * 100, 1) if total_area else 0,
            "cloud_cover_pct": round(_weighted_mean(rows, "cloud_cover_pct"), 1) if _weighted_mean(rows, "cloud_cover_pct") is not None else None,
            "low_cloud_cover_pct": round(_weighted_mean(rows, "low_cloud_cover_pct"), 1) if _weighted_mean(rows, "low_cloud_cover_pct") is not None else None,
            "mid_cloud_cover_pct": round(_weighted_mean(rows, "mid_cloud_cover_pct"), 1) if _weighted_mean(rows, "mid_cloud_cover_pct") is not None else None,
            "high_cloud_cover_pct": round(_weighted_mean(rows, "high_cloud_cover_pct"), 1) if _weighted_mean(rows, "high_cloud_cover_pct") is not None else None,
            "relative_humidity_pct": round(_weighted_mean(rows, "relative_humidity_pct"), 1) if _weighted_mean(rows, "relative_humidity_pct") is not None else None,
            "precipitation_mm": round(_weighted_mean(rows, "precipitation_mm"), 2) if _weighted_mean(rows, "precipitation_mm") is not None else None,
            "shortwave_radiation_wm2": round(_weighted_mean(rows, "shortwave_radiation_wm2"), 1) if _weighted_mean(rows, "shortwave_radiation_wm2") is not None else None,
            "visibility_m": round(_weighted_mean(rows, "visibility_m"), 0) if _weighted_mean(rows, "visibility_m") is not None else None,
            "visibility_completeness_pct": round(visibility_area / total_area * 100, 1) if total_area else 0,
            "low_visibility_coverage_pct": round(low_visibility_area / visibility_area * 100, 1) if visibility_area else None,
            "interpolated_area_pct": round(interpolated_area / valid_area * 100, 1),
        })
    return result


def _daylight_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # is_day is supplied as an astronomical flag by Open-Meteo. Legacy/test
    # fixtures without it remain usable; production snapshots always request it.
    flags = [row.get("is_day") for row in rows]
    if any(flag is not None for flag in flags):
        return [row for row in rows if row.get("is_day") is True]
    return rows


def _classify_day(
    *,
    sunshine_hours: float | None,
    mean_cloud: float | None,
    mean_low_cloud: float | None,
    clear_hours: int,
    bright_hours: int,
    rain_hours: int,
) -> str:
    if rain_hours >= 2:
        return "rainy"
    if clear_hours >= 4 and (mean_cloud is None or mean_cloud <= 45) and (mean_low_cloud is None or mean_low_cloud <= 35):
        return "sunny"
    if bright_hours >= 4 and (mean_low_cloud is None or mean_low_cloud <= 55):
        return "mostly_sunny"
    if bright_hours >= 2:
        return "partly_cloudy"
    if mean_low_cloud is not None:
        if mean_low_cloud >= 75:
            return "overcast"
        if mean_low_cloud >= 55:
            return "cloudy"
    elif mean_cloud is not None:
        if mean_cloud >= 80:
            return "overcast"
        if mean_cloud >= 60:
            return "cloudy"
    if sunshine_hours is not None and sunshine_hours >= 3:
        return "variable"
    return "cloudy"


def _day_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("sunshine_minutes") is not None
             and row.get("data_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT]
    sunshine_hours = sum(row["sunshine_minutes"] for row in valid) / 60
    clear_hours = sum(
        1 for row in valid
        if (row.get("clear_sky_coverage_pct") or 0) >= BASIN_SUNNY_COVERAGE_PCT
        and row.get("cloud_diagnostic_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT
    )
    bright_hours = sum(
        1 for row in valid
        if (row.get("bright_sky_coverage_pct") or 0) >= BASIN_SUNNY_COVERAGE_PCT
        and row.get("cloud_diagnostic_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT
    )
    rain_hours = sum(
        1 for row in rows
        if (row.get("precipitation_mm") is not None and row["precipitation_mm"] >= RAIN_HOURLY_MM)
        or (row.get("rain_coverage_pct") is not None and row["rain_coverage_pct"] >= 10)
    )
    def mean(key: str) -> float | None:
        values = [row[key] for row in valid if row.get(key) is not None]
        return sum(values) / len(values) if values else None
    mean_clear = mean("clear_sky_coverage_pct")
    mean_bright = mean("bright_sky_coverage_pct")
    mean_cloud = mean("cloud_cover_pct")
    mean_low = mean("low_cloud_cover_pct")
    mean_high = mean("high_cloud_cover_pct")
    mean_shortwave = mean("shortwave_radiation_wm2")
    mean_visibility = mean("visibility_m")
    mean_completeness = (
        sum(row.get("cloud_diagnostic_completeness_pct", 0) for row in rows) / len(rows)
        if rows else 0
    )
    # This is a transparent comparative index, not a probability of sunshine.
    score = None
    if valid and mean_clear is not None and mean_bright is not None:
        low_term = 100 - mean_low if mean_low is not None else mean_bright
        cloud_term = 100 - mean_cloud if mean_cloud is not None else mean_clear
        rain_term = max(0.0, 100 - rain_hours * 25)
        score = round(0.4 * mean_clear + 0.25 * mean_bright + 0.2 * low_term + 0.1 * cloud_term + 0.05 * rain_term, 1)
    condition = _classify_day(
        sunshine_hours=sunshine_hours if valid else None,
        mean_cloud=mean_cloud,
        mean_low_cloud=mean_low,
        clear_hours=clear_hours,
        bright_hours=bright_hours,
        rain_hours=rain_hours,
    ) if valid else "pending"
    return {
        "sunshine_hours": round(sunshine_hours, 1) if valid else None,
        "mean_cloud_cover_pct": round(mean_cloud, 1) if mean_cloud is not None else None,
        "mean_low_cloud_cover_pct": round(mean_low, 1) if mean_low is not None else None,
        "mean_high_cloud_cover_pct": round(mean_high, 1) if mean_high is not None else None,
        "mean_shortwave_radiation_wm2": round(mean_shortwave, 1) if mean_shortwave is not None else None,
        "mean_visibility_m": round(mean_visibility, 0) if mean_visibility is not None else None,
        "mean_clear_sky_coverage_pct": round(mean_clear, 1) if mean_clear is not None else None,
        "mean_bright_sky_coverage_pct": round(mean_bright, 1) if mean_bright is not None else None,
        "clear_hours": clear_hours,
        "bright_hours": bright_hours,
        "rain_hours": rain_hours,
        "cloud_diagnostic_completeness_pct": round(mean_completeness, 1),
        "sunny_score": score,
        "condition": condition,
    }


def aggregate_daily(hours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for hour in hours:
        if not hour.get("valid_at"):
            continue
        interval_end = datetime.fromisoformat(hour["valid_at"])
        interval_start = interval_end - timedelta(hours=1)
        grouped[interval_start.date()].append(hour)

    daily: list[dict[str, Any]] = []
    for day, rows in sorted(grouped.items()):
        day_rows = _daylight_rows(rows)
        metrics = _day_metrics(day_rows)
        daily.append({
            "date": day.isoformat(),
            **metrics,
            "data_completeness_pct": round(
                sum(row.get("data_completeness_pct", 0) for row in day_rows) / len(day_rows), 1
            ) if day_rows else 0,
            "status": metrics["condition"],
        })
    return daily


def find_basin_sunshine_window(hours: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        row for row in hours
        if row.get("bright_sky_coverage_pct") is not None
        and row["bright_sky_coverage_pct"] >= BASIN_SUNNY_COVERAGE_PCT
        and row.get("sunshine_coverage_pct", 0) >= BASIN_SUNNY_COVERAGE_PCT
        and row.get("low_cloud_cover_pct") is not None
        and row["low_cloud_cover_pct"] <= BRIGHT_LOW_CLOUD_MAX
        and row.get("precipitation_mm") is not None
        and row["precipitation_mm"] < RAIN_HOURLY_MM
        and row.get("data_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT
        and row.get("cloud_diagnostic_completeness_pct", 0) >= MIN_DATA_COMPLETENESS_PCT
        and row.get("interpolated_area_pct", 0) <= 50
    ]
    candidates.sort(key=lambda row: row["valid_at"])
    streak: list[dict[str, Any]] = []

    def build_window(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "starts_at": (datetime.fromisoformat(items[0]["valid_at"]) - timedelta(hours=1)).isoformat(),
            "ends_at": items[-1]["valid_at"],
            "expected_sunshine_minutes": round(sum(item["sunshine_minutes"] or 0 for item in items), 1),
            "coverage_pct": round(sum(item["bright_sky_coverage_pct"] for item in items) / len(items), 1),
            "clear_sky_coverage_pct": round(sum(item.get("clear_sky_coverage_pct") or 0 for item in items) / len(items), 1),
            "mean_low_cloud_cover_pct": round(sum(item["low_cloud_cover_pct"] for item in items) / len(items), 1),
            "source_model": None,
            "basis": "连续至少 3 小时，盆地有效日照与低云约束后的明亮区域覆盖率均达到 50%，且无明显降水",
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

    def acceptable(row: CityHour) -> bool:
        if row.sunshine_seconds is None or row.sunshine_seconds < SUNNY_HOUR_SECONDS:
            return False
        if row.cloud_cover_pct is None or row.cloud_cover_pct > BRIGHT_TOTAL_CLOUD_MAX:
            return False
        if row.low_cloud_cover_pct is not None and row.low_cloud_cover_pct > BRIGHT_LOW_CLOUD_MAX:
            return False
        if row.visibility_m is not None and row.visibility_m < 1000:
            return False
        return row.precipitation_mm is not None and row.precipitation_mm < RAIN_HOURLY_MM

    def build_window(items: list[CityHour]) -> dict[str, Any]:
        return {
            "starts_at": local_iso(_as_utc(items[0].valid_at) - timedelta(hours=1)),
            "ends_at": local_iso(items[-1].valid_at),
            "expected_sunshine_minutes": round(sum(item.sunshine_seconds or 0 for item in items) / 60, 1),
            "basis": "连续至少 3 个小时，日照、总云量、低云量和降水联合筛选",
        }

    for row in rows:
        current = _as_utc(row.valid_at)
        previous = _as_utc(streak[-1].valid_at) if streak else None
        if not acceptable(row) or (previous is not None and current - previous != timedelta(hours=1)):
            if len(streak) >= MIN_WINDOW_HOURS:
                return build_window(streak)
            streak = []
        if acceptable(row):
            streak.append(row)
    return build_window(streak) if len(streak) >= MIN_WINDOW_HOURS else None


def city_daily_summary(samples: list[CityHour]) -> list[dict[str, Any]]:
    grouped: dict[date, list[CityHour]] = defaultdict(list)
    for row in samples:
        interval_start = _as_utc(row.valid_at) - timedelta(hours=1)
        grouped[interval_start.astimezone(BASIN_TIMEZONE).date()].append(row)
    result: list[dict[str, Any]] = []
    for day, rows in sorted(grouped.items()):
        day_rows = [row for row in rows if row.is_day is not False]
        values = [row.sunshine_seconds for row in day_rows if row.sunshine_seconds is not None]
        sunshine_hours = sum(values) / 3600 if values else None
        clouds = [row.cloud_cover_pct for row in day_rows if row.cloud_cover_pct is not None]
        low_clouds = [row.low_cloud_cover_pct for row in day_rows if row.low_cloud_cover_pct is not None]
        visibilities = [row.visibility_m for row in day_rows if row.visibility_m is not None]
        low_visibility_hours = sum(1 for row in day_rows if row.visibility_m is not None and row.visibility_m < 1000)
        rain_hours = sum(1 for row in day_rows if row.precipitation_mm is not None and row.precipitation_mm >= RAIN_HOURLY_MM)
        clear_hours = sum(1 for row in day_rows if row.sunshine_seconds is not None and row.sunshine_seconds >= SUNNY_HOUR_SECONDS and row.cloud_cover_pct is not None and row.cloud_cover_pct <= CLEAR_TOTAL_CLOUD_MAX and row.low_cloud_cover_pct is not None and row.low_cloud_cover_pct <= CLEAR_LOW_CLOUD_MAX and row.precipitation_mm is not None and row.precipitation_mm < RAIN_HOURLY_MM and (row.visibility_m is None or row.visibility_m >= 1000))
        bright_hours = sum(1 for row in day_rows if row.sunshine_seconds is not None and row.sunshine_seconds >= SUNNY_HOUR_SECONDS and row.low_cloud_cover_pct is not None and row.low_cloud_cover_pct <= BRIGHT_LOW_CLOUD_MAX and row.precipitation_mm is not None and row.precipitation_mm < RAIN_HOURLY_MM and (row.visibility_m is None or row.visibility_m >= 1000))
        mean_cloud = sum(clouds) / len(clouds) if clouds else None
        mean_low = sum(low_clouds) / len(low_clouds) if low_clouds else None
        condition = _classify_day(
            sunshine_hours=sunshine_hours,
            mean_cloud=mean_cloud,
            mean_low_cloud=mean_low,
            clear_hours=clear_hours,
            bright_hours=bright_hours,
            rain_hours=rain_hours,
        ) if values else "pending"
        result.append({
            "date": day.isoformat(),
            "sunshine_hours": round(sunshine_hours, 1) if sunshine_hours is not None else None,
            "mean_cloud_cover_pct": round(mean_cloud, 1) if mean_cloud is not None else None,
            "mean_low_cloud_cover_pct": round(mean_low, 1) if mean_low is not None else None,
            "mean_visibility_m": round(sum(visibilities) / len(visibilities), 0) if visibilities else None,
            "low_visibility_hours": low_visibility_hours,
            "clear_hours": clear_hours,
            "bright_hours": bright_hours,
            "rain_hours": rain_hours,
            "condition": condition,
            "status": condition,
        })
    return result
