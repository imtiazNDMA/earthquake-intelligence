"""Turn an MMI grid into filled contour bands as GeoJSON. Uses contourpy's
filled-contour algorithm, maps pixel coordinates to geographic coordinates via
the raster affine transform, and tags each band with an MMI range and color.

This is what makes the data servable: a 15M-cell surface collapses to a handful
of band polygons (tens of KB), losslessly derived from the full-res grid."""
from __future__ import annotations

import numpy as np
from contourpy import contour_generator, FillType
from shapely.geometry import Polygon, mapping

# A real Vs30 grid varies cell-to-cell, so raw bands shatter into thousands of
# pixel-scale slivers (~MBs of GeoJSON). Simplifying each band's rings and
# dropping sub-threshold slivers cuts the payload by ~10x with no visible change
# at regional zoom. Defaults are in degrees; the Vs30 grid cell is ~0.0083 deg.
_SIMPLIFY_DEG = 0.005       # ~0.6 cell: collapses staircase pixel edges
_MIN_AREA_DEG2 = 2.5e-4     # ~3.6 cells: prunes noise specks, keeps real bands

# USGS ShakeMap-style MMI palette (lower-bound -> hex).
_MMI_COLORS = {
    2: "#bfccff", 3: "#a0e6ff", 4: "#80ffff", 5: "#7aff93",
    6: "#ffff00", 7: "#ffc800", 8: "#ff9100", 9: "#ff0000", 10: "#c80000",
}


def _ring_to_lonlat(points: np.ndarray, start: int, end: int, transform) -> list[list[float]]:
    """Convert a ring slice from pixel (col, row) coords to [lon, lat] pairs."""
    ring_pts = points[start:end]
    xs = ring_pts[:, 0]  # col -> x direction
    ys = ring_pts[:, 1]  # row -> y direction
    lon, lat = transform * (xs, ys)
    return [[float(a), float(b)] for a, b in zip(np.atleast_1d(lon), np.atleast_1d(lat))]


def mmi_to_geojson(mmi: np.ndarray, transform, levels: list[int],
                   simplify_deg: float = _SIMPLIFY_DEG,
                   min_area_deg2: float = _MIN_AREA_DEG2) -> dict:
    """Filled bands between consecutive levels (and an open top band).

    Uses contourpy FillType.OuterOffset (contourpy >= 1.0).
    filled() returns a 2-tuple: (list_of_point_arrays, list_of_offset_arrays).
    Each element i is one polygon:
      - points_list[i]: np.ndarray of shape (N, 2) in pixel (col, row) coords
      - offsets_list[i]: 1-D int array of length (n_rings + 1) where
          offsets[0]:offsets[1]  -> exterior ring
          offsets[1]:offsets[2]  -> first hole ring
          ...
    Exterior + holes are assembled into a shapely Polygon, simplified
    (Douglas-Peucker, topology-preserving) and dropped if smaller than
    ``min_area_deg2``, then emitted as a GeoJSON Feature. Pass
    ``min_area_deg2=0`` / ``simplify_deg=0`` to disable.
    """
    # OuterOffset: one element per outer contour, offsets split exterior/holes.
    gen = contour_generator(z=mmi, name="serial", fill_type=FillType.OuterOffset)
    # Open top band runs from the highest level to just past the data maximum.
    # Guard the sentinel so bounds stay strictly ascending even when the data
    # peaks below the highest requested level (otherwise contourpy raises on a
    # band whose upper bound is below its lower bound).
    data_max = float(np.nanmax(mmi))
    top = max(data_max, float(levels[-1])) + 1.0
    bounds = list(levels) + [top]
    features = []

    for lower, upper in zip(bounds[:-1], bounds[1:]):
        # A level at or above the data maximum yields an empty band; skip it
        # (and never pass a degenerate upper <= lower to contourpy).
        if upper <= lower or lower >= data_max:
            continue
        filled = gen.filled(lower, upper)
        points_list = filled[0]   # list of (N, 2) arrays
        offsets_list = filled[1]  # list of int offset arrays

        for points, offsets in zip(points_list, offsets_list):
            if points is None or len(points) < 4:
                continue

            # Build coordinate rings: first ring is exterior, rest are holes.
            rings = []
            for k in range(len(offsets) - 1):
                ring = _ring_to_lonlat(points, offsets[k], offsets[k + 1], transform)
                if len(ring) < 4:
                    continue
                rings.append(ring)

            if not rings:
                continue

            poly = Polygon(rings[0], rings[1:])
            if simplify_deg > 0:
                poly = poly.simplify(simplify_deg, preserve_topology=True)
            if poly.is_empty or poly.area < min_area_deg2:
                continue
            if not poly.is_valid:
                poly = poly.buffer(0)  # repair self-intersections from simplify
                if poly.is_empty or poly.geom_type != "Polygon":
                    continue

            features.append({
                "type": "Feature",
                "properties": {
                    "mmi_lower": int(lower),
                    "mmi_upper": int(min(upper, 10)),
                    "color": _MMI_COLORS.get(int(lower), "#888888"),
                },
                "geometry": mapping(poly),
            })

    return {"type": "FeatureCollection", "features": features}
