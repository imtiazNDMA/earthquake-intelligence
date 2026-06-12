"""Event catalog reads/writes. Functions take an explicit connection."""
from __future__ import annotations
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

_SELECT = (
    "SELECT id, source, source_event_id, occurred_at, magnitude, depth_km, "
    "ST_X(geom) AS lon, ST_Y(geom) AS lat, cluster_id, is_canonical, created_at, "
    "place, mag_type, event_type, alert, tsunami, sig, review_status, "
    "felt, cdi, mmi_report, gap, nst, url, detail_url, updated_at "
    "FROM seismic_event"
)

_SELECT_DETAIL = (
    "SELECT id, source, source_event_id, occurred_at, magnitude, depth_km, "
    "ST_X(geom) AS lon, ST_Y(geom) AS lat, cluster_id, is_canonical, created_at, "
    "place, mag_type, event_type, alert, tsunami, sig, review_status, "
    "felt, cdi, mmi_report, gap, nst, url, detail_url, updated_at, usgs_detail "
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
        cur.execute(_SELECT_DETAIL + " WHERE id = %s", (event_id,))
        return cur.fetchone()


def update_usgs_detail(conn: psycopg.Connection, event_id: int,
                       detail: dict) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "UPDATE seismic_event SET usgs_detail = %s WHERE id = %s",
            (psycopg.types.json.Json(detail), event_id),
        )
        cur.execute(_SELECT_DETAIL + " WHERE id = %s", (event_id,))
        return cur.fetchone()


def update_event(conn: psycopg.Connection, event_id: int, *,
                 magnitude: float | None = None,
                 depth_km: float | None = None,
                 lon: float | None = None,
                 lat: float | None = None,
                 place: str | None = None,
                 occurred_at: datetime | None = None) -> dict | None:
    sets: list[str] = []
    params: list = []
    if magnitude is not None:
        sets.append("magnitude = %s"); params.append(magnitude)
    if depth_km is not None:
        sets.append("depth_km = %s"); params.append(depth_km)
    if place is not None:
        sets.append("place = %s"); params.append(place)
    if occurred_at is not None:
        sets.append("occurred_at = %s"); params.append(occurred_at)
    if lon is not None and lat is not None:
        sets.append("geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326)")
        params.extend([lon, lat])
    if not sets:
        return get_event(conn, event_id)
    params.append(event_id)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "UPDATE seismic_event SET " + ", ".join(sets) + " WHERE id = %s",
            params,
        )
        cur.execute(_SELECT_DETAIL + " WHERE id = %s", (event_id,))
        return cur.fetchone()


def delete_event(conn: psycopg.Connection, event_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM seismic_event WHERE id = %s", (event_id,))
        return cur.rowcount > 0


def list_events(conn: psycopg.Connection, *, since: datetime | None = None,
                min_magnitude: float | None = None,
                max_magnitude: float | None = None,
                source: str | None = None,
                search: str | None = None,
                limit: int = 100) -> list[dict]:
    clauses = ["is_canonical = TRUE"]
    params: list = []
    if since is not None:
        clauses.append("occurred_at >= %s")
        params.append(since)
    if min_magnitude is not None:
        clauses.append("magnitude >= %s")
        params.append(min_magnitude)
    if max_magnitude is not None:
        clauses.append("magnitude <= %s")
        params.append(max_magnitude)
    if source is not None:
        clauses.append("source = %s")
        params.append(source)
    if search is not None:
        clauses.append("place ILIKE %s")
        params.append(f"%{search}%")
    where = " WHERE " + " AND ".join(clauses)
    params.append(limit)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_SELECT + where + " ORDER BY occurred_at DESC LIMIT %s", params)
        return cur.fetchall()
