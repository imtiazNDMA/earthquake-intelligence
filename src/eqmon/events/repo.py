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
    ", is_mainshock, sequence_id, zone_id "
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


def _build_where(since=None, min_magnitude=None, max_magnitude=None,
                  source=None, search=None,
                  occurred_after=None, occurred_before=None,
                  center_lon=None, center_lat=None, radius_km=None,
                  event_kind="all"):
    clauses = ["is_canonical = TRUE"]
    params: list = []
    if since is not None:
        clauses.append("occurred_at >= %s"); params.append(since)
    if min_magnitude is not None:
        clauses.append("magnitude >= %s"); params.append(min_magnitude)
    if max_magnitude is not None:
        clauses.append("magnitude <= %s"); params.append(max_magnitude)
    if source is not None:
        clauses.append("source = %s"); params.append(source)
    if search is not None:
        clauses.append("place ILIKE %s"); params.append(f"%{search}%")
    if occurred_after is not None:
        clauses.append("occurred_at >= %s"); params.append(occurred_after)
    if occurred_before is not None:
        clauses.append("occurred_at <= %s"); params.append(occurred_before)
    if radius_km is not None:
        clauses.append(
            "ST_DWithin(geom::geography, "
            "ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
        )
        params.extend([center_lon, center_lat, radius_km * 1000.0])
    if event_kind == "mainshocks":
        clauses.append("is_mainshock IS TRUE")
    elif event_kind == "aftershocks":
        clauses.append("is_mainshock IS FALSE")
    return clauses, params


def list_events(conn: psycopg.Connection, *, since: datetime | None = None,
                min_magnitude: float | None = None,
                max_magnitude: float | None = None,
                source: str | None = None,
                 search: str | None = None,
                 occurred_after: datetime | None = None,
                 occurred_before: datetime | None = None,
                 center_lon: float | None = None,
                 center_lat: float | None = None,
                 radius_km: float | None = None,
                 event_kind: str = "all",
                 limit: int = 100,
                offset: int = 0,
                orderby: str = "time") -> list[dict]:
    clauses, params = _build_where(since, min_magnitude, max_magnitude,
                                    source, search, occurred_after, occurred_before,
                                    center_lon, center_lat, radius_km, event_kind)
    where = " WHERE " + " AND ".join(clauses)
    order_map = {
        "time": "occurred_at DESC, id DESC",
        "time-asc": "occurred_at ASC, id ASC",
        "magnitude": "magnitude DESC, id DESC",
    }
    order_sql = order_map.get(orderby, "occurred_at DESC")
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT %s OFFSET %s"
        params.extend([limit, offset])
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            _SELECT + where + f" ORDER BY {order_sql}" + limit_sql,
            params,
        )
        return cur.fetchall()


def count_events(conn: psycopg.Connection, *,
                 min_magnitude: float | None = None,
                 max_magnitude: float | None = None,
                 source: str | None = None,
                  search: str | None = None,
                  occurred_after: datetime | None = None,
                  occurred_before: datetime | None = None,
                  center_lon: float | None = None,
                  center_lat: float | None = None,
                  radius_km: float | None = None,
                  event_kind: str = "all") -> int:
    clauses, params = _build_where(None, min_magnitude, max_magnitude,
                                    source, search, occurred_after, occurred_before,
                                    center_lon, center_lat, radius_km, event_kind)
    where = " WHERE " + " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM seismic_event" + where, params)
        return cur.fetchone()[0]


def catalog_coverage(conn: psycopg.Connection) -> dict:
    """Observed time extent of canonical catalog rows.

    This describes what is stored, not source completeness within the interval.
    """
    row = conn.execute(
        "SELECT MIN(occurred_at), MAX(occurred_at) FROM seismic_event "
        "WHERE is_canonical = TRUE"
    ).fetchone()
    return {
        "earliest_occurred_at": row[0],
        "latest_occurred_at": row[1],
    }


def source_coverage(conn: psycopg.Connection) -> list[dict]:
    """Stored record extent per source, without asserting completeness."""
    rows = conn.execute(
        "SELECT source, COUNT(*), MIN(occurred_at), MAX(occurred_at) "
        "FROM seismic_event GROUP BY source ORDER BY source"
    ).fetchall()
    return [
        {
            "source": source,
            "records": count,
            "earliest_occurred_at": earliest,
            "latest_occurred_at": latest,
        }
        for source, count, earliest, latest in rows
    ]


def catalog_max_time(conn: psycopg.Connection):
    """Most recent event time in the catalog (analytics window anchor)."""
    r = conn.execute("SELECT MAX(occurred_at) FROM seismic_event").fetchone()
    return r[0]


def analytics_rows(conn: psycopg.Connection, from_dt, to_dt, min_mag,
                   zone_id=None, bbox=None) -> list[dict]:
    """Canonical, quality-gated rows for analytics.

    The gate (-1 <= magnitude < 10, depth present) excludes dirty catalog
    rows such as PMD mag/depth swaps. `bbox` is (minlon, minlat, maxlon,
    maxlat) or None.
    """
    clauses = ["is_canonical = TRUE", "magnitude >= -1", "magnitude < 10",
               "depth_km IS NOT NULL", "occurred_at BETWEEN %s AND %s",
               "magnitude >= %s"]
    params = [from_dt, to_dt, min_mag]
    if zone_id is not None:
        clauses.append("zone_id = %s")
        params.append(zone_id)
    if bbox is not None:
        clauses.append("geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)")
        params.extend(bbox)
    sql = ("SELECT id, occurred_at, ST_Y(geom) AS lat, ST_X(geom) AS lon, "
           "magnitude, depth_km, mag_type, place, is_mainshock, zone_id, "
           "sequence_id "
           "FROM seismic_event WHERE " + " AND ".join(clauses))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
