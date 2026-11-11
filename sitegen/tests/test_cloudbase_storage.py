from __future__ import annotations

import json
from pathlib import Path

import httpx

from sitegen.cloudbase_storage import CloudBaseStorageClient


def test_upload_tree_uses_versioned_paths_and_public_cache_headers(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text('{"status":"available"}', encoding="utf-8")
    (tmp_path / "geography").mkdir()
    (tmp_path / "geography" / "grid.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http:
        storage = CloudBaseStorageClient(
            "env-test", "server-key", "zhuqing-data",
            public_base_url="https://cdn.example.com/zhuqing-data",
            http_client=http, sleep=lambda _seconds: None,
        )
        names = storage.upload_tree(
            tmp_path, "zhuqing/snapshots/run-1/data", workers=1
        )

    assert names == [
        "zhuqing/snapshots/run-1/data/geography/grid.geojson",
        "zhuqing/snapshots/run-1/data/status.json",
    ]
    assert len(seen) == 2
    assert all(request.method == "POST" for request in seen)
    assert all(request.headers["authorization"] == "Bearer server-key" for request in seen)
    assert all(request.headers["cache-control"] == "public, max-age=86400" for request in seen)
    assert any(request.headers["content-type"] == "application/geo+json" for request in seen)


def test_upload_json_uses_put_and_falls_back_to_post_when_missing() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "PUT":
            return httpx.Response(404, json={"message": "not found"}, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        storage = CloudBaseStorageClient(
            "env-test", "server-key", "zhuqing-data",
            public_base_url="https://cdn.example.com/zhuqing-data",
            http_client=http, sleep=lambda _seconds: None,
        )
        storage.upload_json("zhuqing/latest.json", {"data_prefix": "snapshots/run/data"})

    assert methods == ["PUT", "POST"]


def test_create_json_does_not_overwrite_existing_lock() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(409, json={"message": "already exists"}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        storage = CloudBaseStorageClient(
            "env-test", "server-key", "zhuqing-data",
            public_base_url="https://cdn.example.com/zhuqing-data",
            http_client=http, sleep=lambda _seconds: None,
        )
        created = storage.create_json("zhuqing/locks/slot.json", {"slot": "slot"})

    assert created is False


def test_get_json_returns_none_for_missing_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        storage = CloudBaseStorageClient(
            "env-test", "server-key", "zhuqing-data",
            public_base_url="https://cdn.example.com/zhuqing-data",
            http_client=http, sleep=lambda _seconds: None,
        )
        assert storage.get_json("zhuqing/latest.json") is None


def test_delete_objects_batches_at_one_hundred() -> None:
    batches: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        batches.append(json.loads(request.content)["prefixes"])
        return httpx.Response(200, json=[], request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        storage = CloudBaseStorageClient(
            "env-test", "server-key", "zhuqing-data",
            public_base_url="https://cdn.example.com/zhuqing-data",
            http_client=http, sleep=lambda _seconds: None,
        )
        storage.delete_objects([f"snapshot/{index}.json" for index in range(205)])

    assert [len(batch) for batch in batches] == [100, 100, 5]
