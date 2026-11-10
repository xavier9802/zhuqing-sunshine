from datetime import date

from sitegen.nasa_power import parse_nasa_power_daily_payload


def test_parse_nasa_power_daily_radiation_payload() -> None:
    payload = {
        "header": {"fill_value": -999},
        "geometry": {"type": "Point", "coordinates": [104.5, 30.5]},
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {
                    "20240601": 22.5,
                    "20240602": -999,
                    "20240603": 61.0,
                    "20240604": 0.0,
                    "20240605": float("nan"),
                    "bad-date": 12.0,
                }
            }
        },
    }

    grid_key, values = parse_nasa_power_daily_payload(
        payload, latitude=30.32, longitude=104.45
    )

    assert grid_key == "30.500,104.500"
    assert values == {
        date(2024, 6, 1): 22.5,
        date(2024, 6, 4): 0.0,
    }


def test_parse_nasa_power_daily_radiation_fallback_grid_key() -> None:
    payload = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {"20240601": 18.0}
            }
        }
    }

    grid_key, values = parse_nasa_power_daily_payload(
        payload, latitude=30.32, longitude=104.45
    )

    assert grid_key == "30.320,104.450"
    assert values[date(2024, 6, 1)] == 18.0

def test_parse_nasa_power_converts_kwh_to_mj() -> None:
    payload = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {"20240601": 3.5}
            }
        },
        "parameters": {
            "ALLSKY_SFC_SW_DWN": {"units": "kWh/m^2/day"}
        },
    }

    _, values = parse_nasa_power_daily_payload(
        payload, latitude=30.32, longitude=104.45
    )

    assert values[date(2024, 6, 1)] == 12.6
\n