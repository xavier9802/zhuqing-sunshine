from shapely.geometry import Polygon

from app.geography import generate_grid_cells


def test_grid_cells_are_clipped_and_weighted() -> None:
    boundary = Polygon([
        (104.0, 30.0),
        (104.5, 30.0),
        (104.5, 30.5),
        (104.0, 30.5),
        (104.0, 30.0),
    ])
    cells = generate_grid_cells(boundary, spacing_degrees=0.25)

    assert cells
    assert all(cell.area_km2 > 0 for cell in cells)
    assert all(boundary.covers(cell.geometry.representative_point()) for cell in cells)
    assert sum(cell.area_km2 for cell in cells) > 0


def test_usgs_source_without_prj_uses_documented_provisional_geographic_crs(tmp_path) -> None:
    from app.geography import source_crs_for

    shapefile = tmp_path / "sed_basins.shp"
    shapefile.touch()

    crs, basis = source_crs_for(shapefile)

    assert crs.to_epsg() == 4326
    assert "datum" in basis
    assert "provisionally" in basis
