from datetime import UTC, datetime

import httpx
import pytest

from app.providers.open_meteo import (
    OpenMeteoClient,
    parse_model_metadata,
    parse_valid_time,
)


def test_metadata_parser_keeps_run_and_native_resolution() -> None:
    metadata = parse_model_metadata(
        "ecmwf_ifs025",
        {
            "last_run_initialisation_time": 1794268800,
            "last_run_availability_time": 1794276000,
            "last_run_modification_time": 1794275000,
            "data_end_time": 1794873600,
            "temporal_resolution_seconds": 10800,
            "update_interval_seconds": 21600,
        },
    )
    assert metadata.model_run_at is not None
    assert metadata.temporal_resolution_seconds == 10800
    assert metadata.update_interval_seconds == 21600


def test_naive_api_time_is_treated_as_utc() -> None:
    parsed = parse_valid_time("2026-11-10T08:00")
    assert parsed.tzinfo == UTC
    assert parsed.hour == 8


def test_client_retries_rate_limit_and_honours_retry_after() -> None:
    attempts = {"count": 0}
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenMeteoClient(
        "https://api.open-meteo.com",
        http_client=http_client,
        max_attempts=3,
        sleep=delays.append,
    )
    try:
        result = client._get_json("https://api.open-meteo.com/test")
    finally:
        http_client.close()

    assert result == {"ok": True}
    assert attempts["count"] == 2
    assert delays == [2.0]


def test_client_does_not_retry_bad_request() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, json={"error": True, "reason": "bad model"})
        )
    )
    client = OpenMeteoClient(
        "https://api.open-meteo.com",
        http_client=http_client,
        max_attempts=4,
        sleep=lambda _: pytest.fail("400 responses must not be retried"),
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            client._get_json("https://api.open-meteo.com/test")
    finally:
        http_client.close()
