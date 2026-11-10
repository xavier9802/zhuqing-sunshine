from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

NASA_POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
NASA_POWER_PARAMETER = "ALLSKY_SFC_SW_DWN"


def _grid_key(payload: dict[str, Any], latitude: float, longitude: float) -> str:
    geometry = payload.get("geometry")
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        try:
            return f"{float(coordinates[1]):.3f},{float(coordinates[0]):.3f}"
        except (TypeError, ValueError):
            pass

    header = payload.get("header")
    if isinstance(header, dict):
        try:
            return f"{float(header['latitude']):.3f},{float(header['longitude']):.3f}"
        except (KeyError, TypeError, ValueError):
            pass

    # POWER's global daily radiation grid is 0.5 degrees. This fallback is
    # only a spatial de-duplication key; the API response remains authoritative.
    grid_lat = round((latitude - 0.25) * 2) / 2 + 0.25
    grid_lon = round((longitude - 0.25) * 2) / 2 + 0.25
    return f"{grid_lat:.2f},{grid_lon:.2f}"


def parse_nasa_power_daily_payload(
    payload: dict[str, Any],
    *,
    latitude: float,
    longitude: float,
) -> tuple[str, dict[date, float]]:
    header = payload.get("header")
    fill_value = (
        float(header["fill_value"])
        if isinstance(header, dict) and header.get("fill_value") is not None
        else -999.0
    )

    properties = payload.get("properties")
    parameters = properties.get("parameter") if isinstance(properties, dict) else None
    series = parameters.get(NASA_POWER_PARAMETER) if isinstance(parameters, dict) else None
    if not isinstance(series, dict):
        raise TypeError(f"NASA POWER response is missing {NASA_POWER_PARAMETER}")

    values: dict[date, float] = {}
    for raw_day, raw_value in series.items():
        if not isinstance(raw_day, str) or len(raw_day) != 8:
            continue
        try:
            day = date(int(raw_day[:4]), int(raw_day[4:6]), int(raw_day[6:8]))
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value <= fill_value or value < 0 or value > 60:
            continue
        values[day] = value

    return _grid_key(payload, latitude, longitude), values


def load_nasa_power_daily_radiation(
    client: httpx.Client,
    *,
    station_id: str,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    cache_dir: Path,
) -> tuple[str, dict[date, float]]:
    cache_path = cache_dir / "nasa_power" / (
        f"{station_id}_{start_date:%Y%m%d}_{end_date:%Y%m%d}.json"
    )
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        values = {
            date.fromisoformat(day): float(value)
            for day, value in cached.get("values", {}).items()
        }
        return str(cached["grid_key"]), values

    params = {
        "parameters": NASA_POWER_PARAMETER,
        "community": "RE",
        "longitude": f"{longitude:.5f}",
        "latitude": f"{latitude:.5f}",
        "start": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "LST",
    }

    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = client.get(NASA_POWER_DAILY_URL, params=params)
            if response.status_code in {429, 500, 502, 503, 504}:
                if attempt == 3:
                    response.raise_for_status()
                time.sleep(min(20.0, 2.0 * (attempt + 1)))
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("NASA POWER returned an invalid response")
            messages = payload.get("messages")
            if isinstance(messages, dict) and messages.get("errors"):
                raise ValueError("NASA POWER returned an error response")
            grid_key, values = parse_nasa_power_daily_payload(
                payload, latitude=latitude, longitude=longitude
            )
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({
                    "grid_key": grid_key,
                    "values": {day.isoformat(): value for day, value in values.items()},
                }),
                encoding="utf-8",
            )
            return grid_key, values
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt == 3:
                raise
            time.sleep(min(20.0, 2.0 * (attempt + 1)))

    if last_error:
        raise last_error
    raise RuntimeError("NASA POWER request failed without a response")
