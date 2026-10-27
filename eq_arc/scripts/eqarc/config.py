"""Paths, layer registry and GDAL environment setup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LAYERS_DIR = DATA_DIR / "layers" / "ARC_layers"
SAMPLE_MMI = DATA_DIR / "sample_mmi" / "mmi_bands.shp"
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"
WEB_DIR = ROOT / "scripts" / "web"

# --- element layers -------------------------------------------------------
# kind: "point"  -> counted by point-in-polygon
#       "line"   -> counted by line/polygon intersection
#       "pop"    -> point layer, but aggregated by summing age/sex columns
LAYERS = {
    "airports":    {"kind": "point", "label": "Airports"},
    "bridges":     {"kind": "point", "label": "Bridges"},
    "hospitals":   {"kind": "point", "label": "Hospitals"},
    "schools":     {"kind": "point", "label": "Schools"},
    "settlements": {"kind": "point", "label": "Settlements"},
    "roads":       {"kind": "line",  "label": "Roads"},
    "population":  {"kind": "pop",   "label": "Population"},
}

# Display / response ordering.
LAYER_ORDER = [
    "population", "settlements", "hospitals", "schools",
    "roads", "bridges", "airports",
]

# Age-band suffixes used by the population layer (glob_f_0 .. glob_f_80).
# The cache builder verifies these against the real schema and uses the
# intersection, so a layer with extra/fewer bands still works.
AGE_BANDS = [0, 1] + list(range(5, 85, 5))

MMI_FIELD = "mmi_high"

# --------------------------------------------------------------------------
# Which directories a `source: "path"` request is allowed to read from.
#
# This matters once the server is bound to 0.0.0.0: without it, anyone on the
# network could ask the API to open any OGR-readable file on this machine.
# Add more roots here if your MMI layers live outside the project, e.g.
#
#     ALLOWED_PATH_ROOTS = [ROOT, Path(r"D:\shared\shakemaps")]
#
# Set it to an empty list to turn the check off entirely (localhost only).
# --------------------------------------------------------------------------
ALLOWED_PATH_ROOTS = [ROOT]

# --------------------------------------------------------------------------
# Smoothing / dissolve settings.
#
# These live on the server. The web page does not send them - edit them here
# and restart the server to change how the MMI bands are cleaned up.
#
#   field             attribute the bands are dissolved on
#   closing_m         morphological closing distance, metres. Heals pinholes
#                     and takes the staircase edge off the contours.
#   min_hole_km2      interior rings smaller than this are filled in
#   min_part_km2      islands smaller than this are dropped
#   simplify_m        Douglas-Peucker tolerance, metres
#   enforce_exclusive subtract higher bands from lower ones so the bands never
#                     overlap. Affects reported area and the map geometry only,
#                     never the counts.
# --------------------------------------------------------------------------
DEFAULT_SMOOTHING = {
    "field": MMI_FIELD,
    "closing_m": 600.0,
    "min_hole_km2": 1.0,
    "min_part_km2": 0.5,
    "simplify_m": 200.0,
    "enforce_exclusive": True,
}

# Approximate metres-per-degree of latitude; used to convert user-facing
# tolerances (metres, km^2) into the degree units the data is stored in.
M_PER_DEG = 111_320.0


def layer_path(name: str) -> Path:
    return LAYERS_DIR / f"{name}.geojson"


def cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.npz"


def find_gdal_data() -> Path | None:
    """Locate the GDAL/PROJ data directory bundled inside the installed wheel."""
    for base in (Path(sys.prefix), Path(sys.base_prefix)):
        osgeo_data = base / "Lib" / "site-packages" / "osgeo" / "data"
        if (osgeo_data / "proj" / "proj.db").is_file():
            return osgeo_data
    return None


def configure_gdal() -> None:
    """Point PROJ/GDAL at the data bundled inside the venv's osgeo package.

    These are set unconditionally rather than with ``setdefault``. GIS-heavy
    Windows boxes very often already export a machine-wide ``PROJ_LIB`` /
    ``GDAL_DATA`` from an unrelated install (OSGeo4W, QGIS, PostGIS). Those
    point at a proj.db built for a different PROJ version - or at a directory
    that no longer exists - and deferring to them makes every CRS lookup fail
    with ``PROJ: proj_create_from_database: Cannot find proj.db``.
    """
    osgeo_data = find_gdal_data()
    if osgeo_data is None:
        return
    proj_dir = osgeo_data / "proj"
    os.environ["PROJ_LIB"] = str(proj_dir)
    os.environ["PROJ_DATA"] = str(proj_dir)
    os.environ["GDAL_DATA"] = str(osgeo_data)
