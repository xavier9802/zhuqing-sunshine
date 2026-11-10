from pathlib import Path

from sitegen.consensus import build_consensus


def test_consensus_requires_two_models_and_reports_agreement(tmp_path: Path) -> None:
    import json

    (tmp_path / "data" / "overview").mkdir(parents=True)
    daily = [
        {"date": "2026-11-13", "condition": "sunny", "sunshine_hours": 7.0,
         "mean_cloud_cover_pct": 20, "mean_low_cloud_cover_pct": 10,
         "mean_clear_sky_coverage_pct": 70, "mean_bright_sky_coverage_pct": 80,
         "sunny_score": 78, "clear_hours": 5, "bright_hours": 6, "rain_hours": 0}
    ]
    for model in ("ecmwf_ifs", "ecmwf_ifs025"):
        (tmp_path / "data" / "overview" / f"{model}.json").write_text(
            json.dumps({"daily_sunshine_hours": daily}), encoding="utf-8"
        )
    statuses = [
        {"model_id": "ecmwf_ifs", "model_name": "IFS HRES", "status": "available"},
        {"model_id": "ecmwf_ifs025", "model_name": "IFS 0.25", "status": "available"},
        {"model_id": "ecmwf_aifs025_single", "model_name": "AIFS", "status": "waiting"},
    ]
    result = build_consensus(tmp_path, statuses, "2026-11-10T12:00:00+08:00")
    assert result["status"] == "available"
    assert result["best_sunny_day"]["date"] == "2026-11-13"
    assert result["best_sunny_day"]["agreement_count"] == 2
    assert result["best_sunny_day"]["agreement_pct"] == 100
    assert result["method"]["minimum_models_for_recommendation"] == 2
