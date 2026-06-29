"""Convert a GeoJSON FeatureCollection of MMI band polygons into a zipped
Esri Shapefile (WGS84). Stateless and HTTP-agnostic so it can be unit-tested
without the API layer."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import fiona
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

_SCHEMA = {
    "geometry": "MultiPolygon",
    "properties": {"mmi_low": "int", "mmi_high": "int", "color": "str"},
}
_LAYER = "mmi_bands"


def featurecollection_to_shapefile_zip(fc: dict) -> bytes:
    """Return zip bytes containing mmi_bands.{shp,shx,dbf,prj,cpg}.

    Non-polygon features are skipped. Raises ValueError if nothing writable
    remains.
    """
    records = []
    for feat in (fc or {}).get("features", []) or []:
        geom_obj = (feat or {}).get("geometry")
        if not geom_obj or geom_obj.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = shape(geom_obj)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        props = (feat.get("properties") or {})
        records.append({
            "geometry": mapping(geom),
            "properties": {
                "mmi_low": props.get("mmi_lower"),
                "mmi_high": props.get("mmi_upper"),
                "color": props.get("color"),
            },
        })

    if not records:
        raise ValueError("no polygonal features to export")

    with TemporaryDirectory() as td:
        shp_path = Path(td) / f"{_LAYER}.shp"
        with fiona.open(
            str(shp_path), "w", driver="ESRI Shapefile",
            schema=_SCHEMA, crs="EPSG:4326", encoding="utf-8",
        ) as dst:
            dst.writerecords(records)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in sorted(Path(td).glob(f"{_LAYER}.*")):
                zf.write(part, arcname=part.name)
    return buf.getvalue()
