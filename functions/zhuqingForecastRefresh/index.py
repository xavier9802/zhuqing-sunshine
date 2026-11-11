"""CloudBase scheduled forecast refresh for Zhuqing."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sitegen.build import DEFAULT_MODELS, generate
from sitegen.cloudbase_storage import CloudBaseStorageClient

LOG = logging.getLogger("zhuqing.cloudbase.function")
ROOT_PREFIX = "zhuqing"
LOCK_TTL = timedelta(minutes=30)


def _slot_id(now: datetime) -> str:
    hour = (now.hour // 4) * 4
    return now.replace(hour=hour, minute=0, second=0, microsecond=0).strftime(
        "%Y%m%dT%H00Z"
    )


def _acquire_lock(client: CloudBaseStorageClient, slot: str, now: datetime) -> str | None:
    lock_name = f"{ROOT_PREFIX}/locks/{slot}.json"
    lock_data = {"started_at": now.isoformat(), "slot": slot}
    if client.create_json(lock_name, lock_data):
        return lock_name

    existing = client.get_json(lock_name)
    if existing:
        try:
            started_at = datetime.fromisoformat(str(existing["started_at"]))
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            if now - started_at.astimezone(UTC) <= LOCK_TTL:
                LOG.warning("A forecast refresh is already running for slot %s", slot)
                return None
        except (KeyError, TypeError, ValueError):
            LOG.warning("Found an invalid forecast lock for slot %s; replacing it", slot)

    client.delete_objects([lock_name])
    if not client.create_json(lock_name, lock_data):
        LOG.warning("Could not acquire forecast lock for slot %s", slot)
        return None
    return lock_name


def main(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Timer entry point; can also be invoked manually from the CloudBase console."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    env_id = os.getenv("TCB_ENV_ID", "").strip()
    service_role_key = os.getenv("TCB_SERVICE_ROLE_KEY", "").strip()
    bucket_id = os.getenv("TCB_STORAGE_BUCKET", "zhuqing-data").strip()
    public_base_url = os.getenv("TCB_STORAGE_PUBLIC_BASE_URL", "").strip()
    if not env_id or not service_role_key or not public_base_url:
        raise RuntimeError(
            "Set TCB_ENV_ID, TCB_SERVICE_ROLE_KEY and TCB_STORAGE_PUBLIC_BASE_URL in the CloudBase function config"
        )

    client = CloudBaseStorageClient(
        env_id=env_id,
        service_role_key=service_role_key,
        bucket_id=bucket_id,
        public_base_url=public_base_url,
        api_base_url=os.getenv("TCB_API_BASE_URL") or None,
    )
    now = datetime.now(UTC)
    slot = _slot_id(now)
    lock_name: str | None = None
    try:
        lock_name = _acquire_lock(client, slot, now)
        if lock_name is None:
            return {"ok": True, "skipped": True, "reason": "refresh already running"}

        with tempfile.TemporaryDirectory(prefix="zhuqing-refresh-") as temp_dir:
            root = Path(temp_dir)
            output = root / "public"
            # Cloud Function /tmp may survive warm invocations. It is only a cache;
            # the build pipeline always validates the cached source files.
            cache = Path("/tmp/zhuqing-cache")
            result = generate(
                output=output,
                cache=cache,
                models=DEFAULT_MODELS,
                mode="live",
                now=now,
                batch_size=25,
            )
            available = [
                model for model in result.get("models", [])
                if model.get("status") == "available"
            ]
            if not available:
                raise RuntimeError(
                    "All ECMWF models failed; preserving the last published snapshot"
                )

            data_dir = output / "data"
            if not (data_dir / "status.json").is_file():
                raise RuntimeError("Forecast pipeline did not create data/status.json")

            run_id = now.strftime("%Y%m%dT%H%M%SZ")
            data_prefix = f"{ROOT_PREFIX}/snapshots/{run_id}/data"
            previous_manifest = client.get_json(f"{ROOT_PREFIX}/latest.json") or {}
            old_previous = previous_manifest.get("previous_object_paths", [])
            previous_paths = previous_manifest.get("object_paths", [])
            if not isinstance(old_previous, list):
                old_previous = []
            if not isinstance(previous_paths, list):
                previous_paths = []

            object_paths = client.upload_tree(
                data_dir,
                data_prefix,
                cache_control="public, max-age=86400",
                workers=6,
            )
            manifest = {
                "schema_version": 1,
                "run_id": run_id,
                "generated_at": now.isoformat(),
                "data_prefix": data_prefix,
                "status": result["status"],
                "models": result["models"],
                "object_count": len(object_paths),
                "object_paths": object_paths,
                "previous_object_paths": previous_paths,
                "source": "Open-Meteo ECMWF Single Runs API",
            }
            # The pointer is written last: clients never switch to an incomplete run.
            client.upload_json(
                f"{ROOT_PREFIX}/latest.json",
                manifest,
                cache_control="public, max-age=60",
            )

            # Keep the current and immediately previous complete snapshots for
            # rollback/debugging; prune the snapshot that was already two runs old.
            if old_previous:
                try:
                    removed = client.delete_objects(old_previous)
                    LOG.info("Pruned %s objects from the two-runs-old snapshot", removed)
                except Exception:
                    LOG.exception("Published successfully but old snapshot cleanup failed")

            summary = {
                "ok": True,
                "run_id": run_id,
                "status": result["status"],
                "available_models": [model["model_id"] for model in available],
                "object_count": len(object_paths),
                "data_prefix": data_prefix,
            }
            LOG.info("Published forecast snapshot: %s", json.dumps(summary, ensure_ascii=False))
            return summary
    finally:
        if lock_name:
            try:
                client.delete_objects([lock_name])
            except Exception:
                LOG.exception("Could not release forecast lock %s", lock_name)
        client.close()
