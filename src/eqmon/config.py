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

# Automated ingest interval (minutes).
INGEST_INTERVAL_MINUTES = 15
