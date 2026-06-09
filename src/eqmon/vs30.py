"""Load the Vs30 COG into a Grid: the value array plus per-cell lon/lat
coordinate arrays. Nodata cells are filled with the Default Site Condition."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from .config import DEFAULT_VS30, VS30_TIF


@dataclass(frozen=True)
class Grid:
    vs30: np.ndarray  # (H, W) float32, no nodata sentinels remain
    lon: np.ndarray   # (H, W) float64, cell-center longitude
    lat: np.ndarray   # (H, W) float64, cell-center latitude
    transform: object  # rasterio Affine, for mapping grid -> geo in contouring


def load_grid(path: Path | str = VS30_TIF, default_vs30: float = DEFAULT_VS30) -> Grid:
    with rasterio.open(path) as ds:
        vs30 = ds.read(1).astype("float32")
        nodata = ds.nodata
        transform = ds.transform
        rows = np.arange(ds.height)
        cols = np.arange(ds.width)
        # cell-center pixel coords -> geographic
        # NOTE: rasterio.transform.xy with integer row/col already returns
        # cell centers (adds 0.5 internally). Using +0.5 here would shift by
        # an extra half pixel. We also reshape because rasterio 1.5.x flattens
        # 2-D array inputs to 1-D output.
        col_grid, row_grid = np.meshgrid(cols, rows)
        lon, lat = rasterio.transform.xy(transform, row_grid, col_grid)
        lon = np.asarray(lon, dtype="float64").reshape(ds.height, ds.width)
        lat = np.asarray(lat, dtype="float64").reshape(ds.height, ds.width)

    if nodata is not None:
        vs30 = np.where(vs30 == np.float32(nodata), np.float32(default_vs30), vs30)
    # guard against zero/negative which would break log10
    vs30 = np.where(vs30 <= 0, np.float32(default_vs30), vs30)
    return Grid(vs30=vs30, lon=lon, lat=lat, transform=transform)
