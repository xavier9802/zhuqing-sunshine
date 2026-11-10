from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
import time

import httpx

from app.catalog import ModelSpec, get_model_spec


@dataclass(frozen=True)
class WeatherLocation:
    location_id: int
    location_key: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class ModelMetadata:
    model_id: str
    model_run_at: datetime | None
    modified_at: datetime | None
    available_at: datetime | None
    data_end_time: datetime | None
    temporal_resolution_seconds: int | None
    update_interval_seconds: int | None
    raw: dict[str, Any]


def _from_unix(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_model_metadata(model_id: str, payload: dict[str, Any]) -> ModelMetadata:
    return ModelMetadata(
        model_id=model_id,
        model_run_at=_from_unix(payload.get("last_run_initialisation_time")),
        modified_at=_from_unix(payload.get("last_run_modification_time")),
        available_at=_from_unix(payload.get("last_run_availability_time")),
        data_end_time=_from_unix(payload.get("data_end_time")),
        temporal_resolution_seconds=_as_int(payload.get("temporal_resolution_seconds")),
        update_interval_seconds=_as_int(payload.get("update_interval_seconds")),
        raw=payload,
    )


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_valid_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def response_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise ValueError("Unexpected Open-Meteo response shape")


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 45,
        max_attempts: int = 5,
        http_client: httpx.Client | None = None,
        sleep=time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_attempts = max_attempts
        self._sleep = sleep
        self.client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=10),
            headers={"User-Agent": "Zhuqing-Sunshine/0.1 (+https://github.com/xavier9802/zhuqing-sunshine)"},
        )
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        retryable = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                response = self.client.get(url, params=params)
                if response.status_code in retryable:
                    if attempt == self.max_attempts - 1:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = _retry_delay(retry_after, attempt)
                    self._sleep(delay)
                    continue

                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("error") is True:
                    raise ValueError(payload.get("reason", "Open-Meteo returned an API error"))
                return payload
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt == self.max_attempts - 1:
                    raise
                self._sleep(_retry_delay(None, attempt))
            except httpx.HTTPStatusError:
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Open-Meteo request failed without a response")

    def fetch_metadata(self, model_id: str) -> ModelMetadata:
        get_model_spec(model_id)
        url = f"{self.base_url}/data/{model_id}/static/meta.json"
        payload = self._get_json(url)
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid metadata response for {model_id}")
        return parse_model_metadata(model_id, payload)

    def fetch_forecast_batch(
        self,
        model_id: str,
        locations: Iterable[WeatherLocation],
        forecast_days: int = 7,
    ) -> list[dict[str, Any]]:
        spec: ModelSpec = get_model_spec(model_id)
        batch = list(locations)
        if not batch:
            return []

        params: dict[str, Any] = {
            "latitude": ",".join(f"{item.latitude:.6f}" for item in batch),
            "longitude": ",".join(f"{item.longitude:.6f}" for item in batch),
            "hourly": ",".join(spec.hourly_variables),
            "forecast_days": forecast_days,
            "timezone": "UTC",
            "timeformat": "iso8601",
            "models": model_id,
            "cell_selection": "land",
        }
        if self.api_key:
            params["apikey"] = self.api_key

        payload = self._get_json(f"{self.base_url}/v1/ecmwf", params=params)
        items = response_items(payload)
        if len(items) != len(batch):
            raise ValueError(
                f"Open-Meteo returned {len(items)} locations for a batch of {len(batch)}"
            )
        for index, item in enumerate(items):
            hourly = item.get("hourly")
            if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
                raise ValueError(f"Missing hourly time series at batch index {index}")
        return items


def _retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.5, min(60.0, float(retry_after)))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(retry_after)
                return max(0.5, min(60.0, (parsed - datetime.now(UTC)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    return min(30.0, 1.5 * (2**attempt))
