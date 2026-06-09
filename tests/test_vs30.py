import numpy as np
import rasterio
from rasterio.transform import from_origin

from eqmon.vs30 import Grid, load_grid


def _write_tiny_tif(path):
    # 2x2 grid, 1-degree cells, origin at (70E, 32N), one nodata cell
    arr = np.array([[400.0, 760.0], [-9999.0, 1000.0]], dtype="float32")
    transform = from_origin(70.0, 32.0, 1.0, 1.0)
    profile = dict(driver="GTiff", height=2, width=2, count=1,
                   dtype="float32", crs="EPSG:4326", transform=transform,
                   nodata=-9999.0)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def test_grid_provides_cell_center_coordinates(tmp_path):
    p = tmp_path / "tiny.tif"
    _write_tiny_tif(p)
    grid = load_grid(p)
    # cell centers: columns at 70.5, 71.5 ; rows at 31.5, 30.5 (north-down)
    assert np.allclose(grid.lon[0], [70.5, 71.5])
    assert np.allclose(grid.lat[:, 0], [31.5, 30.5])


def test_nodata_filled_with_default_vs30(tmp_path):
    p = tmp_path / "tiny.tif"
    _write_tiny_tif(p)
    grid = load_grid(p, default_vs30=760.0)
    assert grid.vs30[1, 0] == 760.0  # was nodata
    assert grid.vs30[0, 0] == 400.0  # unchanged
    assert not np.any(grid.vs30 == -9999.0)
