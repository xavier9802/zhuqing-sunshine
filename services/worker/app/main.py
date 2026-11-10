from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import create_schema, make_engine, make_session_factory
from app.geography import download_usgs_boundary, generate_grid_cells
from app.geonames import download_city_catalog
from app.ingest import ingest_all
from app.providers.open_meteo import OpenMeteoClient
from app.storage import persist_geography, save_geography_assets


def import_geography(settings: Settings) -> dict[str, int]:
    boundary, metadata = download_usgs_boundary(settings.data_dir)
    cities = download_city_catalog(settings.data_dir / "geography")
    cells = generate_grid_cells(boundary, settings.grid_spacing_degrees)

    save_geography_assets(
        settings.data_dir,
        boundary,
        metadata,
        cells,
        cities,
    )

    engine = make_engine(settings.database_url)
    create_schema(engine)
    session_factory = make_session_factory(engine)
    try:
        return persist_geography(
            session_factory,
            boundary,
            metadata,
            cells,
            cities,
            settings.grid_spacing_degrees,
        )
    finally:
        engine.dispose()


def run_ingestion(settings: Settings) -> list[dict[str, object]]:
    engine = make_engine(settings.database_url)
    create_schema(engine)
    session_factory = make_session_factory(engine)
    client = OpenMeteoClient(
        base_url=settings.open_meteo_base_url,
        single_runs_base_url=settings.open_meteo_single_runs_base_url,
        api_key=settings.open_meteo_api_key,
        timeout_seconds=settings.request_timeout_seconds,
        max_attempts=settings.max_attempts,
    )
    try:
        return ingest_all(
            session_factory=session_factory,
            client=client,
            model_ids=settings.model_ids,
            forecast_days=settings.forecast_days,
            batch_size=settings.batch_size,
        )
    finally:
        client.close()
        engine.dispose()


def run_ingestion_loop(settings: Settings, interval_minutes: int) -> None:
    interval_seconds = max(15, interval_minutes * 60)
    print(json.dumps({
        "event": "ingestion_loop_started",
        "interval_minutes": interval_minutes,
        "models": list(settings.model_ids),
    }, ensure_ascii=False), flush=True)
    while True:
        started_at = datetime.now(UTC)
        try:
            result = run_ingestion(settings)
            print(json.dumps({
                "event": "ingestion_cycle_complete",
                "at": datetime.now(UTC).isoformat(),
                "results": result,
            }, ensure_ascii=False), flush=True)
        except (ValueError, RuntimeError, OSError, SQLAlchemyError) as exc:
            print(json.dumps({
                "event": "ingestion_cycle_failed",
                "at": datetime.now(UTC).isoformat(),
                "error": str(exc)[:4000],
            }, ensure_ascii=False), flush=True)
        elapsed = (datetime.now(UTC) - started_at).total_seconds()
        time.sleep(max(15, interval_seconds - elapsed))


def main() -> None:
    parser = argparse.ArgumentParser(description="追晴气象数据采集工具")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "import-geography",
        help="导入 USGS 盆地边界、GeoNames 城市点和 0.25° 网格",
    )
    ingest_parser = commands.add_parser("ingest-once", help="采集指定批次的 ECMWF 单轮预报")
    ingest_parser.add_argument("--days", type=int, default=None)
    loop_parser = commands.add_parser("ingest-loop", help="按固定间隔持续采集新模型批次")
    loop_parser.add_argument("--interval-minutes", type=int, default=60)
    production_parser = commands.add_parser(
        "start-production", help="初始化地理数据并启动持续预报采集"
    )
    production_parser.add_argument("--interval-minutes", type=int, default=60)
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.command == "import-geography":
        result = import_geography(settings)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "ingest-loop":
        run_ingestion_loop(settings, args.interval_minutes)
        return
    if args.command == "start-production":
        geography_result = import_geography(settings)
        print(json.dumps({
            "event": "geography_import_complete",
            "result": geography_result,
        }, ensure_ascii=False), flush=True)
        run_ingestion_loop(settings, args.interval_minutes)
        return

    if args.days is not None:
        settings = replace(settings, forecast_days=max(1, min(15, args.days)))
    result = run_ingestion(settings)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
