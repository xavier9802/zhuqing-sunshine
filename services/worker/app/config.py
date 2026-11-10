from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    open_meteo_usage: str
    open_meteo_base_url: str
    open_meteo_single_runs_base_url: str
    open_meteo_api_key: str | None
    forecast_days: int
    grid_spacing_degrees: float
    batch_size: int
    request_timeout_seconds: float
    max_attempts: int
    model_ids: tuple[str, ...]

    @classmethod
    def from_env(cls) -> Settings:
        usage = os.getenv("OPEN_METEO_USAGE", "non_commercial").strip().lower()
        if usage not in {"non_commercial", "commercial"}:
            raise ValueError("OPEN_METEO_USAGE must be non_commercial or commercial")

        api_key = os.getenv("OPEN_METEO_API_KEY") or None
        if usage == "commercial" and not api_key:
            raise ValueError(
                "Commercial Open-Meteo usage requires OPEN_METEO_API_KEY. "
                "Do not route a commercial product through the free endpoint."
            )

        default_api_base = (
            "https://customer-api.open-meteo.com"
            if usage == "commercial"
            else "https://api.open-meteo.com"
        )
        default_single_runs_base = (
            "https://customer-single-runs-api.open-meteo.com"
            if usage == "commercial"
            else "https://single-runs-api.open-meteo.com"
        )
        api_base = os.getenv("OPEN_METEO_BASE_URL") or default_api_base
        single_runs_base = (
            os.getenv("OPEN_METEO_SINGLE_RUNS_BASE_URL") or default_single_runs_base
        )
        model_ids = tuple(
            item.strip()
            for item in os.getenv(
                "WEATHER_MODELS",
                "ecmwf_ifs,ecmwf_ifs025,ecmwf_aifs025_single",
            ).split(",")
            if item.strip()
        )

        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+psycopg://zhuqing:change-me-locally@localhost:5432/zhuqing",
            ),
            data_dir=Path(os.getenv("DATA_DIR", "/app/data")),
            open_meteo_usage=usage,
            open_meteo_base_url=api_base.rstrip("/"),
            open_meteo_single_runs_base_url=single_runs_base.rstrip("/"),
            open_meteo_api_key=api_key,
            forecast_days=max(1, min(15, int(os.getenv("FORECAST_DAYS", "7")))),
            grid_spacing_degrees=float(os.getenv("GRID_SPACING_DEGREES", "0.25")),
            batch_size=max(1, min(100, int(os.getenv("WEATHER_BATCH_SIZE", "25")))),
            request_timeout_seconds=float(os.getenv("WEATHER_TIMEOUT_SECONDS", "45")),
            max_attempts=max(1, min(8, int(os.getenv("WEATHER_MAX_ATTEMPTS", "5")))),
            model_ids=model_ids,
        )
