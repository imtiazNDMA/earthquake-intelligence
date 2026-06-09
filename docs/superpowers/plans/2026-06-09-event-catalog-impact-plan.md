# Event Catalog & Impact (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PostGIS-backed earthquake event catalog with Manual Event Input, USGS feed ingestion (behind a `SeismicSource` interface ready for the MET feed), source dedup, and per-event district impact aggregation (max-band + representative-point MMI), plus a light event-list/impact-table frontend.

**Architecture:** psycopg 3 + raw parameterized SQL against PostGIS (no ORM). Events and district geometry live in PostGIS; the district↔intensity-band join is a SQL spatial query (`ST_Intersects`). The Plan A intensity engine (`compute_mmi_grid`, `mmi_to_geojson`) is reused unchanged to produce the MMI surface per event. Repository/ingest/impact functions take an explicit `conn` so tests run inside a rolled-back transaction; the FastAPI layer hands them a pooled connection.

**Tech Stack:** Python 3.12, psycopg[binary] 3 + psycopg-pool, PostGIS 3.6 (existing local install), httpx (USGS fetch), shapely (already present), FastAPI, pytest.

**Design reference:** `docs/superpowers/specs/2026-06-09-event-catalog-impact-design.md`.

**Prerequisite (operator, one-time):** a database with PostGIS enabled:
```sql
CREATE DATABASE eqmon;
\c eqmon
CREATE EXTENSION IF NOT EXISTS postgis;
-- and a separate test DB:
CREATE DATABASE eqmon_test;
\c eqmon_test
CREATE EXTENSION IF NOT EXISTS postgis;
```
Set `DATABASE_URL=postgresql://user:pass@localhost:5432/eqmon` and
`DATABASE_URL_TEST=postgresql://user:pass@localhost:5432/eqmon_test`.

---

## File Structure

```
schema.sql                       table + index DDL (idempotent)
src/eqmon/
  db.py                          connection pool, get_conn(), init_schema(), apply_schema()
  events/
    __init__.py
    sources.py                   RawEvent, SeismicSource Protocol, USGSSource, METSource stub
    ingest.py                    IngestResult, ingest(conn, source), dedup clustering
    repo.py                      create_manual_event, list_events, get_event
  impact.py                      sample_grid_at(); compute_event_impact(conn, event, grid)
  api.py                         (modify) add /events, /events/ingest, /events/{id}, /events/{id}/impact
scripts/load_districts.py        one-time district load into PostGIS
tests/
  conftest.py                    (modify) db fixture: DATABASE_URL_TEST + per-test rollback
  fixtures/usgs_sample.json      saved USGS GeoJSON for offline parsing tests
  test_sources.py
  test_ingest.py
  test_repo.py
  test_impact.py
  test_events_api.py
web/app.js, web/index.html       (modify) event list panel + district impact table
```

Each module has one responsibility. DB access is funnelled through `db.py`; the event subsystem lives under `events/`; impact aggregation is isolated in `impact.py` so the spatial SQL is in one place.

---

### Task 1: Dependencies and database foundation

**Files:**
- Modify: `pyproject.toml`
- Create: `schema.sql`
- Create: `src/eqmon/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Add runtime dependencies**

In `pyproject.toml`, add to the `dependencies` list (keep existing entries):
```toml
    "psycopg[binary]>=3.1",
    "psycopg-pool>=3.2",
    "httpx>=0.27",
