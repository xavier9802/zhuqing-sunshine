from datetime import UTC, date, datetime

from shapely.geometry import box

from sitegen.backtest import (
    Station,
    _binary_metrics,
    _common_cloud_model_comparison,
    _common_solar_model_comparison,
    parse_observation,
    parse_sky_cover,
    parse_sky_cover_code,
    parse_sky_cover_from_row,
    parse_station_catalog,
    parse_synop_precipitation,
    parse_synop_sky_cover,
    sample_quality_gate,
    sample_run_dates,
    select_stations,
)


def test_parse_metar_sky_cover_categories() -> None:
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 CLR 18/10 Q1018") == 0
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 FEW020 SCT040 18/10 Q1018") == 43.75
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 BKN015 OVC040 18/10 Q1018") == 100
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 9999 CAVOK 18/10 Q1018") == 26
    assert parse_sky_cover("METAR ZUUU 150000Z 02004MPS 0200 VV002 18/10 Q1018") == 100
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
    line = f"{'CHM00056294':<11} {30.667:8.3f} {104.017:9.3f} {508.0:6.1f}{'':4}{'CHENGDU':<30}{'':9}{'56294':<5} {'ZUUU':<4}"
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

def test_parse_numeric_ghcnh_sky_cover_codes() -> None:
    assert parse_sky_cover_code("0") == 0
    assert parse_sky_cover_code("2") == 25
    assert parse_sky_cover_code("4") == 50
    assert parse_sky_cover_code("8") == 100
    assert parse_sky_cover_code("9") == 100
    assert parse_sky_cover_code("99") is None


def test_parse_ghcnh_overall_and_summed_sky_cover_fields() -> None:
    assert parse_sky_cover_from_row({"sky_condition": "2/1/0"}) == 25
    assert parse_sky_cover_from_row({
        "sky_cover_summation_1": "2",
        "sky_cover_summation_2": "5",
        "sky_cover_summation_3": "99",
    }) == 62.5
    assert parse_sky_cover_from_row({"sky_cover_layer_1": "FEW"}) == 18.75


def test_parse_observation_can_use_native_ghcnh_cloud_field_without_metar() -> None:
    row = parse_observation(
        datetime(2025, 6, 15, 8, tzinfo=UTC),
        "",
        10.0,
        0.0,
        sky_cover_pct=parse_sky_cover_code("2"),
    )
    assert row is not None
    assert row.cloud_cover_pct == 25
    assert row.precipitation is False


def test_quality_gate_rejects_sparse_or_single_station_samples() -> None:
    rows = [
        {"station_id": "CHI0000ZUTF", "lead_day": lead, "target_date": "2025-07-16"}
        for lead in (1, 2, 3) for _ in range(80)
    ]
    quality = sample_quality_gate(rows)
    assert quality["sufficient_for_research_review"] is False
    assert quality["checks"]["at_least_200_station_days"] is True
    assert quality["checks"]["at_least_4_verified_stations"] is False
    assert quality["calibrated_sunshine_probability"] is False


def test_quality_gate_requires_spatial_seasonal_and_lead_coverage() -> None:
    seasons = ["2025-01-15", "2025-04-15", "2025-07-15", "2025-10-15"]
    rows = [
        {"station_id": station, "lead_day": lead, "target_date": target_date}
        for station in ("CHI0000ZUTF", "CHI0000ZUCK", "CHM00056287", "CHM00056492")
        for lead in (1, 2, 3)
        for target_date in seasons
        for _ in range(5)
    ]
    quality = sample_quality_gate(rows)
    assert quality["sufficient_for_research_review"] is True
    assert quality["calibrated_sunshine_probability"] is False
    assert len(quality["represented_seasons"]) == 4


