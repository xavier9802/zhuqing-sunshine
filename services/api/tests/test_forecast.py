from datetime import UTC, datetime, timedelta

from app.forecast import (
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
        GridHour(t, 75, 3600, 10, 0, False),
        GridHour(t, 25, 0, 90, 0, False),
    ]
    result = aggregate_basin_hours(samples)[0]
    assert result["sunshine_minutes"] == 45
    assert result["sunshine_coverage_pct"] == 75
    assert result["data_completeness_pct"] == 100


def test_missing_grid_values_reduce_completeness_not_sunny_denominator() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t, 80, 3600, None, None, False),
        GridHour(t, 20, None, None, None, False),
    ]
    result = aggregate_basin_hours(samples)[0]
    assert result["sunshine_coverage_pct"] == 100
    assert result["data_completeness_pct"] == 80


def test_basin_window_requires_two_consecutive_hours_and_good_coverage() -> None:
    t = datetime(2026, 11, 10, 2, tzinfo=UTC)
    samples = [
        GridHour(t + timedelta(hours=0), 100, 2400, 20, 0, False),
        GridHour(t + timedelta(hours=1), 100, 2100, 25, 0, False),
        GridHour(t + timedelta(hours=2), 100, 0, 80, 0, False),
    ]
    hours = aggregate_basin_hours(samples)
    window = find_basin_sunshine_window(hours)
    assert window is not None
    assert window["starts_at"].startswith("2026-11-10T10:00:00")
    assert window["expected_sunshine_minutes"] == 37.5


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
    ]
    window = find_city_sunshine_window(rows)
    assert window is not None
    assert window["expected_sunshine_minutes"] == 36.7


def test_daily_summary_is_local_calendar_day() -> None:
    t = datetime(2026, 11, 10, 15, tzinfo=UTC)
    rows = aggregate_basin_hours([
        GridHour(t, 100, 3600, 20, 0, False),
        GridHour(t + timedelta(hours=1), 100, 1800, 30, 0, False),
    ])
    daily = aggregate_daily(rows)
    assert daily[0]["date"] == "2026-11-10"
    assert daily[0]["sunshine_hours"] == 0.9
