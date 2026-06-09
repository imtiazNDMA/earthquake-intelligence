"""One-time: convert the 15.4M-polygon Vs30 shapefile into a Cloud-Optimized
GeoTIFF. The polygons are a regular grid (a vectorized raster), so this is
lossless. Run once, then the shapefile can be archived.

Usage:
    uv run python scripts/rasterize_vs30.py
"""
from __future__ import annotations
import sys
from pathlib import Path

# src-layout: make the eqmon package importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — pins PROJ to rasterio's bundled DB before GDAL use
import fiona
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
SHP = ROOT / "Vs30_Polygons" / "Vs30_Polygons" / "Vs30_Neighbours_Polygons.shp"
OUT = ROOT / "data" / "Vs30.tif"
EXPECTED_FEATURES = 15_449_146
NODATA = -9999.0


def detect_cell_size(src) -> float:
    """Infer the grid cell size from the first feature's bounding box."""
    first = next(iter(src))
    minx, miny, maxx, maxy = shape(first["geometry"]).bounds
    dx, dy = maxx - minx, maxy - miny
    assert dx > 0 and dy > 0, "degenerate first cell"
    return float(min(dx, dy))


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with fiona.open(SHP) as src:
        minx, miny, maxx, maxy = src.bounds
        cell = detect_cell_size(src)
        width = int(round((maxx - minx) / cell))
        height = int(round((maxy - miny) / cell))
        transform = from_origin(minx, maxy, cell, cell)
        print(f"cell={cell:.6f} deg  grid={width}x{height}  bounds={src.bounds}", flush=True)

        def shapes():
            for i, feat in enumerate(src):
                val = feat["properties"].get("Vs30")
                if val is None:
                    continue
                if i % 1_000_000 == 0:
                    print(f"  ...{i:,} features", flush=True)
                yield shape(feat["geometry"]), float(val)

        print("rasterizing (one pass; the slow one-time step)...", flush=True)
        arr = rasterize(
            shapes(),
            out_shape=(height, width),
            transform=transform,
            fill=NODATA,
            dtype="float32",
            all_touched=False,
        )

    valid = int(np.count_nonzero(arr != NODATA))
    vmin = float(arr[arr != NODATA].min())
    vmax = float(arr[arr != NODATA].max())
    print(f"valid cells={valid:,} (expected ~{EXPECTED_FEATURES:,})", flush=True)
    print(f"Vs30 range=[{vmin:.1f}, {vmax:.1f}] m/s", flush=True)
    assert 0 < vmin < vmax < 5000, "Vs30 values implausible — check field mapping"
    assert valid >= EXPECTED_FEATURES * 0.95, "too many cells lost in rasterization"

    profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1,
        "dtype": "float32", "crs": "EPSG:4326", "transform": transform,
        "nodata": NODATA, "tiled": True, "blockxsize": 512, "blockysize": 512,
        "compress": "deflate", "predictor": 2,
    }
    with rasterio.open(OUT, "w", **profile) as dst:
        dst.write(arr, 1)
        dst.build_overviews([2, 4, 8, 16], Resampling.average)
    size_mb = OUT.stat().st_size / 1e6
    print(f"wrote {OUT} ({size_mb:.1f} MB)  <- from 3.5 GB shapefile", flush=True)


if __name__ == "__main__":
    main()
