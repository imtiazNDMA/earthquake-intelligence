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


def _build_where(since=None, min_magnitude=None, max_magnitude=None,
                 source=None, search=None,
                 occurred_after=None, occurred_before=None):
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
    return clauses, params


def list_events(conn: psycopg.Connection, *, since: datetime | None = None,
                min_magnitude: float | None = None,
                max_magnitude: float | None = None,
                source: str | None = None,
                search: str | None = None,
                occurred_after: datetime | None = None,
                occurred_before: datetime | None = None,
                limit: int = 100,
                offset: int = 0,
                orderby: str = "time") -> list[dict]:
    clauses, params = _build_where(since, min_magnitude, max_magnitude,
                                    source, search, occurred_after, occurred_before)
    where = " WHERE " + " AND ".join(clauses)
    order_map = {
        "time": "occurred_at DESC",
        "time-asc": "occurred_at ASC",
        "magnitude": "magnitude DESC",
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
                 occurred_before: datetime | None = None) -> int:
    clauses, params = _build_where(None, min_magnitude, max_magnitude,
                                    source, search, occurred_after, occurred_before)
    where = " WHERE " + " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM seismic_event" + where, params)
        return cur.fetchone()[0]


def get_event_stats(conn: psycopg.Connection) -> dict:
    """Return aggregated statistics for the analytics dashboard."""
    import math

    result = {}

    # total / mean / std / max
    r = conn.execute(
        "SELECT COUNT(*), AVG(magnitude), STDDEV(magnitude), MAX(magnitude) "
        "FROM seismic_event WHERE is_canonical = TRUE AND magnitude IS NOT NULL"
    ).fetchone()
    result["total_events"] = r[0]
    result["mean_magnitude"] = round(float(r[1]), 3) if r[1] else None
    result["mag_std"] = round(float(r[2]), 3) if r[2] else None
    result["max_magnitude"] = round(float(r[3]), 2) if r[3] else None

    # tsunami count
    result["tsunami_count"] = conn.execute(
        "SELECT COUNT(*) FROM seismic_event WHERE is_canonical = TRUE AND tsunami = 1"
    ).fetchone()[0]

    # magnitude distribution (bins of 0.5)
    rows = conn.execute("""
        SELECT floor(magnitude * 2) / 2 AS bin_low,
               COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE AND magnitude IS NOT NULL
        GROUP BY bin_low ORDER BY bin_low
    """).fetchall()
    result["magnitude_bins"] = [{"bin": float(r[0]), "count": r[1]} for r in rows]

    # --- Gutenberg-Richter: cumulative per 0.2 mag bin ---
    rows = conn.execute("""
        WITH bins AS (
          SELECT floor(magnitude * 5) / 5 AS mag_low,
                 COUNT(*) AS cnt
          FROM seismic_event WHERE is_canonical = TRUE AND magnitude IS NOT NULL
          GROUP BY mag_low
        )
        SELECT mag_low, cnt,
               SUM(cnt) OVER (ORDER BY mag_low DESC) AS cumulative
        FROM bins ORDER BY mag_low
    """).fetchall()
    result["gr_data"] = [
        {"mag_low": float(r[0]), "count": r[1], "cumulative": r[2]}
        for r in rows
    ]
    # compute b-value (Gutenberg-Richter slope) from linear portion
    b_value = None
    if len(rows) >= 3:
        n_pts = max(3, len(rows) * 3 // 4)
        pts = [(float(r[0]), math.log10(max(r[2], 1))) for r in rows[:n_pts]]
        if pts:
            n = len(pts)
            sx = sum(p[0] for p in pts)
            sy = sum(p[1] for p in pts)
            sxx = sum(p[0] * p[0] for p in pts)
            sxy = sum(p[0] * p[1] for p in pts)
            denom = n * sxx - sx * sx
            if abs(denom) > 1e-12:
                b_value = -round((n * sxy - sx * sy) / denom, 3)
    result["b_value"] = b_value

    # --- full daily counts + cumulative moment (all time) ---
    rows = conn.execute("""
        SELECT DATE(occurred_at) AS day, COUNT(*) AS cnt,
               SUM((10.0 ^ (COALESCE(magnitude, 0) * 1.5))) AS moment_proxy,
               MAX(magnitude) AS max_mag
        FROM seismic_event WHERE is_canonical = TRUE AND occurred_at IS NOT NULL
        GROUP BY day ORDER BY day
    """).fetchall()
    daily = []
    cum_moment = 0.0
    for r in rows:
        cum_moment += float(r[2])
        daily.append({
            "day": str(r[0]), "count": r[1],
            "moment_proxy": round(float(r[2]), 2),
            "cum_moment": round(cum_moment, 2),
            "max_mag": float(r[3]) if r[3] else None,
        })
    result["daily_cumulative"] = daily

    # 7-day rolling seismicity rate
    if daily:
        counts = [d["count"] for d in daily]
        rolling = []
        for i, d in enumerate(daily):
            window = counts[max(0, i - 6):i + 1]
            rolling.append(round(sum(window) / len(window), 1))
            d["rate_7day"] = rolling[-1]
    else:
        result["daily_cumulative"] = []

    # --- depth distribution (bins of 10 km) ---
    rows = conn.execute("""
        SELECT floor(COALESCE(depth_km, 0) / 10) * 10 AS depth_low,
               COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE AND depth_km IS NOT NULL
        GROUP BY depth_low ORDER BY depth_low
    """).fetchall()
    result["depth_bins"] = [
        {"depth_low": int(r[0]), "count": r[1]} for r in rows
    ]

    # --- hour-of-day distribution ---
    rows = conn.execute("""
        SELECT EXTRACT(HOUR FROM occurred_at)::int AS hour, COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE AND occurred_at IS NOT NULL
        GROUP BY hour ORDER BY hour
    """).fetchall()
    hour_map = {r[0]: r[1] for r in rows}
    result["hour_dist"] = [{"hour": h, "count": hour_map.get(h, 0)} for h in range(24)]

    # --- day-of-week distribution ---
    rows = conn.execute("""
        SELECT EXTRACT(DOW FROM occurred_at)::int AS dow, COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE AND occurred_at IS NOT NULL
        GROUP BY dow ORDER BY dow
    """).fetchall()
    dow_map = {r[0]: r[1] for r in rows}
    dow_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    result["weekday_dist"] = [
        {"dow": d, "day": dow_names[d], "count": dow_map.get(d, 0)}
        for d in range(7)
    ]

    # alert distribution
    rows = conn.execute("""
        SELECT COALESCE(alert, 'none') AS alert, COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE
        GROUP BY alert ORDER BY count DESC
    """).fetchall()
    result["alert_dist"] = [{"alert": r[0], "count": r[1]} for r in rows]

    # source distribution
    rows = conn.execute("""
        SELECT source, COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE
        GROUP BY source ORDER BY count DESC
    """).fetchall()
    result["source_dist"] = [{"source": r[0], "count": r[1]} for r in rows]

    # depth vs magnitude pairs (up to 500)
    rows = conn.execute("""
        SELECT magnitude, depth_km FROM seismic_event
        WHERE is_canonical = TRUE AND magnitude IS NOT NULL AND depth_km IS NOT NULL
        ORDER BY occurred_at DESC LIMIT 500
    """).fetchall()
    result["depth_mag_pairs"] = [
        {"mag": float(r[0]), "depth": float(r[1])} for r in rows
    ]

    # top 10 most significant
    rows = conn.execute("""
        SELECT id, magnitude, place, sig, alert, tsunami, occurred_at
        FROM seismic_event WHERE is_canonical = TRUE AND sig IS NOT NULL
        ORDER BY sig DESC LIMIT 10
    """).fetchall()
    result["top_significant"] = [
        {"id": r[0], "magnitude": float(r[1]) if r[1] else None,
         "place": r[2], "sig": r[3], "alert": r[4], "tsunami": r[5],
         "occurred_at": str(r[6]) if r[6] else None}
        for r in rows
    ]

    # mag type distribution
    rows = conn.execute("""
        SELECT COALESCE(mag_type, 'unknown') AS mag_type, COUNT(*) AS count
        FROM seismic_event WHERE is_canonical = TRUE
        GROUP BY mag_type ORDER BY count DESC
    """).fetchall()
    result["mag_type_dist"] = [{"mag_type": r[0], "count": r[1]} for r in rows]

    return result
