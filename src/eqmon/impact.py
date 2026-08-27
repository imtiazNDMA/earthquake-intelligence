"""Per-event admin-boundary impact. Reuses the Plan A engine for the MMI
surface, then for each admin level:
- max-band-intersecting MMI per unit via a PostGIS spatial join;
- representative-point MMI per unit by sampling the MMI grid at each unit's
  point-on-surface."""
from __future__ import annotations
import hashlib
import json

import numpy as np
import psycopg
from psycopg.rows import dict_row

from .config import MMI_BAND_LEVELS
from .analysis_artifacts import (AnalysisKind, ArtifactResolution,
                                 get_or_compute_artifact)
from .contours import mmi_to_geojson
from .intensity import compute_mmi_grid
from .vs30 import Grid

# Levels rolled up per event (national is overlay-only, not aggregated).
ROLLUP_LEVELS = ("province", "district", "tehsil")
EVENT_IMPACT_CALCULATION_VERSION = "1.0"


def sample_grid_at(grid_array: np.ndarray, transform, lons: np.ndarray,
                   lats: np.ndarray) -> np.ndarray:
    """Value of the raster cell that contains each geographic point.

    Points outside the raster extent are clipped to the edge cell."""
    inv = ~transform
    cols, rows = inv * (np.asarray(lons), np.asarray(lats))
    cols = np.clip(np.floor(cols).astype(int), 0, grid_array.shape[1] - 1)
    rows = np.clip(np.floor(rows).astype(int), 0, grid_array.shape[0] - 1)
    return grid_array[rows, cols]


def _rollup_for_level(conn: psycopg.Connection, level: str,
                      mmi: np.ndarray, grid: Grid) -> list[dict]:
    """Max-band + representative MMI for every admin unit at `level`.

    Assumes a temp `_bands` table (mmi int, geom) with a GIST index already
    exists in this transaction."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.name, a.parent,
                   ST_X(ST_PointOnSurface(a.geom)) AS rlon,
                   ST_Y(ST_PointOnSurface(a.geom)) AS rlat,
                   COALESCE(MAX(b.mmi), 0) AS mmi_max
            FROM admin_boundary a
            LEFT JOIN _bands b ON ST_Intersects(a.geom, b.geom)
            WHERE a.level = %s
            GROUP BY a.id, a.name, a.parent, a.geom
            ORDER BY mmi_max DESC, a.name
            """,
            (level,),
        )
        rows = cur.fetchall()

    rlons = np.array([r["rlon"] for r in rows], dtype="float64")
    rlats = np.array([r["rlat"] for r in rows], dtype="float64")
    repr_mmi = (sample_grid_at(mmi, grid.transform, rlons, rlats)
                if rows else np.array([]))
    return [
        {"id": r["id"], "name": r["name"], "parent": r["parent"],
         "mmi_max": int(r["mmi_max"]), "mmi_repr": round(float(rm), 1)}
        for r, rm in zip(rows, repr_mmi)
    ]


def compute_event_impact(conn: psycopg.Connection, event: dict, grid: Grid) -> dict:
    mmi = compute_mmi_grid(
        grid.lon, grid.lat, grid.vs30,
        mag=event["magnitude"], depth_km=event["depth_km"],
        epi_lon=event["lon"], epi_lat=event["lat"],
    )
    bands = mmi_to_geojson(mmi, grid.transform, levels=MMI_BAND_LEVELS)

    # Build the band surface once; reused across every level's spatial join.
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS pg_temp._bands")
        cur.execute("CREATE TEMP TABLE _bands (mmi int, geom geometry(Geometry,4326)) "
                    "ON COMMIT DROP")
        for f in bands["features"]:
            cur.execute(
                "INSERT INTO _bands (mmi, geom) VALUES "
                "(%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                (f["properties"]["mmi_lower"], json.dumps(f["geometry"])),
            )
        cur.execute("CREATE INDEX ON _bands USING GIST (geom)")

    # _rollup_for_level reads the _bands temp table built above; keep that
    # setup immediately before this fan-out so the coupling stays visible.
    rollups = {lvl: _rollup_for_level(conn, lvl, mmi, grid) for lvl in ROLLUP_LEVELS}
    return {"bands": bands, "rollups": rollups}


def get_or_compute_event_impact(conn: psycopg.Connection, event: dict,
                                grid: Grid) -> ArtifactResolution:
    """Persist or reuse the deterministic impact result for one event state."""
    computation_input = {
        "event_id": event["id"],
        "magnitude": event["magnitude"],
        "depth_km": event["depth_km"],
        "lon": event["lon"],
        "lat": event["lat"],
    }
    data_fingerprint = {
        "vs30_sha256": grid.source_sha256,
        "default_vs30": grid.default_vs30,
        "admin_boundaries_sha256": _admin_boundaries_sha256(conn),
    }
    provenance = {
        "event": {
            "id": event["id"],
            "source": event.get("source"),
            "source_event_id": event.get("source_event_id"),
            "occurred_at": event.get("occurred_at"),
            "place": event.get("place"),
        },
        "data": data_fingerprint,
    }
    return get_or_compute_artifact(
        conn,
        kind=AnalysisKind.IMPACT,
        calculation_version=EVENT_IMPACT_CALCULATION_VERSION,
        computation_input=computation_input,
        data_fingerprint=data_fingerprint,
        provenance=provenance,
        compute=lambda: compute_event_impact(conn, event, grid),
    )


def _admin_boundaries_sha256(conn: psycopg.Connection) -> str:
    rows = conn.execute(
        "SELECT id, level, name, parent, ST_AsEWKB(geom) "
        "FROM admin_boundary "
        "WHERE level IN ('province', 'district', 'tehsil') ORDER BY id"
    ).fetchall()
    digest = hashlib.sha256()
    for artifact_id, level, name, parent, geometry in rows:
        metadata = json.dumps(
            [artifact_id, level, name, parent],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("utf-8")
        geometry_bytes = bytes(geometry)
        for value in (metadata, geometry_bytes):
            digest.update(len(value).to_bytes(8, byteorder="big"))
            digest.update(value)
    return digest.hexdigest()
