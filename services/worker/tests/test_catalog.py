from app.catalog import get_model_spec


def test_ifs_hres_native_step_changes_with_lead_time() -> None:
    spec = get_model_spec("ecmwf_ifs")
    assert spec.native_step_seconds(24) == 3600
    assert spec.native_step_seconds(90) == 3600
    assert spec.native_step_seconds(91) == 10800
    assert spec.native_step_seconds(145) == 21600


def test_open_data_ifs_is_three_hourly_then_six_hourly() -> None:
    spec = get_model_spec("ecmwf_ifs025")
    assert spec.native_step_seconds(72) == 10800
    assert spec.native_step_seconds(144) == 10800
    assert spec.native_step_seconds(145) == 21600


def test_aifs_is_six_hourly() -> None:
    spec = get_model_spec("ecmwf_aifs025_single")
    assert spec.native_step_seconds(12) == 21600
    assert spec.native_step_seconds(168) == 21600
