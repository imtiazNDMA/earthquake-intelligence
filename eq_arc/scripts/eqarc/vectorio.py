"""Reading MMI polygon sources (shapefile, GeoJSON, zipped shapefile).

Everything is normalised to EPSG:4326 lon/lat, which is what the element
layers and the cached indexes use.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Iterator

import shapely
from osgeo import ogr, osr
from shapely import wkb as shapely_wkb
from shapely.geometry.base import BaseGeometry

from .config import find_gdal_data

ogr.UseExceptions()
osr.UseExceptions()

# Belt and braces: PROJ latches its search path the first time it initialises,
# so if anything imported osgeo before our env vars were applied, push the
# bundled proj.db in through the API as well.
_gdal_data = find_gdal_data()
if _gdal_data is not None:
    osr.SetPROJSearchPath(str(_gdal_data / "proj"))

WGS84 = osr.SpatialReference()
WGS84.ImportFromEPSG(4326)
WGS84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

VECTOR_SUFFIXES = {".shp", ".geojson", ".json", ".gpkg", ".gml", ".kml", ".fgb"}
SHAPEFILE_SIDECARS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


def _transform_for(layer: ogr.Layer) -> osr.CoordinateTransformation | None:
    """Build a transform to WGS84, or None when the layer already is WGS84."""
    src = layer.GetSpatialRef()
    if src is None:
        return None                      # assume the coordinates are already lon/lat
    src = src.Clone()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    if src.IsSame(WGS84):
        return None
    return osr.CoordinateTransformation(src, WGS84)


def read_features(source: str | Path, layer_name: str | None = None
                  ) -> Iterator[tuple[BaseGeometry, dict[str, Any]]]:
    """Yield ``(shapely geometry, attributes)`` in WGS84 from any OGR source."""
    source = str(source)
    ds = ogr.Open(source, 0)
    if ds is None:
        raise ValueError(f"Could not open vector source: {source}")

    layer = ds.GetLayerByName(layer_name) if layer_name else ds.GetLayer(0)
    if layer is None:
        raise ValueError(f"No layer '{layer_name}' in {source}")

    transform = _transform_for(layer)
    defn = layer.GetLayerDefn()
    names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]

    layer.ResetReading()
    for feature in layer:
        geom = feature.GetGeometryRef()
        if geom is None:
            continue
        geom = geom.Clone()
        if transform is not None:
            geom.Transform(transform)
        try:
            shape = shapely_wkb.loads(bytes(geom.ExportToWkb()))
        except Exception:
            continue
        if shape.is_empty:
            continue
        attrs = {name: feature.GetField(name) for name in names}
        yield shape, attrs

    ds = None


def geojson_to_records(payload: dict[str, Any]
                       ) -> Iterator[tuple[BaseGeometry, dict[str, Any]]]:
    """Turn an inline GeoJSON payload into the same ``(geom, attrs)`` records."""
    if not isinstance(payload, dict):
        raise ValueError("GeoJSON payload must be an object")

    kind = payload.get("type")
    if kind == "FeatureCollection":
        features = payload.get("features") or []
    elif kind == "Feature":
        features = [payload]
    elif kind in {"Polygon", "MultiPolygon", "GeometryCollection"}:
        features = [{"type": "Feature", "geometry": payload, "properties": {}}]
    else:
        raise ValueError(f"Unsupported GeoJSON type: {kind!r}")

    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        try:
            shape = shapely.geometry.shape(geometry)
        except Exception:
            continue
        if shape.is_empty:
            continue
        yield shape, dict(feature.get("properties") or {})


def extract_zip(zip_path: str | Path, dest_dir: str | Path) -> Path:
    """Unpack a zipped shapefile and return the vector file inside it."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            # Flatten, and refuse path traversal out of dest.
            name = Path(member.filename).name
            if not name:
                continue
            with zf.open(member) as src, open(dest / name, "wb") as dst:
                dst.write(src.read())
    return find_vector_file(dest)


def find_vector_file(directory: str | Path) -> Path:
    """Pick the vector file from a directory, preferring .shp."""
    directory = Path(directory)
    candidates = [p for p in directory.rglob("*") if p.suffix.lower() in VECTOR_SUFFIXES]
    if not candidates:
        raise ValueError("No shapefile or GeoJSON found in the uploaded data")
    candidates.sort(key=lambda p: (p.suffix.lower() != ".shp", len(str(p))))
    return candidates[0]


def check_shapefile_set(shp_path: str | Path) -> list[str]:
    """Return the sidecar files missing next to a .shp (.shx/.dbf are fatal)."""
    shp = Path(shp_path)
    if shp.suffix.lower() != ".shp":
        return []
    return [s for s in (".shx", ".dbf") if not shp.with_suffix(s).exists()]
