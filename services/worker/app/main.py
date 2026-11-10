from __future__ import annotations

import argparse
import json

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


def main() -> None:
    parser = argparse.ArgumentParser(description="追晴气象数据采集工具")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("import-geography", help="导入 USGS 盆地边界、GeoNames 城市点和 0.25° 网格")
    ingest_parser = commands.add_parser("ingest-once", help="采集一次 IFS / AIFS 预报")
    ingest_parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.command == "import-geography":
        result = import_geography(settings)
    else:
        if args.days is not None:
            settings = Settings(
                **{
                    **settings.__dict__,
                    "forecast_days": max(1, min(15, args.days)),
                }
            )
        result = run_ingestion(settings)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
