from app.ingest import _float_at, _sha256


def test_missing_values_remain_missing_not_zero() -> None:
    assert _float_at({"sunshine_duration": [None, 1200]}, "sunshine_duration", 0) is None
    assert _float_at({"sunshine_duration": [None, 1200]}, "sunshine_duration", 1) == 1200.0
    assert _float_at({}, "precipitation", 0) is None


def test_payload_hash_is_stable() -> None:
    assert _sha256({"a": 1, "b": 2}) == _sha256({"b": 2, "a": 1})