```

- [ ] **Step 2: Install**

Run: `uv sync --group dev`
Then: `uv run python -c "import psycopg, psycopg_pool, httpx; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Write `schema.sql`**

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS seismic_event (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL CHECK (source IN ('MET', 'USGS', 'MANUAL')),
    source_event_id TEXT,
    occurred_at     TIMESTAMPTZ NOT NULL,
    magnitude       DOUBLE PRECISION NOT NULL,
    depth_km        DOUBLE PRECISION NOT NULL,
    geom            geometry(Point, 4326) NOT NULL,
    cluster_id      BIGINT,
    is_canonical    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS seismic_event_source_uq
    ON seismic_event (source, source_event_id)
    WHERE source_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS seismic_event_geom_gix ON seismic_event USING GIST (geom);
CREATE INDEX IF NOT EXISTS seismic_event_time_ix ON seismic_event (occurred_at);

CREATE TABLE IF NOT EXISTS district (
    id        BIGSERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    province  TEXT,
    geom      geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS district_geom_gix ON district USING GIST (geom);
```

- [ ] **Step 4: Write `src/eqmon/db.py`**

```python
"""PostGIS access: a lazily-created connection pool plus schema helpers.

Repository/ingest/impact functions take an explicit psycopg connection so tests
can run inside a rolled-back transaction. The API acquires a pooled connection
via get_conn()."""
from __future__ import annotations
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema.sql"

_pool: ConnectionPool | None = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(_database_url(), min_size=1, max_size=8, open=True)
    return _pool


@contextmanager
def get_conn():
    """Yield a pooled connection (autocommit). For request handlers."""
    with get_pool().connection() as conn:
        yield conn


def apply_schema(conn: psycopg.Connection) -> None:
    """Apply schema.sql on the given connection (idempotent)."""
    conn.execute(SCHEMA_PATH.read_text())


def init_schema() -> None:
    """Apply schema to the configured DATABASE_URL (CLI / startup convenience)."""
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
```

- [ ] **Step 5: Write `tests/test_db.py`**

```python
import os
import psycopg
import pytest

from eqmon.db import apply_schema

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"),
    reason="DATABASE_URL_TEST not set",
)


def test_apply_schema_creates_tables(db_conn):
    rows = db_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name IN ('seismic_event','district')"
    ).fetchall()
    names = {r[0] for r in rows}
    assert names == {"seismic_event", "district"}


def test_postgis_available(db_conn):
    version = db_conn.execute("SELECT PostGIS_Lib_Version()").fetchone()[0]
    assert version  # non-empty version string
```

- [ ] **Step 6: Add the DB fixture to `tests/conftest.py`**

Append (do not remove the existing `import eqmon` line):
```python
import os
import psycopg
import pytest


@pytest.fixture()
def db_conn():
    """A connection wrapped in a transaction rolled back after each test.

    Schema is applied inside the transaction so tests are fully isolated and
    leave the test database empty. Skipped if DATABASE_URL_TEST is unset.
    """
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST not set")
    from eqmon.db import apply_schema
    conn = psycopg.connect(url)
    try:
        conn.autocommit = False
        apply_schema(conn)          # runs in the open transaction
        yield conn
    finally:
        conn.rollback()
        conn.close()
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_db.py -v`
Expected: with `DATABASE_URL_TEST` set, 2 passed; without it, 2 skipped.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml schema.sql src/eqmon/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: PostGIS schema, connection pool, and test-db fixture"
```

---

### Task 2: District loader

**Files:**
- Create: `scripts/load_districts.py`

One-time load of `boundary/district.geojson` (161 MultiPolygon features, properties `DISTRICT`, `PROVINCE`) into the `district` table. Run-once script; verification built in.

- [ ] **Step 1: Write `scripts/load_districts.py`**

```python
"""One-time: load boundary/district.geojson into the PostGIS `district` table.

Usage: uv run python scripts/load_districts.py
Requires DATABASE_URL and an applied schema (run eqmon.db.init_schema first, or
this script applies it)."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — PROJ pin (harmless here)
import psycopg  # noqa: E402
from eqmon.db import _database_url, apply_schema  # noqa: E402

GEOJSON = Path(__file__).resolve().parents[1] / "boundary" / "district.geojson"


def main() -> None:
    data = json.loads(GEOJSON.read_text(encoding="utf-8"))
    feats = data["features"]
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE district RESTART IDENTITY")
        with conn.cursor() as cur:
            for f in feats:
                props = f["properties"]
                name = props.get("DISTRICT")
                province = props.get("PROVINCE")
                geom = json.dumps(f["geometry"])
                cur.execute(
                    "INSERT INTO district (name, province, geom) "
                    "VALUES (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))",
                    (name, province, geom),
                )
        count = conn.execute("SELECT count(*) FROM district").fetchone()[0]
        print(f"loaded {count} districts (geojson had {len(feats)} features)")
        assert count == len(feats), "row count mismatch"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it (requires DATABASE_URL + PostGIS)**

Run: `uv run python scripts/load_districts.py`
Expected: `loaded 161 districts (geojson had 161 features)`.

- [ ] **Step 3: Commit**

```bash
git add scripts/load_districts.py
git commit -m "feat: one-time district loader into PostGIS"
```

---

### Task 3: Event repository and Manual Event Input

**Files:**
- Create: `src/eqmon/events/__init__.py`
- Create: `src/eqmon/events/repo.py`
- Test: `tests/test_repo.py`

- [ ] **Step 1: Create the package init**

`src/eqmon/events/__init__.py`:
```python
"""Earthquake event catalog: sources, ingestion, and repository."""
```

- [ ] **Step 2: Write `tests/test_repo.py` (TDD)**

```python
import os
from datetime import datetime, timezone

