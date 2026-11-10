from datetime import UTC, date, datetime

from shapely.geometry import box

from sitegen.backtest import (
    Station,
    _binary_metrics,
    parse_observation,
    parse_sky_cover,
    parse_station_catalog,
    sample_run_dates,
    select_stations,
)


def test_parse_metar_sky_cover_categories() -> None:
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 CLR 18/10 Q1018") == 0
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 FEW020 SCT040 18/10 Q1018") == 43.75
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 BKN015 OVC040 18/10 Q1018") == 100
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 CAVOK 18/10 Q1018") == 26
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 18/10 Q1018") is None


def test_parse_observation_uses_weather_and_visibility_fields() -> None:
    row = parse_observation(
        datetime(2025, 6, 15, 8, tzinfo=UTC),
        "METAR ZUUU 150800Z 02004MPS 4000 -RA SCT020 18/10 Q1018",
        4.0,
        0.0,
    )
    assert row is not None
    assert row.cloud_cover_pct == 43.75
    assert row.visibility_m == 4000
    assert row.precipitation is True


def test_parse_station_catalog_csv() -> None:
    content = (
        "ID,LATITUDE,LONGITUDE,ELEVATION,NAME,WMO ID,ICAO\n"
        "CHM00056294,30.667,104.017,508,CHENGDU,56294,ZUUU\n"
    )
    rows = parse_station_catalog(content)
    assert len(rows) == 1
    assert rows[0].station_id == "CHM00056294"
    assert rows[0].icao == "ZUUU"


def test_parse_station_catalog_fixed_width() -> None:
    line = f"{'CHM00056294':<11} {30.667:8.3f} {104.017:9.3f} {508.0:6.1f} {'':2}{'CHENGDU':<30}{'':9}{'56294':<5}{'ZUUU':<4}"
    rows = parse_station_catalog(line)
    assert len(rows) == 1
    assert rows[0].name == "CHENGDU"
    assert rows[0].wmo_id == "56294"
    assert rows[0].icao == "ZUUU"


def test_sample_dates_are_spread_across_period() -> None:
    dates = sample_run_dates(date(2024, 4, 1), date(2025, 12, 31), 5)
    assert len(dates) == 5
    assert dates[0] == date(2024, 4, 15)
    assert dates[-1] == date(2025, 12, 15)


def test_station_selection_prefers_inside_basin_and_spreads_points() -> None:
    stations = [
        Station("CHM00056294", "CHENGDU", 30.667, 104.017, 508, "56294", "ZUUU"),
        Station("CHM00057516", "CHONGQING", 29.72, 106.64, 351, "57516", "ZUCK"),
        Station("CHM00056187", "MIANYANG", 31.43, 104.74, 523, "56187", None),
        Station("CHM00056029", "OUTSIDE", 35.0, 105.0, 500, "56029", None),
    ]
    selected = select_stations(stations, box(102, 27, 110, 34), 3)
    assert len(selected) == 3
    assert all(item.name != "OUTSIDE" for item in selected)


def test_binary_metrics_do_not_invent_probability() -> None:
    samples = [
        {"forecast_condition": "sunny", "observed_condition": "sunny"},
        {"forecast_condition": "mostly_sunny", "observed_condition": "cloudy"},
        {"forecast_condition": "overcast", "observed_condition": "sunny"},
        {"forecast_condition": "rainy", "observed_condition": "rainy"},
    ]
    result = _binary_metrics(samples)
    assert result["station_days"] == 4
    assert result["tp"] == 1
    assert result["fp"] == 1
    assert result["fn"] == 1
    assert result["tn"] == 1
    assert result["accuracy_pct"] == 50
    assert result["precision_pct"] == 50
    assert result["recall_pct"] == 50
    assert result["f1_pct"] == 50
