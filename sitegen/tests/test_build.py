from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from shapely.geometry import box, mapping

from sitegen.build import GeographySnapshot, generate
from sitegen.open_meteo import ModelMetadata

NOW = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)


class FakeWeatherClient:
    def __init__(self, fail: bool = False, hours: int = 5):
        self.fail = fail
        self.hours = hours
        self.calls = 0

    def fetch_metadata(self, model_id: str) -> ModelMetadata:
        if self.fail:
            raise ValueError("provider unavailable")
        return ModelMetadata(
            model_id=model_id,
            model_run_at=NOW,
            modified_at=NOW,
            available_at=NOW - timedelta(hours=1),
            data_end_time=NOW + timedelta(days=7),
            temporal_resolution_seconds=3600,
            update_interval_seconds=21600,
            raw={},
        )

    def fetch_forecast_batch(self, model_id, locations, run_at, forecast_days):
        self.calls += 1
        times = [
            (NOW + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
            for i in range(1, self.hours + 1)
        ]
        return [
            {
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "hourly": {
                    "time": times,
                    "sunshine_duration": [
                        3000 if i <= 3 else 0 for i in range(1, self.hours + 1)
                    ],
                    "cloud_cover": [20] * self.hours,
                    "cloud_cover_low": [15] * self.hours,
                    "cloud_cover_mid": [10] * self.hours,
                    "cloud_cover_high": [5] * self.hours,
                    "precipitation": [0] * self.hours,
                    "temperature_2m": [17] * self.hours,
                    "relative_humidity_2m": [55] * self.hours,
                    "dew_point_2m": [8] * self.hours,
                    "shortwave_radiation": [300] * self.hours,
                    "weather_code": [1] * self.hours,
                    "is_day": [1] * self.hours,
                },
            }
            for loc in locations
        ]


def geography_fixture() -> GeographySnapshot:
    grids = [
        {
            "type": "Feature",
            "geometry": mapping(box(104.0, 30.0, 104.25, 30.25)),
            "properties": {
                "location_key": "grid:416:120",
                "area_km2": 80.0,
                "latitude": 30.125,
                "longitude": 104.125,
            },
        },
        {
            "type": "Feature",
            "geometry": mapping(box(104.25, 30.0, 104.5, 30.25)),
            "properties": {
                "location_key": "grid:417:120",
                "area_km2": 20.0,
                "latitude": 30.125,
                "longitude": 104.375,
            },
        },
    ]
    cities = [
        {"slug": "chengdu", "name_zh": "成都", "latitude": 30.65, "longitude": 104.07},
    ]
    return GeographySnapshot(grid_features=grids, cities=cities)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_static_build_writes_model_city_and_compact_time_layers(tmp_path: Path) -> None:
    output = tmp_path / "public"
    client = FakeWeatherClient()
    result = generate(
        output,
        cache=tmp_path / "cache",
        models=("ecmwf_ifs",),
        geography=geography_fixture(),
        client=client,
        now=NOW,
        batch_size=2,
    )
    assert client.calls == 2
    assert result["status"] == "available"
    assert result["models"][0]["locations_count"] == 3
    overview = read_json(output / "data" / "overview" / "ecmwf_ifs.json")
    assert overview["status"] == "available"
    assert len(overview["hourly"]) == 5  # 00-01 starts exactly at NOW.
    assert overview["hourly"][0]["sunshine_coverage_pct"] == 100
    assert overview["next_sunshine_window"]["expected_sunshine_minutes"] == 150
    first_grid = overview["hourly"][0]["grid_file"]
    layer = read_json(output / "data" / first_grid)
    assert len(layer["values"]) == 2
    assert layer["values"][0][0] == 50
    assert "geometry" not in layer
    assert len(read_json(output / "data" / "geography" / "grid.geojson")["features"]) == 2
    city = read_json(output / "data" / "city" / "ecmwf_ifs" / "chengdu.json")
    assert city["city"]["name"] == "成都"
    assert len(city["city"]["hourly"]) == 5
    assert result["models"][0]["model_run_at"] is not None


def test_missing_provider_never_fabricates_a_forecast(tmp_path: Path) -> None:
    output = tmp_path / "public"
    status = generate(
        output,
        cache=tmp_path / "cache",
        models=("ecmwf_ifs",),
        geography=geography_fixture(),
        client=FakeWeatherClient(fail=True),
        now=NOW,
    )
    assert status["status"] == "initializing"
    overview = read_json(output / "data" / "overview" / "ecmwf_ifs.json")
    assert overview["status"] == "initializing"
    assert overview["hourly"] == []
    assert overview["next_sunshine_window"] is None


def test_placeholder_bootstrap_has_explicit_missing_status(tmp_path: Path) -> None:
    result = generate(
        tmp_path / "public",
        cache=tmp_path / "cache",
        models=("ecmwf_ifs",),
        mode="placeholder",
        now=NOW,
    )
    assert result["status"] == "initializing"
    assert result["models"][0]["locations_count"] == 0


def test_seven_day_totals_are_not_cut_off_by_72_hour_map(tmp_path: Path) -> None:
    output = tmp_path / "public"
    result = generate(
        output,
        cache=tmp_path / "cache",
        models=("ecmwf_ifs",),
        geography=geography_fixture(),
        client=FakeWeatherClient(hours=168),
        now=NOW,
        batch_size=2,
    )
    overview = read_json(output / "data" / "overview" / "ecmwf_ifs.json")
    assert result["status"] == "available"
    assert len(overview["hourly"]) == 72
    assert len(overview["daily_sunshine_hours"]) == 7
    assert len(list((output / "data" / "grid" / "ecmwf_ifs").glob("*.json"))) == 72
    assert len(read_json(output / "data" / "city" / "ecmwf_ifs" / "chengdu.json")["city"]["hourly"]) == 168
    assert overview["model"]["forecast_end_at"].startswith("2026-11-17")
