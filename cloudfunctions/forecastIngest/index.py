"""CloudBase scheduled entry point for the Zhuqing forecast pipeline."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path

import requests
from cloudbase_client import cloudbase

from sitegen.build import generate

LOG = logging.getLogger("zhuqing.cloudbase")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def _upload_file(local_path: Path, object_id: str) -> dict:
    """Upload one generated static snapshot using CloudBase Storage HTTP API."""
    info_list = cloudbase.request(
        "POST",
        "/v1/storages/get-objects-upload-info",
        json=[{"objectId": object_id}],
    )
    if not info_list:
        raise RuntimeError(f"CloudBase returned no upload ticket for {object_id}")
    info = info_list[0]
    headers = {
        "Authorization": info["authorization"],
        "X-Cos-Security-Token": info["token"],
        "X-Cos-Meta-Fileid": info["cloudObjectMeta"],
        "Content-Type": mimetypes.guess_type(local_path.name)[0] or "application/octet-stream",
    }
    with local_path.open("rb") as stream:
        response = requests.put(info["uploadUrl"], headers=headers, data=stream, timeout=120)
    response.raise_for_status()
    return {"object_id": object_id, "size": local_path.stat().st_size}


def _publish_snapshot(output_dir: Path) -> list[dict]:
    root = output_dir / "data"
    if not (root / "status.json").is_file():
        raise RuntimeError("Forecast generator did not produce data/status.json")
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    if not any(model.get("status") == "available" for model in status.get("models", [])):
        raise RuntimeError("No live model succeeded; keeping the previous published snapshot")

    # Upload all data under a versioned prefix first. Update the small manifest last;
    # readers can use the manifest's snapshot_id to avoid observing a half-written run.
    snapshot_id = status.get("last_checked_at", "unknown").replace(":", "").replace("-", "")
    prefix = f"zhuqing/snapshots/{snapshot_id}"
    uploaded = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            relative = path.relative_to(output_dir).as_posix()
            uploaded.append(_upload_file(path, f"{prefix}/{relative}"))

    manifest = {
        "status": status["status"],
        "snapshot_id": snapshot_id,
        "published_at": status.get("last_checked_at"),
        "data_prefix": prefix,
        "models": status.get("models", []),
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as tmp:
        json.dump(manifest, tmp, ensure_ascii=False, separators=(",", ":"))
        manifest_path = Path(tmp.name)
    try:
        uploaded.append(_upload_file(manifest_path, "zhuqing/data/manifest.json"))
    finally:
        manifest_path.unlink(missing_ok=True)
    return uploaded


def main(event, context):
    """Timer-triggered full-basin ingest; supports manual test invocation."""
    env_id = os.getenv("TENCENTCLOUD_RUNENV") or os.getenv("TCB_ENV")
    if not env_id:
        raise RuntimeError("CloudBase environment is missing; configure TCB_ENV")
    output = Path(tempfile.mkdtemp(prefix="zhuqing-output-"))
    cache = Path("/tmp/zhuqing-cache")
    try:
        status = generate(
            output=output,
            cache=cache,
            mode="live",
            batch_size=int(os.getenv("FORECAST_BATCH_SIZE", "20")),
        )
        available = [m for m in status.get("models", []) if m.get("status") == "available"]
        if not available:
            raise RuntimeError("All ECMWF models failed; previous manifest remains unchanged")
        uploaded = _publish_snapshot(output)
        result = {
            "ok": True,
            "status": status["status"],
            "available_models": [m["model_id"] for m in available],
            "uploaded_files": len(uploaded),
            "uploaded_bytes": sum(item["size"] for item in uploaded),
            "published_at": status.get("last_checked_at"),
        }
        LOG.info("CloudBase forecast snapshot published: %s", json.dumps(result, ensure_ascii=False))
        return result
    finally:
        import shutil
        shutil.rmtree(output, ignore_errors=True)
