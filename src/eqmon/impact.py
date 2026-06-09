"""Per-event district impact. Reuses the Plan A engine for the MMI surface, then:
- max-band-intersecting MMI per district via a PostGIS spatial join;
- representative-point MMI per district by sampling the MMI grid at each
  district's point-on-surface."""
from __future__ import annotations
import json

import numpy as np
import psycopg
from psycopg.rows import dict_row

from .config import MMI_BAND_LEVELS
from .contours import mmi_to_geojson
from .intensity import compute_mmi_grid
from .vs30 import Grid


def sample_grid_at(grid_array: np.ndarray, transform, lons: np.ndarray,
                   lats: np.ndarray) -> np.ndarray:
    """Nearest-cell value of a raster array at geographic points."""
    inv = ~transform
    cols, rows = inv * (np.asarray(lons), np.asarray(lats))
    cols = np.clip(np.floor(cols).astype(int), 0, grid_array.shape[1] - 1)
    rows = np.clip(np.floor(rows).astype(int), 0, grid_array.shape[0] - 1)
    return grid_array[rows, cols]


def compute_event_impact(conn: psycopg.Connection, event: dict, grid: Grid) -> dict:
    mmi = compute_mmi_grid(
        grid.lon, grid.lat, grid.vs30,
        mag=event["magnitude"], depth_km=event["depth_km"],
        epi_lon=event["lon"], epi_lat=event["lat"],
    )
    bands = mmi_to_geojson(mmi, grid.transform, levels=MMI_BAND_LEVELS)

    # --- max band per district (spatial join in PostGIS) ---
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE _bands (mmi int, geom geometry(Geometry,4326)) "
                    "ON COMMIT DROP")
        for f in bands["features"]:
            cur.execute(
                "INSERT INTO _bands (mmi, geom) VALUES "
                "(%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                (f["properties"]["mmi_lower"], json.dumps(f["geometry"])),
            )
        cur.execute("CREATE INDEX ON _bands USING GIST (geom)")

    # representative points + max band, one row per district
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT d.id, d.name, d.province,
                   ST_X(ST_PointOnSurface(d.geom)) AS rlon,
                   ST_Y(ST_PointOnSurface(d.geom)) AS rlat,
                   COALESCE(MAX(b.mmi), 0) AS mmi_max
            FROM district d
            LEFT JOIN _bands b ON ST_Intersects(d.geom, b.geom)
            GROUP BY d.id, d.name, d.province, d.geom
            ORDER BY mmi_max DESC, d.name
            """
        )
        rows = cur.fetchall()

    rlons = np.array([r["rlon"] for r in rows], dtype="float64")
    rlats = np.array([r["rlat"] for r in rows], dtype="float64")
    repr_mmi = (sample_grid_at(mmi, grid.transform, rlons, rlats)
                if len(rows) else np.array([]))

    districts = []
    for r, rm in zip(rows, repr_mmi):
        districts.append({
            "id": r["id"], "name": r["name"], "province": r["province"],
            "mmi_max": int(r["mmi_max"]), "mmi_repr": int(np.floor(float(rm))),
        })
    return {"bands": bands, "districts": districts}