import pytest

from eqmon.events.repo import create_manual_event, get_event, list_events

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def test_create_manual_event_persists_and_reads_back(db_conn):
    ev = create_manual_event(
        db_conn, magnitude=6.2, depth_km=12.0, lon=72.5, lat=34.0,
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert ev["id"] > 0
    assert ev["source"] == "MANUAL"
    assert ev["is_canonical"] is True
    assert ev["cluster_id"] == ev["id"]

    got = get_event(db_conn, ev["id"])
    assert got["magnitude"] == 6.2
    assert abs(got["lon"] - 72.5) < 1e-9 and abs(got["lat"] - 34.0) < 1e-9


def test_list_events_filters_by_min_magnitude(db_conn):
    create_manual_event(db_conn, magnitude=4.0, depth_km=5, lon=70, lat=30,
                        occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    create_manual_event(db_conn, magnitude=6.5, depth_km=5, lon=71, lat=31,
                        occurred_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
    big = list_events(db_conn, min_magnitude=6.0)
    assert len(big) == 1 and big[0]["magnitude"] == 6.5


def test_get_event_missing_returns_none(db_conn):
    assert get_event(db_conn, 999999) is None
```

- [ ] **Step 3: Write `src/eqmon/events/repo.py`**

```python
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
        # a manual event is its own cluster
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_repo.py -v`
Expected: 3 passed (or skipped if no test DB).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/events/__init__.py src/eqmon/events/repo.py tests/test_repo.py
git commit -m "feat: event repository with Manual Event Input"
```

---

### Task 4: Seismic sources (USGS adapter + MET stub)

**Files:**
- Create: `src/eqmon/events/sources.py`
- Create: `tests/fixtures/usgs_sample.json`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Create the fixture `tests/fixtures/usgs_sample.json`**

A minimal USGS GeoJSON with one in-region and one out-of-region feature:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "id": "us1000abcd",
      "properties": {"mag": 5.4, "time": 1767225600000, "place": "near Pakistan"},
      "geometry": {"type": "Point", "coordinates": [72.5, 34.0, 15.0]}
    },
    {
      "id": "us1000ffff",
      "properties": {"mag": 6.0, "time": 1767225601000, "place": "Pacific"},
      "geometry": {"type": "Point", "coordinates": [-150.0, 60.0, 30.0]}
    }
  ]
}
```

- [ ] **Step 2: Write `tests/test_sources.py` (TDD — pure parsing, no network)**

```python
import json
from datetime import datetime, timezone
from pathlib import Path

from eqmon.events.sources import parse_usgs, RawEvent

FIXTURE = Path(__file__).parent / "fixtures" / "usgs_sample.json"


def test_parse_usgs_maps_fields_and_filters_region():
    data = json.loads(FIXTURE.read_text())
    events = parse_usgs(data)
    # only the in-region feature survives the Coverage Region filter
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, RawEvent)
    assert ev.source == "USGS"
    assert ev.source_event_id == "us1000abcd"
    assert ev.magnitude == 5.4
    assert ev.depth_km == 15.0
    assert ev.lon == 72.5 and ev.lat == 34.0
    assert ev.occurred_at == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_parse_usgs_skips_features_missing_required_fields():
    data = {"features": [{"id": "x", "properties": {"mag": None, "time": 1767225600000},
                          "geometry": {"type": "Point", "coordinates": [72.5, 34.0, 5.0]}}]}
    assert parse_usgs(data) == []
