"""Shared constants. Domain language follows CONTEXT.md."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VS30_TIF = PROJECT_ROOT / "data" / "Vs30.tif"

# TileServerGL instance serving per-district building footprints (one .mbtiles
# per district, vector layer id "buildings"). Typically a WSL host IP, which
# moves between machines and reboots — hence env-configurable rather than baked
# into the frontend. See src/eqmon/buildings.py.
BUILDINGS_TILE_URL = os.getenv("BUILDINGS_TILE_URL", "http://172.19.112.1:8081").rstrip("/")

# Buildings render only at/above this zoom. A national view of all 161 districts
# is millions of polygons; this floor is the load-bearing guard against it.
BUILDINGS_MIN_ZOOM = 12

# Default Site Condition (CONTEXT.md): used where the Vs30 grid has no value.
DEFAULT_VS30 = 760.0

# Coverage Region bounding box (minx, miny, maxx, maxy) in WGS84 degrees:
# Iran (west) through China/Nepal (east), covering PK/IN/AF/IR/CN/NP.
COVERAGE_BBOX = (44.0, 8.0, 105.0, 56.0)

# Primary Focus Country viewport (Pakistan) for the map.
MAP_CENTER = (30.4, 69.3)  # (lat, lon)
MAP_ZOOM = 5

# MMI band thresholds for filled contours (Modified Mercalli classes).
MMI_BAND_LEVELS = [2, 3, 4, 5, 6, 7, 8, 9, 10]

# Modified Mercalli intensity classes: MMI integer -> (Roman numeral, perceived-
# shaking descriptor). Source of truth for classification/labels, mirroring
# classification_range.md (the USGS ShakeMap scheme). Class I is "not felt" and
# is never contoured (surface shaking below MMI 2 is left unshaded); it is listed
# here so consumers can label the un-shaded background consistently.
MMI_CLASSES = {
    1: ("I", "Not Felt"),
    2: ("II", "Weak"),
    3: ("III", "Weak"),
    4: ("IV", "Light"),
    5: ("V", "Moderate"),
    6: ("VI", "Strong"),
    7: ("VII", "Very Strong"),
    8: ("VIII", "Severe"),
    9: ("IX", "Violent"),
    10: ("X", "Extreme"),
}


def mmi_class_label(level: int) -> str:
    """Human label for an MMI class, e.g. 6 -> "VI (Strong)"."""
    roman, name = MMI_CLASSES.get(int(level), (str(level), ""))
    return f"{roman} ({name})" if name else roman

# Automated ingest intervals. Base tick runs every 1 min; PMD (full-catalog)
# is ingested every 5th tick since it has no incremental API.
INGEST_INTERVAL_MINUTES = 1
PMD_INTERVAL_MULTIPLIER = 5

# --- Seismicity analytics tunables ---
GRID_CELL_DEG = 0.25              # hotspot grid cell size (degrees)
MC_MIN_N = 50                     # min events to estimate Mc
BVALUE_MIN_N = 50                 # min events (>= Mc) to report a b-value
MC_CORRECTION = 0.2               # MAXC completeness correction
MAG_BIN_WIDTH = 0.1               # magnitude bin width
DEPTH_CRUSTAL_MAX_KM = 35.0       # crustal < 35 km
DEPTH_INTERMEDIATE_MAX_KM = 70.0  # intermediate 35-70 km; deep > 70 km
