from datetime import UTC, datetime, timedelta

from sitegen.forecast import (
    CityHour,
    GridHour,
    aggregate_basin_hours,
    aggregate_daily,
    find_basin_sunshine_window,
    find_city_sunshine_window,
)


def test_basin_coverage_uses_clipped_cell_area_weights() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t, 75, 3600, 10, 0, False, low_cloud_cover_pct=10),
        GridHour(t, 25, 0, 90, 0, False, low_cloud_cover_pct=90),
    ]
    result = aggregate_basin_hours(samples)[0]
    assert result["sunshine_minutes"] == 45
    assert result["sunshine_coverage_pct"] == 75
    assert result["data_completeness_pct"] == 100


def test_missing_grid_values_reduce_completeness_not_sunny_denominator() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t, 80, 3600, 10, 0, False, low_cloud_cover_pct=10),
        GridHour(t, 20, None, None, None, False),
    ]
    result = aggregate_basin_hours(samples)[0]
    assert result["sunshine_coverage_pct"] == 100
    assert result["data_completeness_pct"] == 80


def test_basin_window_requires_two_consecutive_hours_and_good_coverage() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t + timedelta(hours=0), 100, 2400, 20, 0, False, low_cloud_cover_pct=15),
        GridHour(t + timedelta(hours=1), 100, 2100, 25, 0, False, low_cloud_cover_pct=20),
        GridHour(t + timedelta(hours=2), 100, 0, 80, 0, False, low_cloud_cover_pct=80),
    ]
    hours = aggregate_basin_hours(samples)
    window = find_basin_sunshine_window(hours)
    assert window is None  # only two consecutive acceptable bright hours


def test_basin_window_does_not_bridge_a_missing_hour() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t, 100, 3600, 10, 0, False),
        GridHour(t + timedelta(hours=2), 100, 3600, 10, 0, False),
    ]
    assert find_basin_sunshine_window(aggregate_basin_hours(samples)) is None


def test_city_window_uses_two_consecutive_effective_sunshine_hours() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    rows = [
        CityHour(t, 2000, 30, 0, 18, False),
        CityHour(t + timedelta(hours=1), 2400, 20, 0, 19, False),
        CityHour(t + timedelta(hours=2), 2200, 25, 0, 20, False),
    ]
    window = find_city_sunshine_window(rows)
    assert window is not None
    assert window["expected_sunshine_minutes"] == 110.0


def test_daily_summary_is_local_calendar_day() -> None:
    t = datetime(2026, 11, 10, 13, tzinfo=UTC)
    rows = aggregate_basin_hours([
        GridHour(t, 100, 3600, 20, 0, False, low_cloud_cover_pct=15),
        GridHour(t + timedelta(hours=1), 100, 1800, 30, 0, False, low_cloud_cover_pct=25),
    ])
    daily = aggregate_daily(rows)
    assert daily[0]["date"] == "2026-11-10"
    assert daily[0]["sunshine_hours"] == 1.5


def test_basin_window_returns_the_entire_contiguous_sunshine_period() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t + timedelta(hours=i), 100, 2400, 20, 0, False, low_cloud_cover_pct=15)
        for i in range(3)
    ]
    window = find_basin_sunshine_window(aggregate_basin_hours(samples))
    assert window is not None
    assert window["starts_at"].startswith("2026-11-10T09:00:00")
    assert window["ends_at"].startswith("2026-11-10T12:00:00")
    assert window["expected_sunshine_minutes"] == 120


def test_daily_total_ignores_hours_below_data_completeness_threshold() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    rows = aggregate_basin_hours([
        GridHour(t, 100, 3600, 20, 0, False, low_cloud_cover_pct=15),
        GridHour(t + timedelta(hours=1), 20, 3600, 20, 0, False, low_cloud_cover_pct=15),
        GridHour(t + timedelta(hours=1), 80, None, None, None, False),
    ])
    daily = aggregate_daily(rows)
    assert daily[0]["sunshine_hours"] == 1.0


def test_daily_summary_assigns_midnight_timestamp_to_previous_hour_day() -> None:
    # 16:00 UTC is 00:00 the next day in Sichuan; the preceding-hour value
    # belongs to 23:00–00:00 on the previous local calendar day.
    t = datetime(2026, 11, 10, 16, tzinfo=UTC)
    daily = aggregate_daily(aggregate_basin_hours([
        GridHour(t, 100, 1800, 20, 0, False, low_cloud_cover_pct=15),
    ]))
    assert daily[0]["date"] == "2026-11-10"
    assert daily[0]["sunshine_hours"] == 0.5

def test_low_cloud_and_total_cloud_gate_clear_basin_window() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    # Sunshine duration alone would qualify these hours, but persistent low
    # cloud must prevent a false "sunny" window.
    samples = [
        GridHour(t + timedelta(hours=i), 100, 3600, 95, 0, False, low_cloud_cover_pct=90)
        for i in range(4)
    ]
    hours = aggregate_basin_hours(samples)
    assert all(row["sunshine_coverage_pct"] == 100 for row in hours)
    assert all(row["bright_sky_coverage_pct"] == 0 for row in hours)
    assert find_basin_sunshine_window(hours) is None


def test_clear_sky_coverage_requires_complete_cloud_and_rain_diagnostics() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    rows = [
        GridHour(t, 100, 3600, 10, None, False, low_cloud_cover_pct=5),
    ]
    hour = aggregate_basin_hours(rows)[0]
    assert hour["clear_sky_coverage_pct"] == 0
    assert hour["cloud_diagnostic_completeness_pct"] == 0


def test_daily_classification_distinguishes_clear_and_overcast_days() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    clear = aggregate_daily(aggregate_basin_hours([
        GridHour(t + timedelta(hours=i), 100, 3600, 10, 0, False, low_cloud_cover_pct=5, is_day=True)
        for i in range(5)
    ]))[0]
    cloudy = aggregate_daily(aggregate_basin_hours([
        GridHour(t + timedelta(hours=i), 100, 3600, 95, 0, False, low_cloud_cover_pct=90, is_day=True)
        for i in range(5)
    ]))[0]
    assert clear["condition"] == "sunny"
    assert cloudy["condition"] == "overcast"
