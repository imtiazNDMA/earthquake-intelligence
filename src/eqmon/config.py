"""Shared constants. Domain language follows CONTEXT.md."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VS30_TIF = PROJECT_ROOT / "data" / "Vs30.tif"

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
