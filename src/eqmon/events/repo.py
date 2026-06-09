"""Event catalog reads/writes. Functions take an explicit connection."""
from __future__ import annotations
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

_SELECT = (
    "SELECT id, source, source_event_id, occurred_at, magnitude, depth_km, "
    "ST_X(geom) AS lon, ST_Y(geom) AS lat, cluster_id, is_canonical, created_at "
    "FROM seismic_event"
)


def create_manual_event(conn: psycopg.Connection, *, magnitude: float,
                        depth_km: float, lon: float, lat: float,
                        occurred_at: datetime | None = None) -> dict:
    occurred_at = occurred_at or datetime.now(timezone.utc)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "INSERT INTO seismic_event "
            "(source, occurred_at, magnitude, depth_km, geom) "
            "VALUES ('MANUAL', %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) "
            "RETURNING id",
            (occurred_at, magnitude, depth_km, lon, lat),
        )
        new_id = cur.fetchone()["id"]
        cur.execute("UPDATE seismic_event SET cluster_id = %s WHERE id = %s",
                    (new_id, new_id))
        cur.execute(_SELECT + " WHERE id = %s", (new_id,))
        return cur.fetchone()


def get_event(conn: psycopg.Connection, event_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_SELECT + " WHERE id = %s", (event_id,))
        return cur.fetchone()


def list_events(conn: psycopg.Connection, *, since: datetime | None = None,
                min_magnitude: float | None = None, limit: int = 100) -> list[dict]:
    clauses = ["is_canonical = TRUE"]
    params: list = []
    if since is not None:
        clauses.append("occurred_at >= %s")
        params.append(since)
    if min_magnitude is not None:
        clauses.append("magnitude >= %s")
        params.append(min_magnitude)
    where = " WHERE " + " AND ".join(clauses)
    params.append(limit)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_SELECT + where + " ORDER BY occurred_at DESC LIMIT %s", params)
        return cur.fetchall()
