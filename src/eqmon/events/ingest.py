"""Ingest events from a SeismicSource: upsert by (source, source_event_id), then
re-cluster within a space-time window, preferring the Primary source.

Dedup window: <= 60 s and <= 50 km. Source priority MET(1) > USGS(2); MANUAL is
never clustered with feed events (it stays its own cluster). Clustering uses the
smallest event id in a row's window as the cluster id — sufficient for the
pairwise dedup this platform needs."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

import psycopg

from .sources import RawEvent, SeismicSource

DEDUP_SECONDS = 60
DEDUP_METERS = 50_000


@dataclass
class IngestResult:
    source: str
    fetched: int
    inserted: int
    errors: list[str]


def _upsert(conn: psycopg.Connection, e: RawEvent) -> bool:
    cur = conn.execute(
        "INSERT INTO seismic_event "
        "(source, source_event_id, occurred_at, magnitude, depth_km, geom) "
        "VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) "
        "ON CONFLICT (source, source_event_id) WHERE source_event_id IS NOT NULL "
        "DO NOTHING RETURNING id",
        (e.source, e.source_event_id, e.occurred_at, e.magnitude, e.depth_km,
         e.lon, e.lat),
    )
    return cur.fetchone() is not None


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
           AND abs(extract(epoch FROM (a.occurred_at - b.occurred_at))) <= %s
           AND ST_DWithin(a.geom::geography, b.geom::geography, %s)
          GROUP BY a.id
        ) sub
        WHERE s.id = sub.id AND s.source <> 'MANUAL'
        """,
        (DEDUP_SECONDS, DEDUP_METERS),
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
                   CASE source WHEN 'MET' THEN 1 WHEN 'USGS' THEN 2 ELSE 3 END,
                   id
        )
        """
    )


def ingest(conn: psycopg.Connection, source: SeismicSource,
           since: datetime | None = None) -> IngestResult:
    errors: list[str] = []
    try:
        raw = source.fetch(since)
    except Exception as exc:  # network/parse failure is non-fatal
        return IngestResult(source.name, 0, 0, [f"fetch failed: {exc!r}"])
    inserted = 0
    for e in raw:
        try:
            if _upsert(conn, e):
                inserted += 1
        except Exception as exc:
            errors.append(f"{e.source_event_id}: {exc!r}")
    _recluster(conn)
    return IngestResult(source.name, len(raw), inserted, errors)
