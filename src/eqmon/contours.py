"""Turn an MMI grid into filled contour bands as GeoJSON. Uses contourpy's
filled-contour algorithm, maps pixel coordinates to geographic coordinates via
the raster affine transform, and tags each band with an MMI range and color.

This is what makes the data servable: a 15M-cell surface collapses to a handful
of band polygons (tens of KB), losslessly derived from the full-res grid."""
from __future__ import annotations

import numpy as np
from contourpy import contour_generator, FillType

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


def mmi_to_geojson(mmi: np.ndarray, transform, levels: list[int]) -> dict:
    """Filled bands between consecutive levels (and an open top band).

    Uses contourpy FillType.OuterOffset (contourpy >= 1.0).
    filled() returns a 2-tuple: (list_of_point_arrays, list_of_offset_arrays).
    Each element i is one polygon:
      - points_list[i]: np.ndarray of shape (N, 2) in pixel (col, row) coords
      - offsets_list[i]: 1-D int array of length (n_rings + 1) where
          offsets[0]:offsets[1]  -> exterior ring
          offsets[1]:offsets[2]  -> first hole ring
          ...
    Exterior + holes are assembled into a GeoJSON Polygon coordinates array
    (first element = exterior, remaining = holes), then wrapped in a Feature.
    """
    # OuterOffset: one element per outer contour, offsets split exterior/holes.
    gen = contour_generator(z=mmi, name="serial", fill_type=FillType.OuterOffset)
    bounds = list(levels) + [float(np.nanmax(mmi)) + 1.0]
    features = []

    for lower, upper in zip(bounds[:-1], bounds[1:]):
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

            features.append({
                "type": "Feature",
                "properties": {
                    "mmi_lower": int(lower),
                    "mmi_upper": int(min(upper, 10)),
                    "color": _MMI_COLORS.get(int(lower), "#888888"),
                },
                "geometry": {"type": "Polygon", "coordinates": rings},
            })

    return {"type": "FeatureCollection", "features": features}
