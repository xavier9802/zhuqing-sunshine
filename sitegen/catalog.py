from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    display_name: str
    spatial_resolution_km: float
    update_interval_seconds: int
    # (maximum lead hour, native interval in seconds), ordered by lead.
    native_steps: tuple[tuple[float, int], ...]
    hourly_variables: tuple[str, ...]
    dni_method: str

    def native_step_seconds(self, lead_hours: float) -> int:
        for max_lead, interval in self.native_steps:
            if lead_hours <= max_lead:
                return interval
        return self.native_steps[-1][1]


# Sunshine duration alone is not a sufficient proxy for a clear/pleasant day.
# Collect cloud layers, humidity and radiation diagnostics as independent evidence.
COMMON_VARIABLES = (
    "sunshine_duration",
    "cloud_cover",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "precipitation",
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "shortwave_radiation",
    "weather_code",
    "is_day",
)

MODEL_CATALOG: dict[str, ModelSpec] = {
    "ecmwf_ifs": ModelSpec(
        model_id="ecmwf_ifs",
        display_name="ECMWF IFS HRES 9 km",
        spatial_resolution_km=9.0,
        update_interval_seconds=6 * 3600,
        native_steps=((90, 3600), (144, 3 * 3600), (360, 6 * 3600)),
        hourly_variables=COMMON_VARIABLES + ("visibility",),
        dni_method="native_direct_radiation_with_solar_geometry",
    ),
    "ecmwf_ifs025": ModelSpec(
        model_id="ecmwf_ifs025",
        display_name="ECMWF IFS Open Data 0.25 degree",
        spatial_resolution_km=25.0,
        update_interval_seconds=6 * 3600,
        native_steps=((144, 3 * 3600), (360, 6 * 3600)),
        hourly_variables=COMMON_VARIABLES,
        dni_method="derived_from_global_radiation",
    ),
    "ecmwf_aifs025_single": ModelSpec(
        model_id="ecmwf_aifs025_single",
        display_name="ECMWF AIFS 0.25 degree Single",
        spatial_resolution_km=28.0,
        update_interval_seconds=6 * 3600,
        native_steps=((360, 6 * 3600),),
        hourly_variables=COMMON_VARIABLES,
        dni_method="derived_from_global_radiation",
    ),
}


def get_model_spec(model_id: str) -> ModelSpec:
    try:
        return MODEL_CATALOG[model_id]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported ECMWF model '{model_id}'. "
            f"Supported: {', '.join(MODEL_CATALOG)}"
        ) from exc
