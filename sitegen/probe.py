"""Low-cost real-provider probe: one city, one day, one request per model."""

from __future__ import annotations

import json
import sys

import httpx

from sitegen.catalog import MODEL_CATALOG
from sitegen.open_meteo import OpenMeteoClient, WeatherLocation


def main() -> None:
    client = OpenMeteoClient(base_url="https://api.open-meteo.com")
    location = WeatherLocation(
        location_id=1, location_key="city:chengdu", latitude=30.65, longitude=104.07
    )
    statuses: list[dict[str, object]] = []
    try:
        for model_id in MODEL_CATALOG:
            try:
                meta = client.fetch_metadata(model_id)
                if meta.model_run_at is None:
                    raise ValueError("Missing model run time")
                hourly = client.fetch_forecast_batch(
                    model_id=model_id,
                    locations=[location],
                    run_at=meta.model_run_at,
                    forecast_days=1,
                )[0]["hourly"]
                required = ("sunshine_duration", "cloud_cover", "cloud_cover_low",
                            "precipitation", "is_day")
                missing = [field for field in required if field not in hourly]
                if missing:
                    raise ValueError(f"Missing diagnostic variables: {missing}")
                valid = [item for item in hourly["sunshine_duration"] if item is not None]
                if not valid or not any(item is not None for item in hourly["cloud_cover_low"]):
                    raise ValueError("No usable sunshine or low-cloud diagnostics")
                statuses.append(
                    {
                        "model": model_id,
                        "status": "available",
                        "initialised_at": meta.model_run_at.isoformat(),
                        "valid_hours": len(valid),
                    }
                )
            except (httpx.HTTPError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                statuses.append(
                    {"model": model_id, "status": "failed", "error": str(exc)[:300]}
                )
    finally:
        client.close()
    print(json.dumps(statuses, ensure_ascii=False, indent=2))
    if not any(item["status"] == "available" for item in statuses):
        sys.exit("No model passed the provider probe")


if __name__ == "__main__":
    main()
