"""Pin PROJ to rasterio's bundled database.

A system PROJ install (e.g. shipped with PostgreSQL/PostGIS) can leave a stale
``proj.db`` on the default search path that rasterio's bundled GDAL rejects,
yielding ``CRSError: The EPSG code is unknown`` when opening even a plain
EPSG:4326 GeoTIFF. This module forces PROJ_DATA/PROJ_LIB to the copy that ships
with rasterio, so the engine works regardless of what else is installed.

Import this before any rasterio/pyproj use. ``eqmon/__init__`` does so, which
covers both the running service and the test suite.
"""
from __future__ import annotations

import os
from importlib.resources import files


def pin_bundled_proj() -> None:
    try:
        proj_data = str(files("rasterio").joinpath("proj_data"))
    except (ModuleNotFoundError, FileNotFoundError, AttributeError):
        return
    if os.path.isdir(proj_data):
        # Force (not setdefault): our app requires the bundled DB, and a system
        # PROJ_LIB pointing at an incompatible proj.db is exactly what we override.
        os.environ["PROJ_DATA"] = proj_data
        os.environ["PROJ_LIB"] = proj_data


pin_bundled_proj()