```

- [ ] **Step 3: Write `src/eqmon/events/sources.py`**

```python
"""Seismic event sources. USGSSource (Secondary) is fully implemented; METSource
(Primary) is a stub until the Pakistan MET feed format is known. parse_usgs is
pure (no network) for testability."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from ..config import COVERAGE_BBOX

USGS_FEED_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)


@dataclass(frozen=True)
class RawEvent:
    source: str
    source_event_id: str
    occurred_at: datetime
    magnitude: float
    depth_km: float
    lon: float
    lat: float


class SeismicSource(Protocol):
    name: str
    def fetch(self, since: datetime | None = None) -> list[RawEvent]: ...


def _in_region(lon: float, lat: float) -> bool:
    minx, miny, maxx, maxy = COVERAGE_BBOX
    return minx <= lon <= maxx and miny <= lat <= maxy


def parse_usgs(geojson: dict) -> list[RawEvent]:
    out: list[RawEvent] = []
    for f in geojson.get("features", []):
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 3:
            continue
        lon, lat, depth = coords[0], coords[1], coords[2]
        mag = props.get("mag")
        time_ms = props.get("time")
        eid = f.get("id")
        if mag is None or time_ms is None or eid is None:
            continue
        if not _in_region(lon, lat):
            continue
        out.append(RawEvent(
            source="USGS",
            source_event_id=str(eid),
            occurred_at=datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc),
            magnitude=float(mag),
            depth_km=float(depth),
            lon=float(lon),
            lat=float(lat),
        ))
    return out


class USGSSource:
    name = "USGS"

    def __init__(self, url: str = USGS_FEED_URL, timeout: float = 15.0):
        self.url = url
        self.timeout = timeout

    def fetch(self, since: datetime | None = None) -> list[RawEvent]:
        resp = httpx.get(self.url, timeout=self.timeout)
        resp.raise_for_status()
        events = parse_usgs(resp.json())
        if since is not None:
            events = [e for e in events if e.occurred_at >= since]
        return events


class METSource:
    """Primary Seismic Source (Pakistan MET Department).

    Stub: the feed endpoint and format are not yet known. Implement `fetch` to
    return RawEvent(source="MET", ...) once the format is provided.
    """
    name = "MET"

    def fetch(self, since: datetime | None = None) -> list[RawEvent]:
        raise NotImplementedError("MET feed format not yet defined")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_sources.py -v`
Expected: 2 passed (no DB needed — pure parsing).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/events/sources.py tests/fixtures/usgs_sample.json tests/test_sources.py
git commit -m "feat: USGS source adapter (parse + fetch) and MET stub behind SeismicSource"
```

---

### Task 5: Ingestion with dedup clustering

**Files:**
- Create: `src/eqmon/events/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write `tests/test_ingest.py` (TDD)**

```python
import os
from datetime import datetime, timedelta, timezone

import pytest

from eqmon.events.ingest import ingest, IngestResult
from eqmon.events.sources import RawEvent
from eqmon.events.repo import list_events

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _FakeSource:
    name = "USGS"
    def __init__(self, events): self._events = events
    def fetch(self, since=None): return list(self._events)


def test_ingest_inserts_and_is_idempotent(db_conn):
    src = _FakeSource([RawEvent("USGS", "a1", T0, 5.5, 10, 72.5, 34.0)])
    r1 = ingest(db_conn, src)
    assert isinstance(r1, IngestResult) and r1.inserted == 1
    r2 = ingest(db_conn, src)  # same event again
    assert r2.inserted == 0  # ON CONFLICT, no duplicate
    assert len(list_events(db_conn)) == 1


def test_dedup_clusters_close_events_and_prefers_met(db_conn):
    usgs = _FakeSource([RawEvent("USGS", "u1", T0, 5.5, 10, 72.50, 34.00)])
    met = _FakeSource([RawEvent("MET", "m1", T0 + timedelta(seconds=30), 5.6, 10, 72.55, 34.02)])
    ingest(db_conn, usgs)
    ingest(db_conn, met)
    canonical = list_events(db_conn)
    # one cluster -> one canonical event, and MET (Primary) wins
    assert len(canonical) == 1
    assert canonical[0]["source"] == "MET"


def test_far_apart_events_are_separate_clusters(db_conn):
    a = _FakeSource([RawEvent("USGS", "u1", T0, 5.5, 10, 72.5, 34.0)])
    b = _FakeSource([RawEvent("USGS", "u2", T0, 5.5, 10, 80.0, 40.0)])  # ~900 km away
    ingest(db_conn, a)
    ingest(db_conn, b)
    assert len(list_events(db_conn)) == 2
```

- [ ] **Step 2: Write `src/eqmon/events/ingest.py`**

```python
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
_PRIORITY = {"MET": 1, "USGS": 2, "MANUAL": 3}


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
        UPDATE seismic_event s SET is_canonical = TRUE
        WHERE s.id IN (
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
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: 3 passed (or skipped without test DB).

- [ ] **Step 4: Commit**

```bash
git add src/eqmon/events/ingest.py tests/test_ingest.py
git commit -m "feat: USGS ingestion with idempotent upsert and space-time dedup"
```

---

### Task 6: District impact aggregation

**Files:**
- Create: `src/eqmon/impact.py`
- Test: `tests/test_impact.py`

- [ ] **Step 1: Write `tests/test_impact.py` (TDD)**

```python
import os
import numpy as np
import pytest
from rasterio.transform import from_origin

from eqmon.impact import sample_grid_at

# --- pure helper test (no DB) ---


def test_sample_grid_at_nearest_cell():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype="float32")
    transform = from_origin(70.0, 32.0, 1.0, 1.0)  # cells: cols 70-72, rows 32-30
    # point in the lower-right cell (lon ~71.5, lat ~30.5) -> value 4.0
    vals = sample_grid_at(arr, transform, np.array([71.5]), np.array([30.5]))
    assert vals[0] == 4.0
    # point in the upper-left cell -> value 1.0
    vals2 = sample_grid_at(arr, transform, np.array([70.5]), np.array([31.5]))
    assert vals2[0] == 1.0


# --- impact integration test (DB) ---
pytest_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


@pytest_db
def test_compute_event_impact_reports_max_and_repr(db_conn):
    from eqmon.vs30 import load_grid
    from eqmon.config import VS30_TIF
    from eqmon.events.repo import create_manual_event
    from eqmon.impact import compute_event_impact

    # a small district square right over the epicenter
    db_conn.execute(
        "INSERT INTO district (name, province, geom) VALUES "
        "('Epi', 'Test', ST_Multi(ST_SetSRID("
        "ST_MakeEnvelope(72.0, 33.5, 73.0, 34.5), 4326)))"
    )
    grid = load_grid(VS30_TIF)
    ev = create_manual_event(db_conn, magnitude=6.5, depth_km=10, lon=72.5, lat=34.0)
    impact = compute_event_impact(db_conn, ev, grid)

    assert impact["bands"]["type"] == "FeatureCollection"
    epi = next(d for d in impact["districts"] if d["name"] == "Epi")
    assert epi["mmi_max"] >= epi["mmi_repr"]   # worst-case >= point value
    assert epi["mmi_repr"] >= 1.0
```

- [ ] **Step 2: Write `src/eqmon/impact.py`**

```python
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
            "mmi_max": int(r["mmi_max"]), "mmi_repr": round(float(rm), 1),
        })
    return {"bands": bands, "districts": districts}
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_impact.py -v`
Expected: the `sample_grid_at` test passes always; the DB test passes with a test DB (or skips). Requires `data/Vs30.tif` (Plan A output) to exist for the DB test.

- [ ] **Step 4: Commit**

```bash
git add src/eqmon/impact.py tests/test_impact.py
git commit -m "feat: per-event district impact (max band via PostGIS, representative point)"
```

---

### Task 7: Event API endpoints

**Files:**
- Modify: `src/eqmon/api.py`
- Test: `tests/test_events_api.py`

- [ ] **Step 1: Write `tests/test_events_api.py` (TDD)**

```python
import os
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


@pytest.fixture()
def client(monkeypatch):
    # point the app's pool at the test DB
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL_TEST"])
    from eqmon import api, db
    db._pool = None  # force pool recreation against test DB
    # ensure schema present
    db.init_schema()
    return TestClient(api.app)


def test_manual_event_create_and_get(client):
    r = client.post("/events", json={"magnitude": 6.1, "depth_km": 10,
                                     "lat": 34.0, "lon": 72.5})
    assert r.status_code == 200
    eid = r.json()["id"]
    g = client.get(f"/events/{eid}")
    assert g.status_code == 200 and g.json()["source"] == "MANUAL"


def test_manual_event_out_of_region_rejected(client):
    r = client.post("/events", json={"magnitude": 6.1, "depth_km": 10,
                                     "lat": 0.0, "lon": 0.0})
    assert r.status_code == 422
```

> Note: these tests write to the test DB without per-test rollback (they use the
> app pool, not `db_conn`). Keep them few and self-cleaning: each asserts on the
> row it created by id. If you prefer full isolation, gate them behind a separate
> marker and `TRUNCATE seismic_event` in the fixture teardown.

- [ ] **Step 2: Add endpoints to `src/eqmon/api.py`**

Add these imports near the top (with the existing imports):
```python
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel as _BaseModel  # alias if BaseModel already imported

from . import db
from .events.ingest import ingest
from .events.repo import create_manual_event, get_event, list_events
from .events.sources import USGSSource
from .impact import compute_event_impact
```
(If `BaseModel`, `Field`, `field_validator` are already imported, reuse them — do
not import twice.)

Add models and routes (after the existing `EventRequest` / `/intensity`):
```python
class ManualEvent(BaseModel):
    magnitude: float = Field(ge=0.0, le=10.0)
    depth_km: float = Field(ge=0.0, le=700.0)
    lat: float
    lon: float
    occurred_at: datetime | None = None

    @field_validator("lat")
    @classmethod
    def _lat_region(cls, v):
        _, miny, _, maxy = config.COVERAGE_BBOX
        if not (miny <= v <= maxy):
            raise ValueError("latitude outside Coverage Region")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_region(cls, v):
        minx, _, maxx, _ = config.COVERAGE_BBOX
        if not (minx <= v <= maxx):
            raise ValueError("longitude outside Coverage Region")
        return v


@app.post("/events")
def create_event(ev: ManualEvent):
    with db.get_conn() as conn:
        row = create_manual_event(conn, magnitude=ev.magnitude, depth_km=ev.depth_km,
                                  lon=ev.lon, lat=ev.lat, occurred_at=ev.occurred_at)
        conn.commit()
    return row


@app.post("/events/ingest")
def ingest_events():
    with db.get_conn() as conn:
        result = ingest(conn, USGSSource())
        conn.commit()
    return result.__dict__


@app.get("/events")
def get_events(since: datetime | None = None, min_magnitude: float | None = None,
               limit: int = 100):
    with db.get_conn() as conn:
        return list_events(conn, since=since, min_magnitude=min_magnitude, limit=limit)


@app.get("/events/{event_id}")
def event_detail(event_id: int):
    with db.get_conn() as conn:
        row = get_event(conn, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")
    return row


@app.post("/events/{event_id}/impact")
def event_impact(event_id: int):
    with db.get_conn() as conn:
        event = get_event(conn, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        impact = compute_event_impact(conn, event, get_grid())
    return impact
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_events_api.py -v`
Then the full suite: `uv run pytest -q`
Expected: event API tests pass with a test DB (or skip); all Plan A tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/eqmon/api.py tests/test_events_api.py
git commit -m "feat: event API (manual input, ingest, list, detail, impact)"
```

---

### Task 8: Frontend — event list and district impact table

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`

- [ ] **Step 1: Add markup to `web/index.html`**

Inside `#panel`, after the `#status` div, add an ingest button and an events list:
```html
    <button id="ingest" style="margin-top:8px;background:#2c3e50">Pull USGS feed</button>
    <div id="events" style="margin-top:10px;max-height:160px;overflow:auto;font-size:12px"></div>
    <div id="impact" style="margin-top:10px;max-height:200px;overflow:auto;font-size:12px"></div>
```

- [ ] **Step 2: Add logic to `web/app.js`**

Append:
```javascript
const eventsEl = document.getElementById("events");
const impactEl = document.getElementById("impact");

async function refreshEvents() {
  const resp = await fetch("/events?limit=20");
  if (!resp.ok) return;
  const events = await resp.json();
  eventsEl.innerHTML = "<strong>Catalog</strong>" + events.map(e =>
    `<div class="evt" data-id="${e.id}" style="cursor:pointer;padding:3px 0;border-bottom:1px solid #eee">
       M${e.magnitude.toFixed(1)} · ${e.source} · ${new Date(e.occurred_at).toLocaleString()}
     </div>`).join("");
  document.querySelectorAll(".evt").forEach(el =>
    el.addEventListener("click", () => showImpact(el.dataset.id)));
}

async function showImpact(id) {
  impactEl.textContent = "Computing impact…";
  const resp = await fetch(`/events/${id}/impact`, { method: "POST" });
  if (!resp.ok) { impactEl.textContent = "Impact failed"; return; }
  const data = await resp.json();
  if (intensityLayer) map.removeLayer(intensityLayer);
  intensityLayer = L.geoJSON(data.bands, { style }).addTo(map);
  if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  const top = data.districts.filter(d => d.mmi_max > 0).slice(0, 12);
  impactEl.innerHTML = "<strong>District impact</strong><table style='width:100%'>" +
    "<tr><th align=left>District</th><th>Max</th><th>Repr</th></tr>" +
    top.map(d => `<tr><td>${d.name ?? "?"}</td><td align=center>${d.mmi_max}</td>` +
                 `<td align=center>${d.mmi_repr}</td></tr>`).join("") + "</table>";
}

document.getElementById("ingest").addEventListener("click", async () => {
  statusEl.textContent = "Pulling USGS feed…";
  const r = await fetch("/events/ingest", { method: "POST" });
  const res = await r.json();
  statusEl.textContent = `Ingest: ${res.inserted} new of ${res.fetched}`;
  refreshEvents();
});

refreshEvents();
```

- [ ] **Step 3: Manual verification**

Run: `uv run uvicorn eqmon.api:app --port 8000` (with `DATABASE_URL` set and
districts loaded). Open `http://localhost:8000/`, click **Pull USGS feed** →
the catalog populates; click an event → its MMI bands render and the district
impact table lists affected districts with max + representative MMI.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: event list, USGS pull, and district impact table in the UI"
```

---

### Task 9: Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the "Not yet built" section**

Update `README.md`'s closing section to document the event subsystem: the
`DATABASE_URL` / `DATABASE_URL_TEST` setup, `CREATE EXTENSION postgis`, running
`scripts/load_districts.py`, the `/events*` endpoints, and that the MET adapter
is a stub behind `SeismicSource`. Note that the Vs30 grid remains a GeoTIFF and
is not in the database.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: event catalog setup and endpoints"
```

---

## Self-Review notes

- **Spec coverage:** event catalog → Task 1/3; Manual Event Input → Task 3/7;
  USGS ingestion + `SeismicSource` + MET stub → Task 4; dedup (60 s/50 km, MET
  preferred) → Task 5; district impact (max band via SQL + representative point)
  → Task 6; API → Task 7; UI → Task 8. All design decisions covered.
- **Type consistency:** event rows are dicts with keys `id, source, occurred_at,
  magnitude, depth_km, lon, lat, cluster_id, is_canonical` everywhere (repo →
  impact → api); `RawEvent` fields consistent (sources → ingest); `IngestResult`
  fields `source, fetched, inserted, errors` (ingest → api `.__dict__`);
  `compute_event_impact` returns `{bands, districts:[{name,province,mmi_max,
  mmi_repr}]}` (impact → api → app.js).
- **Placeholder scan:** none. `METSource.fetch` raising `NotImplementedError` is
  an intentional, documented stub per the approved design, not a placeholder.
- **Known fragility flagged inline:** event-API tests don't use per-test rollback
  (they exercise the real pool) — Task 7 Step 1 note explains the self-cleaning
  approach. `_recluster` uses min-id-in-window clustering (pairwise-correct,
  which is all the dedup window needs) — documented in the `ingest.py` docstring.

## Operator setup recap (one-time)

```bash
# 1. enable PostGIS and create DBs (psql): CREATE EXTENSION postgis; in eqmon + eqmon_test
# 2. export DATABASE_URL=... and DATABASE_URL_TEST=...
uv run python -c "from eqmon.db import init_schema; init_schema()"
uv run python scripts/load_districts.py
uv run uvicorn eqmon.api:app --port 8000
```
