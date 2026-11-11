"""Small PG-mode CloudBase Storage HTTP client used by the forecast publisher."""

from __future__ import annotations

import json
import logging
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

LOG = logging.getLogger("zhuqing.cloudbase")
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class CloudBaseStorageError(RuntimeError):
    """Raised when a CloudBase Storage operation cannot be completed."""


class CloudBaseStorageClient:
    """Upload immutable forecast snapshots to a public PG-mode Storage bucket.

    The service-role API key is only used server-side. Public reads are granted
    separately by the bucket's RLS policy; this client never exposes the key.
    """

    def __init__(
        self,
        env_id: str,
        service_role_key: str,
        bucket_id: str,
        *,
        public_base_url: str,
        api_base_url: str | None = None,
        http_client: httpx.Client | None = None,
        attempts: int = 4,
        sleep=time.sleep,
    ) -> None:
        if not env_id.strip():
            raise ValueError("CloudBase environment ID is required")
        if not service_role_key.strip():
            raise ValueError("CloudBase service-role API key is required")
        if not bucket_id.strip():
            raise ValueError("CloudBase Storage bucket ID is required")
        if attempts < 1:
            raise ValueError("attempts must be at least 1")

        self.env_id = env_id
        self.bucket_id = bucket_id
        if not public_base_url.strip():
            raise ValueError("CloudBase Storage public base URL is required")
        self.public_base_url = public_base_url.rstrip("/")
        self.base_url = (
            api_base_url or f"https://{env_id}.api.tcloudbasegateway.com"
        ).rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {service_role_key}",
            "Accept": "application/json",
        }
        self.attempts = attempts
        self.sleep = sleep
        self.client = http_client or httpx.Client(timeout=60)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _object_url(self, object_name: str) -> str:
        if not object_name or object_name.startswith("/") or ".." in object_name.split("/"):
            raise ValueError("Invalid CloudBase Storage object name")
        bucket = quote(self.bucket_id, safe="")
        key = quote(object_name, safe="/")
        return f"{self.base_url}/v1/storages/object/{bucket}/{key}"

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        authenticated = kwargs.pop("authenticated", True)
        headers = dict(self.headers) if authenticated else {}
        headers.update(kwargs.pop("headers", {}) or {})
        for attempt in range(self.attempts):
            try:
                response = self.client.request(
                    method, url, headers=headers, **kwargs
                )
            except httpx.TransportError:
                if attempt + 1 >= self.attempts:
                    raise
                delay = min(2 ** attempt, 8)
                LOG.warning(
                    "CloudBase Storage transport failure (%s/%s); retrying in %ss",
                    attempt + 1, self.attempts, delay,
                )
                self.sleep(delay)
                continue

            if response.status_code not in RETRYABLE_STATUS or attempt + 1 >= self.attempts:
                return response

            delay = min(2 ** attempt, 8)
            LOG.warning(
                "CloudBase Storage HTTP %s (%s/%s); retrying in %ss",
                response.status_code, attempt + 1, self.attempts, delay,
            )
            self.sleep(delay)

        raise CloudBaseStorageError(f"Request retry loop exhausted: {method} {url}")

    def get_json(self, object_name: str) -> dict[str, Any] | None:
        # PG Storage's public-object download route is served through the stable
        # getPublicUrl/CDN base; the management API route is intentionally not used.
        url = f"{self.public_base_url}/{quote(object_name, safe='/')}"
        response = self._request(
            "GET",
            url,
            authenticated=False,
            params={"v": str(int(time.time()))},
            headers={"Cache-Control": "no-cache"},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise CloudBaseStorageError(
                f"Expected a JSON object at {object_name}"
            )
        return value

    def create_json(self, object_name: str, value: dict[str, Any]) -> bool:
        """Create an object without overwriting; return False if it already exists."""
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        response = self._request(
            "POST",
            self._object_url(object_name),
            content=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
            },
        )
        if response.status_code == 409:
            return False
        response.raise_for_status()
        return True

    def upload_bytes(
        self,
        object_name: str,
        content: bytes,
        *,
        content_type: str,
        cache_control: str,
        overwrite: bool = False,
    ) -> None:
        method = "PUT" if overwrite else "POST"
        response = self._request(
            method,
            self._object_url(object_name),
            content=content,
            headers={
                "Content-Type": content_type,
                "Cache-Control": cache_control,
            },
        )
        if overwrite and response.status_code == 404:
            response = self._request(
                "POST",
                self._object_url(object_name),
                content=content,
                headers={
                    "Content-Type": content_type,
                    "Cache-Control": cache_control,
                },
            )
        response.raise_for_status()

    def upload_json(
        self,
        object_name: str,
        value: dict[str, Any],
        *,
        cache_control: str = "public, max-age=60",
    ) -> None:
        body = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        self.upload_bytes(
            object_name,
            body,
            content_type="application/json; charset=utf-8",
            cache_control=cache_control,
            overwrite=True,
        )

    @staticmethod
    def _content_type(path: Path) -> str:
        if path.suffix.lower() == ".geojson":
            return "application/geo+json"
        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    def upload_tree(
        self,
        local_root: Path,
        object_prefix: str,
        *,
        cache_control: str = "public, max-age=86400",
        workers: int = 6,
    ) -> list[str]:
        root = local_root.resolve()
        files = sorted(path for path in root.rglob("*") if path.is_file())
        if not files:
            raise CloudBaseStorageError("Refusing to publish an empty forecast snapshot")

        jobs: list[tuple[Path, str]] = []
        for path in files:
            relative = path.resolve().relative_to(root).as_posix()
            object_name = f"{object_prefix.rstrip('/')}/{relative}"
            jobs.append((path, object_name))

        def upload_one(job: tuple[Path, str]) -> str:
            path, object_name = job
            self.upload_bytes(
                object_name,
                path.read_bytes(),
                content_type=self._content_type(path),
                cache_control=cache_control,
            )
            return object_name

        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            uploaded = list(executor.map(upload_one, jobs))
        return uploaded

    def delete_objects(self, object_names: list[str]) -> int:
        """Delete exact object names in PG Storage batches of at most 100."""
        if not object_names:
            return 0
        url = (
            f"{self.base_url}/v1/storages/object/"
            f"{quote(self.bucket_id, safe='')}"
        )
        deleted = 0
        for offset in range(0, len(object_names), 100):
            batch = object_names[offset : offset + 100]
            response = self._request(
                "DELETE", url, json={"prefixes": batch}
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                deleted += len(payload)
            elif isinstance(payload, dict):
                items = payload.get("data", payload.get("objects", []))
                deleted += len(items) if isinstance(items, list) else len(batch)
            else:
                deleted += len(batch)
        return deleted
