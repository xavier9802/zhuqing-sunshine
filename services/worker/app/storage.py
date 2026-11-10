from __future__ import annotations

import json
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.geography import BOUNDARY_SLUG, GridCell
from app.models import ForecastLocation, RegionBoundary


def persist_geography(
    session_factory,
    boundary_geometry,
    boundary_metadata: dict[str, object],
    cells: list[GridCell],
    cities: list[dict[str, object]],
    grid_spacing_degrees: float,
) -> dict[str, int]:
    with session_factory() as session:
        boundary = (
            session.query(RegionBoundary)
            .filter(RegionBoundary.slug == BOUNDARY_SLUG)
            .one_or_none()
        )
        if boundary is None:
            boundary = RegionBoundary(
                slug=BOUNDARY_SLUG,
                name="四川盆地",
                boundary_type="structural_sedimentary_basin_proxy",
                source_name=str(boundary_metadata["source_name"]),
                source_url=str(boundary_metadata["source_url"]),
                source_scale_denominator=int(boundary_metadata["source_scale_denominator"]),
                source_map_year=int(boundary_metadata["source_map_year"]),
                source_dataset_year=int(boundary_metadata["source_dataset_year"]),
                source_crs=str(boundary_metadata["source_crs"]),
                metadata_json=boundary_metadata,
                geometry=from_shape(boundary_geometry, srid=4326),
            )
            session.add(boundary)
            session.flush()
        else:
            boundary.metadata_json = boundary_metadata
            boundary.geometry = from_shape(boundary_geometry, srid=4326)
            boundary.source_crs = str(boundary_metadata["source_crs"])

        grid_count = 0
        for cell in cells:
            record = (
                session.query(ForecastLocation)
                .filter(ForecastLocation.location_key == cell.location_key)
                .one_or_none()
            )
            values = {
                "location_type": "grid",
                "name_zh": None,
                "name_en": cell.location_key,
                "latitude": cell.latitude,
                "longitude": cell.longitude,
                "area_km2": cell.area_km2,
                "grid_spacing_degrees": grid_spacing_degrees,
                "region_boundary_id": boundary.id,
                "source_metadata": {
                    "grid_i": cell.grid_i,
                    "grid_j": cell.grid_j,
                    "grid_spacing_degrees": grid_spacing_degrees,
                    "source_boundary": BOUNDARY_SLUG,
                },
                "geometry": from_shape(
                    Point(cell.longitude, cell.latitude), srid=4326
                ),
                "cell_geometry": from_shape(cell.geometry, srid=4326),
            }
            if record is None:
                session.add(ForecastLocation(location_key=cell.location_key, **values))
            else:
                for key, value in values.items():
                    setattr(record, key, value)
            grid_count += 1

        city_count = 0
        for city in cities:
            key = f"city:{city['slug']}"
            record = (
                session.query(ForecastLocation)
                .filter(ForecastLocation.location_key == key)
                .one_or_none()
            )
            values = {
                "location_type": "city",
                "name_zh": str(city["name_zh"]),
                "name_en": str(city["name_en"]),
                "geoname_id": int(city["geoname_id"]),
                "latitude": float(city["latitude"]),
                "longitude": float(city["longitude"]),
                "area_km2": None,
                "grid_spacing_degrees": None,
                "region_boundary_id": boundary.id,
                "source_metadata": city,
                "geometry": from_shape(
                    Point(float(city["longitude"]), float(city["latitude"])),
                    srid=4326,
                ),
                "cell_geometry": None,
            }
            if record is None:
                session.add(ForecastLocation(location_key=key, **values))
            else:
                for field, value in values.items():
                    setattr(record, field, value)
            city_count += 1

        session.commit()

    return {"grid_cells": grid_count, "cities": city_count}


def save_geography_assets(
    data_dir: Path,
    boundary_geometry,
    boundary_metadata: dict[str, object],
    cells: list[GridCell],
    cities: list[dict[str, object]],
) -> None:
    from app.geography import write_boundary_geojson, write_grid_geojson

    geography_dir = data_dir / "geography"
    write_boundary_geojson(
        boundary_geometry,
        boundary_metadata,
        geography_dir / "sichuan_basin_boundary.geojson",
    )
    write_grid_geojson(cells, geography_dir / "grid_cells.geojson")
    (geography_dir / "cities.json").write_text(
        json.dumps(cities, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
