from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
from bisect import bisect_left
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from shapely.geometry import Point

from sitegen.forecast import _classify_day
from sitegen.geography import download_usgs_boundary
from sitegen.open_meteo import OpenMeteoClient, WeatherLocation, parse_valid_time

LOG = logging.getLogger("zhuqing.backtest")
TIMEZONE = ZoneInfo("Asia/Shanghai")
GHCNH_CSV_URL = (
    "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/"
    "hourly/doc/ghcnh-station-list.csv"
)
GHCNH_TXT_URL = GHCNH_CSV_URL.removesuffix(".csv") + ".txt"
GHCNH_YEAR_URL = (
    "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/"
    "hourly/access/by-year/{year}/psv/GHCNh_{station_id}_{year}.psv"
)
FORECAST_MODEL = "ecmwf_ifs"
DAY_HOURS = range(7, 19)
MIN_MATCHED_HOURS = 4
OBSERVATION_TOLERANCE = timedelta(minutes=35)

CLOUD_TOKEN = re.compile(
    r"(?<![A-Z0-9])(?:FEW|SCT|BKN|OVC|VV)(?:\d{3}|///)(?:CB|TCU)?(?![A-Z0-9])"
)
CLEAR_TOKEN = re.compile(r"(?<![A-Z0-9])(?:CLR|SKC|NCD|NSC|CAVOK)(?![A-Z0-9])")
PRECIP_TOKEN = re.compile(
    r"(?<![A-Z0-9])[+-]?(?:VC)?(?:MI|PR|BC|DR|BL|SH|FZ|TS)?"
    r"(?:RA|DZ|SN|PL|GR|GS|UP|TS)(?![A-Z0-9])"
)
CLOUD_FRACTIONS = {
    "FEW": 18.75,
    "SCT": 43.75,
    "BKN": 75.0,
    "OVC": 100.0,
    "VV": 100.0,
}


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    latitude: float
    longitude: float
    elevation_m: float | None
    wmo_id: str | None
    icao: str | None
    available_years: tuple[int, ...] = ()


@dataclass(frozen=True)
class Observation:
    valid_at: datetime
    cloud_cover_pct: float
    visibility_m: float | None
    precipitation: bool


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lstrip("\ufeff").lower())


def _field(row: dict[str, Any], *names: str) -> str | None:
    values = {_normalise_key(str(key)): value for key, value in row.items() if key}
    for name in names:
        value = values.get(_normalise_key(name))
        if value is not None and str(value).strip() not in {"", "-9999", "-9999.0"}:
            return str(value).strip()
    return None


