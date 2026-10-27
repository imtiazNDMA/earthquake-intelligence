"""Dissolve + smooth MMI shaking-intensity bands.

The bands produced by ShakeMap-style contouring are messy: the sample layer has
322 polygons carrying 2942 interior rings, ~83% of which are slivers under
1 km2. They also overlap their neighbours by hairline slivers along shared
contour edges. This module turns that into one clean polygon per ``mmi_high``
value.

Pipeline (each step optional / tunable):

  1. repair    - make_valid() every input part
  2. dissolve  - union_all() grouped by the band field
  3. close     - buffer(+d).buffer(-d) morphological closing to heal pinholes
                 and knock the jaggedness off contour staircases
  4. declutter - drop interior rings and parts below an area threshold
  5. simplify  - Douglas-Peucker with topology preserved
  6. exclusive - subtract higher bands from lower ones so no area, and hence no
                 element, is ever counted twice

Tolerances are supplied in real-world units (metres / km2) and converted to
degrees here, because the data is stored in EPSG:4326.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import shapely
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from .config import DEFAULT_SMOOTHING, M_PER_DEG, MMI_FIELD


@dataclass
class SmoothingOptions:
    """Knobs for the dissolve stage.

    Defaults come from ``config.DEFAULT_SMOOTHING`` - that is the one place to
    change them. Requests may override individual values, but are not required
    to send any.
    """

    field: str = DEFAULT_SMOOTHING["field"]
    closing_m: float = DEFAULT_SMOOTHING["closing_m"]
    min_hole_km2: float = DEFAULT_SMOOTHING["min_hole_km2"]
    min_part_km2: float = DEFAULT_SMOOTHING["min_part_km2"]
    simplify_m: float = DEFAULT_SMOOTHING["simplify_m"]
    enforce_exclusive: bool = DEFAULT_SMOOTHING["enforce_exclusive"]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "SmoothingOptions":
        opts = cls()
        if not raw:
            return opts
        for key in ("field", "closing_m", "min_hole_km2",
                    "min_part_km2", "simplify_m", "enforce_exclusive"):
            if key in raw and raw[key] is not None:
                value = raw[key]
                if key == "field":
                    opts.field = str(value)
                elif key == "enforce_exclusive":
                    opts.enforce_exclusive = bool(value)
                else:
                    setattr(opts, key, max(0.0, float(value)))
        return opts

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "closing_m": self.closing_m,
            "min_hole_km2": self.min_hole_km2,
            "min_part_km2": self.min_part_km2,
            "simplify_m": self.simplify_m,
            "enforce_exclusive": self.enforce_exclusive,
        }


@dataclass
class Band:
    """One dissolved MMI band."""

    value: float
    geometry: BaseGeometry
    attrs: dict[str, Any] = field(default_factory=dict)
    area_km2: float = 0.0
    parts: int = 0
    holes: int = 0
    vertices: int = 0

    def stats(self) -> dict[str, Any]:
        return {
            "area_km2": round(self.area_km2, 2),
            "parts": self.parts,
            "holes": self.holes,
            "vertices": self.vertices,
        }


# --------------------------------------------------------------------------
# unit helpers - the data is in degrees, the knobs are in metres
# --------------------------------------------------------------------------

def _deg_per_m(lat_deg: float) -> tuple[float, float]:
    """Return (deg-per-metre-x, deg-per-metre-y) at a given latitude."""
    lat = math.radians(max(-89.5, min(89.5, lat_deg)))
    return 1.0 / (M_PER_DEG * max(math.cos(lat), 1e-6)), 1.0 / M_PER_DEG


def _km2_per_deg2(lat_deg: float) -> float:
    """Area of one square degree, in km2, at a given latitude."""
    lat = math.radians(max(-89.5, min(89.5, lat_deg)))
    return (M_PER_DEG / 1000.0) ** 2 * max(math.cos(lat), 1e-6)


def _mean_lat(geom: BaseGeometry) -> float:
    miny, maxy = geom.bounds[1], geom.bounds[3]
    return (miny + maxy) / 2.0


# --------------------------------------------------------------------------
# geometry cleaning primitives
# --------------------------------------------------------------------------

def _polygons(geom: BaseGeometry) -> list[Polygon]:
    """Flatten any geometry down to its polygonal parts."""
    if geom is None or geom.is_empty:
        return []
    kind = geom.geom_type
    if kind == "Polygon":
        return [geom]
    if kind == "MultiPolygon":
        return list(geom.geoms)
    if kind == "GeometryCollection":
        out: list[Polygon] = []
        for part in geom.geoms:
            out.extend(_polygons(part))
        return out
    return []


def _as_polygonal(geom: BaseGeometry) -> BaseGeometry:
    parts = _polygons(geom)
    if not parts:
        return Polygon()
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def _repair(geom: BaseGeometry) -> BaseGeometry:
    """Force a geometry valid, keeping only its polygonal component."""
    if geom is None or geom.is_empty:
        return Polygon()
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
        if not geom.is_valid:              # last resort for pathological rings
            geom = geom.buffer(0)
    return _as_polygonal(geom)


def _close(geom: BaseGeometry, distance_deg_x: float, distance_deg_y: float) -> BaseGeometry:
    """Morphological closing: dilate then erode.

    Heals pinholes and hairline gaps between adjacent contour polygons without
    materially growing the band. Uses the mean of the x/y degree scales because
    shapely buffers isotropically in coordinate space.
    """
    if distance_deg_x <= 0:
        return geom
    d = (distance_deg_x + distance_deg_y) / 2.0
    grown = geom.buffer(d, join_style="round", quad_segs=4)
    shrunk = grown.buffer(-d, join_style="round", quad_segs=4)
    return _as_polygonal(shrunk if not shrunk.is_empty else geom)


def _declutter(geom: BaseGeometry, min_hole_deg2: float, min_part_deg2: float) -> BaseGeometry:
    """Fill pinhole interior rings and drop speck islands."""
    kept: list[Polygon] = []
    for poly in _polygons(geom):
        if min_part_deg2 > 0 and poly.area < min_part_deg2:
            continue
        if min_hole_deg2 > 0 and poly.interiors:
            rings = [r for r in poly.interiors if Polygon(r).area >= min_hole_deg2]
            if len(rings) != len(poly.interiors):
                poly = Polygon(poly.exterior, rings)
        kept.append(poly)
    if not kept:
        return _as_polygonal(geom)   # never let cleaning erase a whole band
    return kept[0] if len(kept) == 1 else MultiPolygon(kept)


def _simplify(geom: BaseGeometry, tol_deg: float) -> BaseGeometry:
    if tol_deg <= 0:
        return geom
    out = geom.simplify(tol_deg, preserve_topology=True)
    return _repair(out) if not out.is_empty else geom


def _count_holes(geom: BaseGeometry) -> int:
    return sum(len(p.interiors) for p in _polygons(geom))


# --------------------------------------------------------------------------
# main entry point
# --------------------------------------------------------------------------

def dissolve_bands(
    records: Iterable[tuple[BaseGeometry, dict[str, Any]]],
    options: SmoothingOptions | None = None,
) -> tuple[list[Band], dict[str, Any]]:
    """Dissolve ``records`` on the configured field and smooth each band.

    ``records`` is an iterable of ``(geometry, attributes)``. Returns the bands
    ordered by descending MMI (strongest shaking first) plus a report describing
    what the cleaning actually removed.
    """
    opts = options or SmoothingOptions()

    grouped: dict[float, list[Polygon]] = {}
    carried: dict[float, dict[str, Any]] = {}
    raw_parts = raw_holes = skipped = 0

    for geom, attrs in records:
        value = attrs.get(opts.field)
        if value is None:
            skipped += 1
            continue
        repaired = _repair(geom)
        parts = _polygons(repaired)
        if not parts:
            skipped += 1
            continue
        raw_parts += len(parts)
        raw_holes += _count_holes(repaired)
        key = float(value)
        grouped.setdefault(key, []).extend(parts)
        # Keep the first non-geometry attributes seen for the band (colour etc.)
        if key not in carried:
            carried[key] = {k: v for k, v in attrs.items() if k != opts.field}

    if not grouped:
        raise ValueError(
            f"No usable polygons carrying field '{opts.field}'. "
            "Check the band field name."
        )

    bands: list[Band] = []
    for value, parts in grouped.items():
        merged = _repair(shapely.union_all(parts))
        lat = _mean_lat(merged)
        dx, dy = _deg_per_m(lat)
        km2_deg2 = _km2_per_deg2(lat)

        merged = _close(merged, opts.closing_m * dx, opts.closing_m * dy)
        merged = _declutter(
            merged,
            min_hole_deg2=opts.min_hole_km2 / km2_deg2 if km2_deg2 else 0.0,
            min_part_deg2=opts.min_part_km2 / km2_deg2 if km2_deg2 else 0.0,
        )
        merged = _simplify(merged, opts.simplify_m * ((dx + dy) / 2.0))
        merged = _repair(merged)

        bands.append(Band(value=value, geometry=merged, attrs=carried.get(value, {})))

    # Strongest shaking first. Differencing in this order means a cell that two
    # bands both claim is awarded to the more severe one.
    bands.sort(key=lambda b: b.value, reverse=True)

    if opts.enforce_exclusive and len(bands) > 1:
        accumulated: BaseGeometry | None = None
        for band in bands:
            if accumulated is not None and not accumulated.is_empty:
                clipped = band.geometry.difference(accumulated)
                if not clipped.is_empty:
                    band.geometry = _repair(clipped)
            accumulated = (
                band.geometry if accumulated is None
                else shapely.union_all([accumulated, band.geometry])
            )

    for band in bands:
        km2_deg2 = _km2_per_deg2(_mean_lat(band.geometry))
        band.area_km2 = band.geometry.area * km2_deg2
        band.parts = len(_polygons(band.geometry))
        band.holes = _count_holes(band.geometry)
        band.vertices = int(shapely.get_num_coordinates(band.geometry))
        shapely.prepare(band.geometry)   # speeds up the exposure predicates

    report = {
        "input_parts": raw_parts,
        "input_holes": raw_holes,
        "skipped_features": skipped,
        "bands": len(bands),
        "output_parts": sum(b.parts for b in bands),
        "output_holes": sum(b.holes for b in bands),
        "output_vertices": sum(b.vertices for b in bands),
        "options": opts.to_dict(),
    }
    return bands, report


def bands_to_geojson(bands: Sequence[Band], field: str = MMI_FIELD) -> dict[str, Any]:
    """Serialise dissolved bands as a GeoJSON FeatureCollection for the map."""
    features = []
    for band in bands:
        props = {field: band.value, **band.attrs, **band.stats()}
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": shapely.geometry.mapping(band.geometry),
        })
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3/CRS84"}},
        "features": features,
    }