def test_station_selection_includes_all_available_icao_network_stations() -> None:
    stations = [
        Station("CHI0000ZUUU", "CHENGDU SHUANGLIU", 30.57, 103.94, 495, None, None),
        Station("CHI0000ZUTF", "CHENGDU TIANFU", 30.31, 104.45, 446, None, None),
        Station("CHI0000ZUCK", "CHONGQING JIANGBEI", 29.72, 106.64, 416, None, None),
        Station("CHM00056492", "YIBIN", 28.8, 104.6, 350, "56492", None),
        Station("CHM00057306", "LANGZHONG", 31.58, 105.97, 370, "57306", None),
    ]
    selected = select_stations(stations, box(102, 27, 110, 34), 3)
    assert {station.station_id for station in selected} == {
        "CHI0000ZUUU", "CHI0000ZUTF", "CHI0000ZUCK"
    }

def test_parse_fm12_synop_total_cloud_amount() -> None:
    # AAXX YYGGiw IIiii iRiXhVV Nddff ...; N is total cloud amount in oktas.
    assert parse_synop_sky_cover("AAXX 15004 57083 42960 00000 10123") == 0
    assert parse_synop_sky_cover("AAXX 15004 57083 42960 43210 10123") == 50
    assert parse_synop_sky_cover("AAXX 15004 57083 42960 83210 10123") == 100
    assert parse_synop_sky_cover("AAXX 15004 57083 42960 93210 10123") == 100
    assert parse_synop_sky_cover("AAXX 15004 57083 42960") is None


def test_parse_fm12_synop_present_weather() -> None:
    assert parse_synop_precipitation("AAXX 15004 57083 42960 43210 10123 20012 30000 40123 50001 60000 70000 80000") is False
    assert parse_synop_precipitation("AAXX 15004 57083 42960 43210 10123 20012 30000 40123 50001 60000 70000 80000") is False
    assert parse_synop_precipitation("AAXX 15004 57083 42960 43210 10123 20012 30000 40123 50001 60000 75000 80000") is True


def test_parse_observation_uses_fm12_cloud_and_weather_groups() -> None:
    row = parse_observation(
        datetime(2025, 6, 15, 8, tzinfo=UTC),
        "AAXX 15004 57083 42960 83210 10123 20012 30000 40123 50001 60000 75000 80000",
        None,
        None,
    )
    assert row is not None
    assert row.cloud_cover_pct == 100
    assert row.precipitation is True

def test_parse_noaa_compact_synop_report() -> None:
    # NOAA GHCNh REM uses SYN<encoded header> followed by iRiXhVV Nddff.
    assert parse_synop_sky_cover("SYN12457516 04850 32902 10266 76000") == 37.5
    assert parse_synop_sky_cover("SYN12457516 04850 /2902 10266 76000") is None
    assert parse_synop_precipitation("SYN12457516 04850 /2902 10266 76000") is True
    assert parse_synop_precipitation("SYN12457516 04850 /2902 10266 70000") is False

def test_common_cloud_model_comparison_uses_identical_cases() -> None:
    sample = {
        "station_id": "CHI0000ZUCK",
        "target_date": "2025-06-16",
        "lead_day": 1,
        "forecast_condition": "sunny",
        "observed_condition": "mostly_sunny",
        "cloud_cover_abs_error_pct": 12.0,
        "forecast_mean_cloud_cover_pct": 25.0,
        "observed_mean_cloud_cover_pct": 37.0,
    }
    result = _common_cloud_model_comparison({
        "ecmwf_ifs": {1: [sample], 2: [], 3: []},
        "ecmwf_ifs025": {1: [sample], 2: [], 3: []},
    })
    assert result["common_case_count"] == 1
    assert result["by_model"]["ecmwf_ifs"]["1"]["station_days"] == 1


def test_common_solar_model_comparison_uses_identical_cases() -> None:
    sample = {
        "grid_key": "30.5,104.5",
        "target_date": "2025-06-16",
        "lead_day": 1,
        "forecast_shortwave_mj_m2": 18.0,
        "nasa_power_shortwave_mj_m2": 16.0,
    }
    result = _common_solar_model_comparison({
        "ecmwf_ifs": {1: [sample], 2: [], 3: []},
        "ecmwf_aifs025_single": {1: [sample], 2: [], 3: []},
    })
    assert result["common_case_count"] == 1
    assert result["by_model"]["ecmwf_ifs"]["1"]["mae_mj_m2"] == 2.0

