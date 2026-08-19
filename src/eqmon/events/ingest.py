"""Ingest events from a SeismicSource: upsert by (source, source_event_id), then
re-cluster within a space-time window, preferring the Primary source.

Dedup window: <= 60 s and <= 50 km. Source priority PMD(1) > USGS(2); MANUAL is
never clustered with feed events (it stays its own cluster). Clustering uses the
smallest event id in a row's window as the cluster id — sufficient for the
pairwise dedup this platform needs."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

import psycopg

from .sources import RawEvent, SeismicSource
from ..analytics import decluster_gardner_knopoff

DEDUP_SECONDS = 60
DEDUP_METERS = 50_000
INGEST_ADVISORY_LOCK = 0x45514D4F  # "EQMO", shared across API and CLI processes
DECLUSTER_MAX_EVENTS = 5_000


@dataclass
class IngestResult:
    source: str
    fetched: int
    inserted: int
    errors: list[str]
    watermark: datetime | None = None


def _upsert(conn: psycopg.Connection, e: RawEvent) -> bool:
    cur = conn.execute(
        "INSERT INTO seismic_event "
        "(source, source_event_id, occurred_at, magnitude, depth_km, geom, "
        " place, mag_type, event_type, alert, tsunami, sig, review_status, "
        " felt, cdi, mmi_report, gap, nst, url, detail_url, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), "
        " %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (source, source_event_id) WHERE source_event_id IS NOT NULL "
        "DO UPDATE SET "
        "occurred_at = EXCLUDED.occurred_at, "
        "magnitude = EXCLUDED.magnitude, "
        "depth_km = EXCLUDED.depth_km, "
        "geom = EXCLUDED.geom, "
        "place = EXCLUDED.place, "
        "mag_type = EXCLUDED.mag_type, "
        "event_type = EXCLUDED.event_type, "
        "alert = EXCLUDED.alert, "
        "tsunami = EXCLUDED.tsunami, "
        "sig = EXCLUDED.sig, "
        "review_status = EXCLUDED.review_status, "
        "felt = EXCLUDED.felt, "
        "cdi = EXCLUDED.cdi, "
        "mmi_report = EXCLUDED.mmi_report, "
        "gap = EXCLUDED.gap, "
        "nst = EXCLUDED.nst, "
        "url = EXCLUDED.url, "
        "detail_url = EXCLUDED.detail_url, "
        "updated_at = EXCLUDED.updated_at "
        "WHERE seismic_event.updated_at IS NULL "
        "OR EXCLUDED.updated_at IS NULL "
        "OR EXCLUDED.updated_at >= seismic_event.updated_at "
        "RETURNING (xmax = 0) AS inserted",
        (e.source, e.source_event_id, e.occurred_at, e.magnitude, e.depth_km,
         e.lon, e.lat,
         e.place, e.mag_type, e.event_type, e.alert, e.tsunami, e.sig,
         e.review_status, e.felt, e.cdi, e.mmi_report, e.gap, e.nst,
         e.url, e.detail_url, e.updated_at),
    )
    row = cur.fetchone()
    return bool(row and row[0])


def _recluster(conn: psycopg.Connection) -> None:
    # cluster_id = smallest id of any feed event within the space-time window
    conn.execute(
        """
        UPDATE seismic_event s SET cluster_id = sub.cid
        FROM (
          SELECT a.id, MIN(b.id) AS cid
          FROM seismic_event a
          JOIN seismic_event b
            ON a.source <> 'MANUAL' AND b.source <> 'MANUAL'
           AND b.occurred_at BETWEEN
               a.occurred_at - (%s * INTERVAL '1 second') AND
               a.occurred_at + (%s * INTERVAL '1 second')
           AND ST_DWithin(a.geom::geography, b.geom::geography, %s)
          GROUP BY a.id
        ) sub
        WHERE s.id = sub.id AND s.source <> 'MANUAL'
        """,
        (DEDUP_SECONDS, DEDUP_SECONDS, DEDUP_METERS),
    )
    # canonical = best (lowest) priority within each cluster, tie-broken by id
    conn.execute("UPDATE seismic_event SET is_canonical = FALSE WHERE source <> 'MANUAL'")
    conn.execute(
        """
        UPDATE seismic_event SET is_canonical = TRUE
        WHERE id IN (
          SELECT DISTINCT ON (cluster_id) id
          FROM seismic_event
          WHERE source <> 'MANUAL'
          ORDER BY cluster_id,
                   CASE source WHEN 'PMD' THEN 1 WHEN 'USGS' THEN 2 ELSE 3 END,
                   id
        )
        """
    )


def _decluster(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT id, occurred_at, ST_Y(geom) AS lat, ST_X(geom) AS lon, magnitude "
        "FROM seismic_event WHERE is_canonical = TRUE "
        "AND magnitude >= -1 AND magnitude < 10"
    ).fetchall()
    events = [{"id": r[0], "occurred_at": r[1], "lat": r[2], "lon": r[3],
               "magnitude": r[4]} for r in rows]
    flags = decluster_gardner_knopoff(events)
    conn.execute("UPDATE seismic_event SET is_mainshock = NULL, sequence_id = NULL")
    if events:
        ids = [ev["id"] for ev in events]
        mains = [bool(is_main) for (is_main, _seq) in flags]
        seqs = [int(seq) for (_is_main, seq) in flags]
        conn.execute(
            "UPDATE seismic_event AS s SET is_mainshock = v.m, sequence_id = v.seq "
            "FROM (SELECT unnest(%s::bigint[]) AS id, "
            "unnest(%s::boolean[]) AS m, unnest(%s::bigint[]) AS seq) AS v "
            "WHERE s.id = v.id",
            (ids, mains, seqs),
        )


def _assign_zones(conn: psycopg.Connection) -> None:
    conn.execute(
        "UPDATE seismic_event e SET zone_id = z.id "
        "FROM tectonic_zone z WHERE ST_Contains(z.geom, e.geom)"
    )


def finalize_ingest(conn: psycopg.Connection, *, classify_sequences: bool = True) -> None:
    """Apply catalog-wide relationships after one or more source loads.

    Historical backfills defer this work until every source has been upserted so
    source priority is resolved once. Sequence classification is optional because
    the current Gardner-Knopoff implementation is quadratic and is not suitable
    for a century-scale catalog.
    """
    _recluster(conn)
    event_count = conn.execute(
        "SELECT COUNT(*) FROM seismic_event WHERE is_canonical = TRUE"
    ).fetchone()[0]
    if classify_sequences and event_count <= DECLUSTER_MAX_EVENTS:
        _decluster(conn)
    _assign_zones(conn)


def ingest(conn: psycopg.Connection, source: SeismicSource,
           since: datetime | None = None,
           updatedafter: datetime | None = None,
           postprocess: bool = True) -> IngestResult:
    errors: list[str] = []
    try:
        raw = source.fetch(since, updatedafter=updatedafter)
    except Exception as exc:  # network/parse failure is non-fatal
        return IngestResult(source.name, 0, 0, [f"fetch failed: {exc!r}"])
    watermark = max((e.updated_at or e.occurred_at for e in raw), default=None)
    # The API's threading lock cannot coordinate a separate backfill process.
    # A transaction-scoped PostgreSQL lock serializes every catalog writer.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (INGEST_ADVISORY_LOCK,))
    inserted = 0
    for e in raw:
        try:
            if _upsert(conn, e):
                inserted += 1
        except Exception as exc:
            errors.append(f"{e.source_event_id}: {exc!r}")
    if postprocess:
        finalize_ingest(conn)
    return IngestResult(source.name, len(raw), inserted, errors, watermark)