def _number(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < -9000:
        return None
    return parsed


def _station_from_row(row: dict[str, Any]) -> Station | None:
    station_id = _field(row, "ID", "STATION_ID", "GHCN_ID", "STATION")
    latitude = _number(_field(row, "LATITUDE", "LAT"))
    longitude = _number(_field(row, "LONGITUDE", "LON"))
    if not station_id or latitude is None or longitude is None:
        return None
    if not re.fullmatch(r"[A-Z0-9]{11}", station_id.upper()):
        return None
    return Station(
        station_id=station_id.upper(),
        name=_field(row, "NAME", "STATION_NAME") or station_id,
        latitude=latitude,
        longitude=longitude,
        elevation_m=_number(_field(row, "ELEVATION", "ELEVATION_M")),
        wmo_id=_field(row, "WMO ID", "WMO_ID", "WMO"),
        icao=_field(row, "ICAO", "ICAO_ID"),
    )


def parse_station_catalog(content: str) -> list[Station]:
    stations: dict[str, Station] = {}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        station = _station_from_row(row)
        if station:
            stations[station.station_id] = station
    if stations:
        return sorted(stations.values(), key=lambda item: item.station_id)

    # NOAA also publishes the station list in the documented fixed-width format.
    for line in content.splitlines():
        if len(line) < 30:
            continue
        station_id = line[0:11].strip()
        if not re.fullmatch(r"[A-Z0-9]{11}", station_id):
            continue
        try:
            latitude = float(line[12:20].strip())
            longitude = float(line[21:30].strip())
        except ValueError:
            continue
        stations[station_id] = Station(
            station_id=station_id,
            name=line[41:71].strip() or station_id,
            latitude=latitude,
            longitude=longitude,
            elevation_m=_number(line[31:37].strip()),
            wmo_id=line[80:85].strip() or None,
            icao=line[86:90].strip() or None,
        )
    return sorted(stations.values(), key=lambda item: item.station_id)


def parse_synop_sky_cover(report: str) -> float | None:
    """Decode total cloud amount N from an FM-12 AAXX Nddff group."""
    text = report.upper()
    match = re.search(
        r"\bAAXX\s+\d{5}\s+\d{5}\s+\d{5}\s+([0-9])\d{4}\b",
        text,
    )
    if not match:
        return None
    amount = int(match.group(1))
    if amount <= 8:
        return round(amount / 8 * 100, 1)
    if amount == 9:
        # N=9 means sky obscured; it is not a clear-sky observation.
        return 100.0
    return None


def parse_synop_precipitation(report: str) -> bool:
    """Detect present precipitation from the FM-12 ww group when available."""
    text = report.upper()
    if "AAXX" not in text:
        return False
    tokens = text.split()
    for token in tokens[5:]:
        match = re.fullmatch(r"7(\d{2})\d{2}", token)
        if match:
            # SYNOP ww 50–99 describes current drizzle/rain/snow or other
            # precipitation phenomena. 20–49 are not treated as current rain.
            return int(match.group(1)) >= 50
    return False


def parse_sky_cover(report: str) -> float | None:
    text = report.upper()
    groups = CLOUD_TOKEN.findall(text)
    if groups:
        return max(CLOUD_FRACTIONS['VV' if group.startswith('VV') else group[:3]] for group in groups)
    clear = CLEAR_TOKEN.findall(text)
    if clear:
        if "CAVOK" in clear or "NSC" in clear or "NCD" in clear:
            # CAVOK/NSC do not prove a cloud-free sky; keep them in the bright band.
            return 26.0
        return 0.0
    return parse_synop_sky_cover(text)


def parse_observation(
    valid_at: datetime,
    report: str,
    visibility_km: float | None,
    precipitation_mm: float | None,
    sky_cover_pct: float | None = None,
) -> Observation | None:
    cloud = parse_sky_cover(report)
    if cloud is None:
        cloud = sky_cover_pct
    if cloud is None:
        return None
    visibility_m = visibility_km * 1000 if visibility_km is not None else None
    if visibility_m is None and re.search(
        r"(?<!\d)9999(?!\d)|(?<![A-Z0-9])CAVOK(?![A-Z0-9])",
        report.upper(),
    ):
        visibility_m = 10_000.0
    precipitation = (
        bool(PRECIP_TOKEN.search(report.upper()))
        or parse_synop_precipitation(report)
        or (precipitation_mm is not None and precipitation_mm >= 0.1)
    )
    return Observation(
        valid_at=valid_at.astimezone(UTC),
        cloud_cover_pct=cloud,
        visibility_m=visibility_m,
        precipitation=precipitation,
    )



def parse_sky_cover_code(value: str | float | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text or text in {"-9999", "-9999.0", "99", "999", "9999"}:
        return None
    # Some GHCNh source streams encode total/opaque/lowest cover as a slash-
    # separated triplet; the first component is total sky cover.
    first = re.split(r"[/, ]+", text)[0]
    if first in CLOUD_FRACTIONS:
        return CLOUD_FRACTIONS[first]
    if first in {"CLR", "SKC"}:
        return 0.0
    if first in {"CAVOK", "NSC", "NCD"}:
        return 26.0
    category = parse_sky_cover(first)
    if category is not None:
        return category
    try:
        code = float(first)
    except ValueError:
        return None
    if 0 <= code <= 8:
        return round(code / 8 * 100, 1)
    if code in {9, 10}:
        # 9 = obscured sky; 10 = partial obscuration. Neither is safe to
        # interpret as a clear-sky observation.
        return 100.0
    if 10 < code <= 100:
        return code
    return None


def parse_sky_cover_from_row(row: dict[str, Any]) -> float | None:
    overall = parse_sky_cover_code(_field(row, "sky_condition"))
    if overall is not None:
        return overall
    summations = [
        parse_sky_cover_code(_field(row, f"sky_cover_summation_{index}"))
        for index in range(1, 5)
    ]
    available = [value for value in summations if value is not None]
    if available:
        return max(available)
    layers = [
        parse_sky_cover_code(_field(row, f"sky_cover_layer_{index}"))
        for index in range(1, 5)
    ]
    available = [value for value in layers if value is not None]
    return max(available) if available else None


def stations_near_boundary(stations: list[Station], boundary: Any) -> list[Station]:
    buffered = boundary.buffer(0.5)
    return [
        station for station in stations
        if buffered.covers(Point(station.longitude, station.latitude))
    ]


def probe_station_availability(
    client: httpx.Client,
    stations: list[Station],
    years: list[int],
) -> list[Station]:
    available: list[Station] = []
    for station in stations:
        station_years: list[int] = []
        for year in years:
            url = GHCNH_YEAR_URL.format(year=year, station_id=station.station_id)
            try:
                response = client.head(url)
                if response.status_code in {405, 501}:
                    response = client.get(url, headers={"Range": "bytes=0-0"})
                if response.status_code in {200, 206}:
                    station_years.append(year)
                elif response.status_code != 404:
                    LOG.warning(
                        "Station availability probe %s/%s returned HTTP %s",
                        station.station_id, year, response.status_code,
                    )
            except httpx.HTTPError as exc:
                LOG.warning("Station availability probe failed for %s/%s: %s", station.station_id, year, exc)
        if station_years:
            available.append(replace(station, available_years=tuple(station_years)))
    LOG.info(
        "NOAA GHCNh station availability: %s/%s stations have data in target years %s",
        len(available), len(stations), years,
    )
    return available


def select_stations(stations: list[Station], boundary: Any, max_stations: int) -> list[Station]:
    if max_stations < 1:
        raise ValueError("max_stations must be at least 1")
    inside = [
        station for station in stations
        if boundary.covers(Point(station.longitude, station.latitude))
    ]
    candidates = inside
    selection_basis = "inside_basin"
    if len(candidates) < min(3, max_stations):
        expanded = [
            station for station in stations
            if boundary.buffer(0.5).covers(Point(station.longitude, station.latitude))
        ]
        if len(expanded) > len(candidates):
            candidates = expanded
            selection_basis = "inside_or_within_0_5_degree_buffer"
    if not candidates:
        raise RuntimeError("NOAA GHCNh has no stations inside or near the basin boundary")

    candidates = sorted(
        candidates,
        key=lambda item: (
            -len(item.available_years),
            not bool(item.icao),
            not bool(item.wmo_id),
            item.station_id,
        ),
    )
    selected: list[Station] = []
    # CHI network IDs are ICAO-coded airport stations; include them before
    # spatially filling in lower-frequency SYNOP sites. Station-year file
    # presence alone does not prove that sky-cover fields are usable.
    airport_candidates = [
        station for station in candidates
        if station.station_id.startswith("CHI") or station.icao
    ]
    remaining = candidates.copy()
    for station in airport_candidates:
        if len(selected) >= max_stations:
            break
        selected.append(station)
        remaining.remove(station)

    # Farthest-point sampling then covers the rest of the basin, instead of
    # allowing remote SYNOP locations to crowd out observed airport cloud data.
    while remaining and len(selected) < max_stations:
        if not selected:
            centre = boundary.centroid
            next_station = min(
                remaining,
                key=lambda item: Point(item.longitude, item.latitude).distance(centre),
            )
        else:
            next_station = max(
                remaining,
                key=lambda item: min(
                    Point(item.longitude, item.latitude).distance(
                        Point(chosen.longitude, chosen.latitude)
                    )
                    for chosen in selected
                ),
            )
        selected.append(next_station)
        remaining.remove(next_station)
    LOG.info(
        "Selected %s GHCNh stations (%s); %s candidates available",
        len(selected), selection_basis, len(candidates),
    )
    return selected


def sample_run_dates(start: date, end: date, max_runs: int) -> list[date]:
    if end < start:
        raise ValueError("end date must not precede start date")
    if max_runs < 1:
        raise ValueError("max_runs must be at least 1")
    dates: list[date] = []
    year, month = start.year, start.month
    while True:
        candidate = date(year, month, 15)
        if start <= candidate <= end:
            dates.append(candidate)
        month += 1
        if month == 13:
            year += 1
            month = 1
        if date(year, month, 1) > end:
            break
    if len(dates) <= max_runs:
        return dates
    if max_runs == 1:
        return [dates[len(dates) // 2]]
    indices = sorted({
        round(index * (len(dates) - 1) / (max_runs - 1))
        for index in range(max_runs)
    })
    return [dates[index] for index in indices]


def _parse_timestamp(row: dict[str, Any]) -> datetime | None:
    raw = _field(row, "DATE", "TIMESTAMP", "DATE_TIME")
    if raw:
        try:
            parsed = datetime.fromisoformat(raw)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            pass
    year = _number(_field(row, "YEAR"))
    month = _number(_field(row, "MONTH"))
    day = _number(_field(row, "DAY"))
    hour = _number(_field(row, "HOUR"))
    minute = _number(_field(row, "MINUTE")) or 0
    if None in {year, month, day, hour}:
        return None
    try:
        return datetime(
            int(year), int(month), int(day), int(hour), int(minute), tzinfo=UTC
        )
    except ValueError:
        return None


def load_station_year(
    client: httpx.Client,
    station: Station,
    year: int,
    cache_dir: Path,
    target_dates: set[date],
    diagnostics: dict[str, Any] | None = None,
) -> list[Observation]:
    cache_path = cache_dir / "ghcnh" / str(year) / f"{station.station_id}.psv"
    if cache_path.is_file():
        content = cache_path.read_text(encoding="utf-8", errors="replace")
    else:
        url = GHCNH_YEAR_URL.format(year=year, station_id=station.station_id)
        response = client.get(url)
        if response.status_code == 404:
            LOG.warning("No NOAA GHCNh file for %s in %s", station.station_id, year)
            return []
        response.raise_for_status()
        content = response.text
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(content, encoding="utf-8")

    observations: dict[datetime, Observation] = {}
    reader = csv.DictReader(io.StringIO(content), delimiter="|")
    for row in reader:
        if diagnostics is not None:
            diagnostics["rows_read"] = diagnostics.get("rows_read", 0) + 1
        valid_at = _parse_timestamp(row)
        if valid_at is None or valid_at.astimezone(TIMEZONE).date() not in target_dates:
            continue
        if diagnostics is not None:
            diagnostics["rows_in_target_dates"] = diagnostics.get("rows_in_target_dates", 0) + 1
        report = _field(row, "REM", "REMARKS") or ""
        if report and diagnostics is not None:
            diagnostics["rows_with_raw_report"] = diagnostics.get("rows_with_raw_report", 0) + 1
            if parse_synop_sky_cover(report) is not None:
                diagnostics["rows_with_fm12_synop_cloud"] = (
                    diagnostics.get("rows_with_fm12_synop_cloud", 0) + 1
                )
            if parse_synop_precipitation(report):
                diagnostics["rows_with_fm12_synop_precipitation"] = (
                    diagnostics.get("rows_with_fm12_synop_precipitation", 0) + 1
                )
            examples = diagnostics.setdefault("raw_report_examples", [])
            if len(examples) < 3:
                examples.append({
                    "report": report[:500],
                    "columns": sorted(
                        key for key in row
                        if any(token in _normalise_key(key) for token in (
                            "sky", "cloud", "remarks", "report", "weather", "visibility"
                        ))
                    ),
                })
        sky_cover = parse_sky_cover_from_row(row)
        if sky_cover is not None and diagnostics is not None:
            diagnostics["rows_with_sky_cover_fields"] = diagnostics.get("rows_with_sky_cover_fields", 0) + 1
        observation = parse_observation(
            valid_at,
            report,
            _number(_field(row, "visibility")),
            _number(_field(row, "precipitation")),
            sky_cover_pct=sky_cover,
        )
        if observation is not None:
            if diagnostics is not None:
                diagnostics["usable_observations"] = diagnostics.get("usable_observations", 0) + 1
            observations[valid_at] = observation
    return sorted(observations.values(), key=lambda item: item.valid_at)


def nearest_observation(
    observations: list[Observation],
    timestamps: list[datetime],
    target: datetime,
) -> Observation | None:
    if not observations:
        return None
    index = bisect_left(timestamps, target)
    candidates = []
    if index < len(observations):
        candidates.append(observations[index])
    if index > 0:
        candidates.append(observations[index - 1])
    if not candidates:
        return None
    nearest = min(candidates, key=lambda item: abs(item.valid_at - target))
    return nearest if abs(nearest.valid_at - target) <= OBSERVATION_TOLERANCE else None


def _forecast_number(hourly: dict[str, Any], key: str, index: int) -> float | None:
    values = hourly.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return _number(values[index])


def _forecast_day_metrics(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [
        row for row in rows
        if row["sunshine_seconds"] is not None
        and row["cloud_cover_pct"] is not None
        and row["low_cloud_cover_pct"] is not None
        and row["precipitation_mm"] is not None
    ]
    if len(valid) < MIN_MATCHED_HOURS:
        return None
    sunshine_hours = sum(row["sunshine_seconds"] for row in valid) / 3600
    clear_hours = sum(
        1 for row in valid
        if row["sunshine_seconds"] >= 1800
        and row["cloud_cover_pct"] <= 30
        and row["low_cloud_cover_pct"] <= 25
        and row["precipitation_mm"] < 0.1
        and (row["visibility_m"] is None or row["visibility_m"] >= 1000)
    )
    bright_hours = sum(
        1 for row in valid
        if row["sunshine_seconds"] >= 1800
        and row["low_cloud_cover_pct"] <= 50
        and row["precipitation_mm"] < 0.1
        and (row["visibility_m"] is None or row["visibility_m"] >= 1000)
    )
    rain_hours = sum(1 for row in valid if row["precipitation_mm"] >= 0.1)
    mean_cloud = sum(row["cloud_cover_pct"] for row in valid) / len(valid)
    mean_low = sum(row["low_cloud_cover_pct"] for row in valid) / len(valid)
    return {
        "condition": _classify_day(
            sunshine_hours=sunshine_hours,
            mean_cloud=mean_cloud,
            mean_low_cloud=mean_low,
            clear_hours=clear_hours,
            bright_hours=bright_hours,
            rain_hours=rain_hours,
        ),
        "sunshine_hours": round(sunshine_hours, 2),
        "mean_cloud_cover_pct": round(mean_cloud, 1),
        "clear_hours": clear_hours,
        "bright_hours": bright_hours,
        "rain_hours": rain_hours,
        "matched_hours": len(valid),
    }


def _observed_day_metrics(rows: list[Observation]) -> dict[str, Any] | None:
    if len(rows) < MIN_MATCHED_HOURS:
        return None
    clear_hours = sum(
        1 for row in rows
        if row.cloud_cover_pct <= 25
        and not row.precipitation
        and (row.visibility_m is None or row.visibility_m >= 1000)
    )
    bright_hours = sum(
        1 for row in rows
        if row.cloud_cover_pct <= 50
        and not row.precipitation
        and (row.visibility_m is None or row.visibility_m >= 1000)
    )
    rain_hours = sum(1 for row in rows if row.precipitation)
    mean_cloud = sum(row.cloud_cover_pct for row in rows) / len(rows)
    return {
        "condition": _classify_day(
            sunshine_hours=None,
            mean_cloud=mean_cloud,
            mean_low_cloud=None,
            clear_hours=clear_hours,
            bright_hours=bright_hours,
            rain_hours=rain_hours,
        ),
        "mean_cloud_cover_pct": round(mean_cloud, 1),
        "clear_hours": clear_hours,
        "bright_hours": bright_hours,
        "rain_hours": rain_hours,
        "matched_hours": len(rows),
    }


def _binary_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    positive = {"sunny", "mostly_sunny"}
    tp = fp = tn = fn = 0
    for sample in samples:
        predicted = sample["forecast_condition"] in positive
        observed = sample["observed_condition"] in positive
        if predicted and observed:
            tp += 1
        elif predicted:
            fp += 1
        elif observed:
            fn += 1
        else:
            tn += 1
    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "station_days": total,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "accuracy_pct": round((tp + tn) / total * 100, 1) if total else None,
        "precision_pct": round(precision * 100, 1) if precision is not None else None,
        "recall_pct": round(recall * 100, 1) if recall is not None else None,
        "f1_pct": (
            round(2 * precision * recall / (precision + recall) * 100, 1)
            if precision is not None and recall is not None and precision + recall > 0
            else None
        ),
    }


def _lead_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    result = _binary_metrics(samples)
    cloud_errors = [
        sample["cloud_cover_abs_error_pct"]
        for sample in samples
        if sample.get("cloud_cover_abs_error_pct") is not None
    ]
    cloud_bias = [
        sample["forecast_mean_cloud_cover_pct"] - sample["observed_mean_cloud_cover_pct"]
        for sample in samples
        if sample.get("forecast_mean_cloud_cover_pct") is not None
        and sample.get("observed_mean_cloud_cover_pct") is not None
    ]
    result["cloud_cover_mae_pct"] = (
        round(sum(cloud_errors) / len(cloud_errors), 1) if cloud_errors else None
    )
    result["cloud_cover_bias_pct"] = (
        round(sum(cloud_bias) / len(cloud_bias), 1) if cloud_bias else None
    )
    result["station_day_cloud_pairs"] = len(cloud_errors)
    return result


def sample_quality_gate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    verified_stations = {row["station_id"] for row in samples}
    months = {int(row["target_date"][5:7]) for row in samples}
    seasons = {
        "winter" if month in {12, 1, 2}
        else "spring" if month in {3, 4, 5}
        else "summer" if month in {6, 7, 8}
        else "autumn"
        for month in months
    }
    lead_counts = {
        str(lead): sum(row["lead_day"] == lead for row in samples)
        for lead in (1, 2, 3)
    }
    checks = {
        "at_least_200_station_days": len(samples) >= 200,
        "at_least_4_verified_stations": len(verified_stations) >= 4,
        "at_least_50_days_per_lead": all(count >= 50 for count in lead_counts.values()),
        "four_seasons_represented": len(seasons) == 4,
    }
    return {
        "sufficient_for_research_review": bool(samples) and all(checks.values()),
        "calibrated_sunshine_probability": False,
        "checks": checks,
        "verified_station_count": len(verified_stations),
        "verified_station_ids": sorted(verified_stations),
        "lead_station_days": lead_counts,
        "represented_seasons": sorted(seasons),
        "caveat": (
            "通过样本规模门槛也不代表可直接标定晴天概率；"
            "仍需独立留出集、太阳辐射/实测日照数据及区域分层核验。"
        ),
    }


def run_backtest(
    *,
    start_date: date,
    end_date: date,
    max_runs: int,
    max_stations: int,
    cache_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    run_dates = sample_run_dates(start_date, end_date, max_runs)
    if not run_dates:
        raise ValueError("No monthly sample dates fall inside the requested period")

    boundary, boundary_metadata = download_usgs_boundary(cache_dir)
    station_http = httpx.Client(
        timeout=httpx.Timeout(120, connect=20),
        headers={"User-Agent": "Zhuqing-Sunshine-Backtest/1.0"},
        follow_redirects=True,
    )
    try:
        response = station_http.get(GHCNH_CSV_URL)
        if response.status_code == 200:
            station_catalog = parse_station_catalog(response.text)
        else:
            response = station_http.get(GHCNH_TXT_URL)
            response.raise_for_status()
            station_catalog = parse_station_catalog(response.text)
        if not station_catalog:
            raise RuntimeError("NOAA GHCNh station list returned no parsable stations")
        target_dates = {
            (
                datetime.combine(run_day, datetime.min.time(), tzinfo=UTC)
                .astimezone(TIMEZONE).date() + timedelta(days=lead)
            )
            for run_day in run_dates
            for lead in (1, 2, 3)
        }
        years = sorted({day.year for day in target_dates})
        regional_candidates = stations_near_boundary(station_catalog, boundary)
        available_candidates = probe_station_availability(
            station_http, regional_candidates, years
        )
        if not available_candidates:
            raise RuntimeError(
                f"No NOAA GHCNh station-year files found in the region for {years}"
            )
        stations = select_stations(available_candidates, boundary, max_stations)
        station_observations: dict[str, list[Observation]] = {}
        station_diagnostics: dict[str, dict[str, Any]] = {}
        for station in stations:
            records: list[Observation] = []
            diagnostics: dict[str, int] = {}
            for year in station.available_years:
                records.extend(
                    load_station_year(
                        station_http, station, year, cache_dir, target_dates, diagnostics
                    )
                )
            unique = {item.valid_at: item for item in records}
            station_observations[station.station_id] = sorted(
                unique.values(), key=lambda item: item.valid_at
            )
            diagnostics["unique_usable_observations"] = len(unique)
            station_diagnostics[station.station_id] = diagnostics
    finally:
        station_http.close()

    forecast_client = OpenMeteoClient(
        base_url="https://api.open-meteo.com",
        single_runs_base_url="https://single-runs-api.open-meteo.com",
        timeout_seconds=60,
        max_attempts=4,
    )
    station_locations = [
        WeatherLocation(
            location_id=index,
            location_key=station.station_id,
            latitude=station.latitude,
            longitude=station.longitude,
        )
        for index, station in enumerate(stations)
    ]
    samples_by_lead: dict[int, list[dict[str, Any]]] = defaultdict(list)
    run_statuses: list[dict[str, Any]] = []
    try:
        for run_day in run_dates:
            run_at = datetime.combine(run_day, datetime.min.time(), tzinfo=UTC)
            try:
                forecast_items = forecast_client.fetch_forecast_batch(
                    model_id=FORECAST_MODEL,
                    locations=station_locations,
                    run_at=run_at,
                    forecast_days=5,
                )
            except (httpx.HTTPError, ValueError, TypeError, RuntimeError) as exc:
                LOG.warning("Forecast run %s unavailable: %s", run_at.isoformat(), exc)
                run_statuses.append({
                    "run_at": run_at.isoformat(),
                    "status": "unavailable",
                    "reason": str(exc)[:240],
                })
                continue
            run_statuses.append({
                "run_at": run_at.isoformat(),
                "status": "available",
                "station_count": len(forecast_items),
            })
            for station, item in zip(stations, forecast_items, strict=True):
                hourly = item.get("hourly", {})
                time_values = hourly.get("time", [])
                station_obs = station_observations.get(station.station_id, [])
                obs_times = [row.valid_at for row in station_obs]
                for lead_day in (1, 2, 3):
                    target_day = run_at.astimezone(TIMEZONE).date() + timedelta(days=lead_day)
                    pairs: list[tuple[dict[str, Any], Observation]] = []
                    for index, stamp in enumerate(time_values):
                        valid_at = parse_valid_time(stamp)
                        local_time = valid_at.astimezone(TIMEZONE)
                        if local_time.date() != target_day or local_time.hour not in DAY_HOURS:
                            continue
                        forecast_row = {
                            "valid_at": valid_at,
                            "sunshine_seconds": _forecast_number(hourly, "sunshine_duration", index),
                            "cloud_cover_pct": _forecast_number(hourly, "cloud_cover", index),
                            "low_cloud_cover_pct": _forecast_number(hourly, "cloud_cover_low", index),
                            "precipitation_mm": _forecast_number(hourly, "precipitation", index),
                            "visibility_m": _forecast_number(hourly, "visibility", index),
                        }
                        if any(
                            forecast_row[key] is None
                            for key in (
                                "sunshine_seconds", "cloud_cover_pct",
                                "low_cloud_cover_pct", "precipitation_mm",
                            )
                        ):
                            continue
                        observation = nearest_observation(station_obs, obs_times, valid_at)
                        if observation is not None:
                            pairs.append((forecast_row, observation))
                    if len(pairs) < MIN_MATCHED_HOURS:
                        continue
                    forecast_metrics = _forecast_day_metrics([pair[0] for pair in pairs])
                    observed_metrics = _observed_day_metrics([pair[1] for pair in pairs])
                    if forecast_metrics is None or observed_metrics is None:
                        continue
                    cloud_errors = [
                        abs(pair[0]["cloud_cover_pct"] - pair[1].cloud_cover_pct)
                        for pair in pairs
                    ]
                    samples_by_lead[lead_day].append({
                        "run_at": run_at.isoformat(),
                        "target_date": target_day.isoformat(),
                        "lead_day": lead_day,
                        "station_id": station.station_id,
                        "station_name": station.name,
                        "forecast_condition": forecast_metrics["condition"],
                        "observed_condition": observed_metrics["condition"],
                        "matched_hours": len(pairs),
                        "forecast_sunshine_hours": forecast_metrics["sunshine_hours"],
                        "forecast_mean_cloud_cover_pct": forecast_metrics["mean_cloud_cover_pct"],
                        "observed_mean_cloud_cover_pct": observed_metrics["mean_cloud_cover_pct"],
                        "cloud_cover_abs_error_pct": round(sum(cloud_errors) / len(cloud_errors), 1),
                    })
    finally:
        forecast_client.close()

    lead_summaries = {
        str(lead): _lead_summary(samples_by_lead[lead])
        for lead in (1, 2, 3)
    }
    all_samples = [
        sample
        for lead in (1, 2, 3)
        for sample in samples_by_lead[lead]
    ]
    quality = sample_quality_gate(all_samples)
    payload = {
        "status": (
            "insufficient_observations" if not all_samples
            else "research_ready" if quality["sufficient_for_research_review"]
            else "exploratory"
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "forecast_model": FORECAST_MODEL,
        "forecast_source": "Open-Meteo Single Runs API (archived ECMWF IFS HRES)",
        "observation_source": "NOAA NCEI Global Historical Climatology Network hourly (GHCNh)",
        "sample_period": {
            "start_date": min(run_dates).isoformat(),
            "end_date": max(run_dates).isoformat(),
            "run_count_requested": len(run_dates),
            "run_count_available": sum(1 for item in run_statuses if item["status"] == "available"),
        },
        "stations": [asdict(station) for station in stations],
        "station_count": quality["verified_station_count"],
        "candidate_station_count": len(stations),
        "quality_gates": quality,
        "station_diagnostics": station_diagnostics,
        "lead_days": lead_summaries,
        "sample_count": len(all_samples),
        "samples": all_samples,
        "method": {
            "target": "机场/地面站 METAR 天空状况、能见度和降水构成的晴好天气代理标签",
            "daylight_window_local": "07:00–18:59 Asia/Shanghai",
            "lead_days": [1, 2, 3],
            "matching": "forecast valid time 与 NOAA 观测时间最近邻匹配，容差 35 分钟；每日至少 4 个匹配小时",
            "positive_class": "sunny 或 mostly_sunny",
            "cloud_mae_method": "先计算每个站点日匹配时次的平均绝对误差，再对站点日等权平均；不代表所有逐小时样本等权。",
            "forecast_cycle_note": "跨越不同 ECMWF IFS 版本的结果暂按总体展示，正式校准必须额外分版本回测。",
            "cloud_cover": "优先采用 GHCNh sky_condition/sky_cover_summation/sky_cover_layer 观测字段；缺失时回退解析 METAR 原始报文。FEW/SCT/BKN/OVC/VV 转为 oktas 覆盖率区间中点；CAVOK/NSC/NCD 保守记为 26%，不等同于晴空",
            "limitations": [
                "GHCNh 站点主要为机场/地面报文站，空间分布稀疏，不能代表整个盆地每个网格。",
                "METAR 云量是天空状况代理，不是地面日照时数传感器；本报告不能验证 sunshine_duration 的分钟级误差。",
                "观测缺测、报文类型和站点代表性会影响样本量；不将缺测视为晴天或无降水。",
                "本轮只评估 ECMWF IFS HRES 单模型站点预报；不能据此校准三个模型的独立概率。",
            ],
            "boundary_source": boundary_metadata.get("source_name"),
            "boundary_caveat": boundary_metadata.get("boundary_caveat"),
        },
        "forecast_runs": run_statuses,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify archived ECMWF sunshine/sky-condition forecasts against NOAA station reports"
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2024, 4, 15))
    parser.add_argument("--end-date", type=date.fromisoformat, default=datetime.now(UTC).date() - timedelta(days=14))
    parser.add_argument("--max-runs", type=int, default=16)
    parser.add_argument("--max-stations", type=int, default=12)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/zhuqing"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/forecast-backtest.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_backtest(
        start_date=args.start_date,
        end_date=args.end_date,
        max_runs=args.max_runs,
        max_stations=args.max_stations,
        cache_dir=args.cache_dir,
        output_path=args.output,
    )
    print(json.dumps({
        "status": result["status"],
        "station_count": result["station_count"],
        "sample_count": result["sample_count"],
        "lead_days": result["lead_days"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    if result["status"] == "insufficient_observations":
        raise SystemExit("No valid forecast/observation matches; no accuracy claim can be made")


if __name__ == "__main__":
    main()
