from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import httpx
import shapefile
from pyproj import CRS, Transformer
from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

USGS_BOUNDARY_URL = (
    "https://pubs.usgs.gov/of/2000/of00-047/SHP_files/sed_basins.ZIP"
)
USGS_REPORT_URL = "https://pubs.usgs.gov/of/2000/of00-047/"
USGS_METADATA_URL = "https://geo-nsdi.er.usgs.gov/metadata/open-file/00-47/sed_basins.faq.html"
BOUNDARY_SLUG = "sichuan-basin-structural-sedimentary-proxy"


@dataclass(frozen=True)
class GridCell:
    location_key: str
    latitude: float
    longitude: float
    area_km2: float
    grid_i: int
    grid_j: int
    geometry: Any


def _safe_extract(archive_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    root = target_dir.resolve()
    with ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (target_dir / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError("Unsafe path found in USGS boundary archive")
            archive.extract(member, target_dir)


def _prj_for(shp_path: Path) -> Path | None:
    return next(
        (
            path for path in shp_path.parent.iterdir()
            if path.stem.casefold() == shp_path.stem.casefold()
            and path.suffix.casefold() == ".prj"
        ),
        None,
    )


def source_crs_for(shp_path: Path) -> tuple[CRS, str]:
    prj_path = _prj_for(shp_path)
    if prj_path is not None:
        return (
            CRS.from_wkt(prj_path.read_text(encoding="utf-8")),
            "Read from the shapefile .prj sidecar.",
        )

    # USGS FGDC FAQ confirms geographic latitude/longitude in decimal degrees,
    # but does not declare a geodetic datum. WGS84 is therefore an explicit,
    # provisional map-display assumption, not a claim about source survey datum.
    return (
        CRS.from_epsg(4326),
        (
            "The source archive has no .prj. USGS metadata FAQ states geographic "
            "latitude/longitude in decimal degrees but does not identify the datum; "
            "WGS84 is assigned provisionally for regional display and is not "
            "survey-grade geodetic provenance."
        ),
    )


def download_usgs_boundary(data_dir: Path) -> tuple[Any, dict[str, object]]:
    downloads = data_dir / "downloads"
    extract_dir = data_dir / "geography" / "usgs_sedimentary_basins"
    downloads.mkdir(parents=True, exist_ok=True)
    archive_path = downloads / "usgs_sedimentary_basins.zip"

    with httpx.Client(timeout=httpx.Timeout(120, connect=20)) as client:
        response = client.get(USGS_BOUNDARY_URL)
        response.raise_for_status()
        archive_path.write_bytes(response.content)

    _safe_extract(archive_path, extract_dir)
    shp_files = [
        path for path in extract_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".shp"
    ]

    matches: list[tuple[Any, dict[str, object], Path]] = []
    for shp_path in shp_files:
        reader = shapefile.Reader(str(shp_path))
        field_names = [field[0] for field in reader.fields[1:]]
        name_field = next(
            (field for field in field_names if field.casefold() == "name"),
            None,
        )
        if name_field is None:
            reader.close()
            continue

        for item in reader.iterShapeRecords():
            attributes = dict(zip(field_names, item.record))
            if str(attributes.get(name_field, "")).strip().casefold() == "sichuan basin":
                matches.append(
                    (shape(item.shape.__geo_interface__), attributes, shp_path)
                )
        reader.close()

    if len(matches) != 1:
        raise ValueError(
            f"Expected one Sichuan Basin feature in USGS archive; found {len(matches)}"
        )

    geometry, attributes, shp_path = matches[0]
    source_crs, source_crs_basis = source_crs_for(shp_path)
    target_crs = CRS.from_epsg(4326)
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    geometry = transform(transformer.transform, geometry)
    if not geometry.is_valid:
        geometry = make_valid(geometry)

    if geometry.geom_type == "GeometryCollection":
        polygons = [
            part for part in geometry.geoms
            if part.geom_type in {"Polygon", "MultiPolygon"}
        ]
        geometry = unary_union(polygons)

    if isinstance(geometry, Polygon):
        geometry = MultiPolygon([geometry])
    elif geometry.geom_type == "MultiPolygon":
        geometry = MultiPolygon(list(geometry.geoms))
    else:
        raise ValueError(f"Unexpected boundary geometry type: {geometry.geom_type}")

    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Sichuan Basin boundary is empty or invalid after reprojection")

    metadata: dict[str, object] = {
        "slug": BOUNDARY_SLUG,
        "name": "四川盆地",
        "boundary_type": "structural_sedimentary_basin_proxy",
        "source_name": "USGS Open-File Report 00-047",
        "source_url": USGS_REPORT_URL,
        "source_download_url": USGS_BOUNDARY_URL,
        "source_scale_denominator": 5_000_000,
        "source_map_year": 1992,
        "source_dataset_year": 2000,
        "source_crs": source_crs.to_string(),
        "source_crs_basis": source_crs_basis,
        "source_metadata_url": USGS_METADATA_URL,
        "target_crs": "EPSG:4326",
        "source_attributes": attributes,
        "boundary_caveat": (
            "Generalized structural sedimentary basin boundary digitized from a "
            "1:5,000,000 map; it is an initial operational proxy, not a definitive "
            "geomorphological or administrative boundary. The source archive has "
            "no .prj and its metadata does not specify the geodetic datum; WGS84 is "
            "used provisionally for regional display only."
        ),
    }
    return geometry, metadata


def generate_grid_cells(boundary: Any, spacing_degrees: float = 0.25) -> list[GridCell]:
    if spacing_degrees <= 0:
        raise ValueError("spacing_degrees must be greater than zero")

    min_lon, min_lat, max_lon, max_lat = boundary.bounds
    i_start = int(min_lon // spacing_degrees) - 1
    i_end = int(max_lon // spacing_degrees) + 1
    j_start = int(min_lat // spacing_degrees) - 1
    j_end = int(max_lat // spacing_degrees) + 1

    equal_area = CRS.from_epsg(6933)
    to_equal_area = Transformer.from_crs(
        CRS.from_epsg(4326), equal_area, always_xy=True
    ).transform

    cells: list[GridCell] = []
    for i in range(i_start, i_end + 1):
        for j in range(j_start, j_end + 1):
            cell_polygon = box(
                i * spacing_degrees,
                j * spacing_degrees,
                (i + 1) * spacing_degrees,
                (j + 1) * spacing_degrees,
            )
            clipped = boundary.intersection(cell_polygon)
            if clipped.is_empty:
                continue

            if clipped.geom_type == "GeometryCollection":
                polygons = [
                    part for part in clipped.geoms
                    if part.geom_type in {"Polygon", "MultiPolygon"}
                ]
                clipped = unary_union(polygons)
            if clipped.is_empty or clipped.area <= 0:
                continue

            sample = clipped.representative_point()
            area_km2 = transform(to_equal_area, clipped).area / 1_000_000
            if area_km2 <= 0:
                continue

            if clipped.geom_type == "Polygon":
                clipped = MultiPolygon([clipped])
            elif clipped.geom_type == "MultiPolygon":
                clipped = MultiPolygon(list(clipped.geoms))
            else:
                continue

            cells.append(
                GridCell(
                    location_key=f"grid:{i}:{j}",
                    latitude=float(sample.y),
                    longitude=float(sample.x),
                    area_km2=float(area_km2),
                    grid_i=i,
                    grid_j=j,
                    geometry=clipped,
                )
            )

    return cells


def write_boundary_geojson(
    geometry: Any,
    metadata: dict[str, object],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    feature = {
        "type": "Feature",
        "geometry": mapping(geometry),
        "properties": metadata,
    }
    output_path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": [feature]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def write_grid_geojson(cells: list[GridCell], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features = [
        {
            "type": "Feature",
            "geometry": mapping(cell.geometry),
            "properties": {
                "location_key": cell.location_key,
                "latitude": cell.latitude,
                "longitude": cell.longitude,
                "area_km2": cell.area_km2,
                "grid_i": cell.grid_i,
                "grid_j": cell.grid_j,
            },
        }
        for cell in cells
    ]
    output_path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
