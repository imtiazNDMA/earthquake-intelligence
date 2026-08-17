"""Load the Vs30 COG into a Grid: the value array plus per-cell lon/lat
coordinate arrays. Nodata cells are filled with the Default Site Condition."""
from __future__ import annotations
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
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
    source_sha256: str  # exact COG bytes used to build this grid
    default_vs30: float  # fill value applied to nodata/invalid cells


def load_grid(path: Path | str = VS30_TIF, default_vs30: float = DEFAULT_VS30) -> Grid:
    source_sha256 = _file_sha256(Path(path))
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
    return Grid(
        vs30=vs30, lon=lon, lat=lat, transform=transform,
        source_sha256=source_sha256, default_vs30=float(default_vs30),
    )


@lru_cache(maxsize=1)
def get_grid() -> Grid:
    """Process-wide grid shared by HTTP routes and deterministic tool adapters."""
    path = Path(os.environ.get("EQMON_VS30_TIF", str(VS30_TIF)))
    return load_grid(path)


def reset_grid_cache() -> None:
    """Clear the configured-grid cache so an environment override takes effect."""
    get_grid.cache_clear()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
