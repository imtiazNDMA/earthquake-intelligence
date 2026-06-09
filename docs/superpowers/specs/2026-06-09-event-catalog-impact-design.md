# Event Catalog & Impact — Design (Plan B)

**Status:** Approved 2026-06-09. Supersedes nothing; builds on the merged Plan A
(intensity engine + map).

## Purpose

Add the *event* subsystem to the platform: a persistent earthquake event catalog,
operator-entered events (Manual Event Input), automated ingestion from the USGS
feed (Secondary Seismic Source) behind an interface ready for the Pakistan MET
feed (Primary Seismic Source), and per-event district impact aggregation. The
Plan A engine (PGA→MMI, contour bands) is reused unchanged.

Domain language follows `CONTEXT.md` (Coverage Region, Primary/Secondary Seismic
Source, Manual Event Input, Default Site Condition, Primary Focus Country).

## Scope

In scope:
- PostGIS-backed event catalog.
- Manual Event Input (operator-entered events).
- USGS ingestion (Secondary) with a `SeismicSource` interface; `METSource`
  (Primary) is a documented stub until its feed format is known.
- Source dedup (Primary preferred over Secondary).
- Per-event district impact: max-band-intersecting and representative-point MMI.
- Light frontend: event list + markers + district impact table.

Out of scope (later plans):
- Live MET feed adapter (interface is provided now).
- Built-in scheduler/cron for polling (ingest is triggerable; scheduling is ops).
- Authentication / multi-tenant.

## Decisions (locked)

1. **USGS now, MET behind interface.** Build USGS ingestion fully; define
   `SeismicSource` so a MET adapter slots in later without rework.
2. **Postgres + PostGIS, spatial-in-SQL.** Events and district geometry live in
   PostGIS; district↔band joins use SQL spatial predicates. Use the existing
   local PostGIS 3.6 instance via `DATABASE_URL`.
3. **District MMI = both** max-band-intersecting (worst case) **and**
   representative-point value.
4. **psycopg 3 + raw parameterized SQL + `schema.sql`** (no ORM, no Alembic) so
   the PostGIS calls are explicit and auditable.
5. **Dedup window:** events match if within **≤ 60 s and ≤ 50 km**; canonical =
   higher-priority source (MET > USGS). Manual events stand alone.

## Data model (PostGIS, SRID 4326)

`seismic_event`
- `id BIGSERIAL PK`
- `source TEXT` — one of `MET`, `USGS`, `MANUAL`
- `source_event_id TEXT NULL` — provider id (null for MANUAL)
- `occurred_at TIMESTAMPTZ`
- `magnitude DOUBLE PRECISION`
- `depth_km DOUBLE PRECISION`
- `geom geometry(Point, 4326)` — epicenter
- `cluster_id BIGINT NULL` — dedup grouping (FK to a canonical event id)
- `is_canonical BOOLEAN DEFAULT TRUE`
- `created_at TIMESTAMPTZ DEFAULT now()`
- `UNIQUE (source, source_event_id)` — makes feed ingest idempotent (partial
  index where `source_event_id IS NOT NULL`).
- GIST index on `geom`; btree on `occurred_at`.

`district`
- `id BIGSERIAL PK`
- `name TEXT`, `province TEXT`
- `geom geometry(MultiPolygon, 4326)`
- GIST index on `geom`.
- Loaded once from `boundary/district.geojson` by `scripts/load_districts.py`
  (properties `DISTRICT`, `PROVINCE`).

No persisted impact table — impact is computed on demand per event (cheap: ~hundreds
of contour bands × 161 districts).

## Components

```
src/eqmon/
  db.py                  psycopg connection pool; init_schema(); helpers
  events/
    __init__.py
    sources.py           SeismicSource Protocol; USGSSource; METSource (stub)
    ingest.py            fetch -> upsert -> cluster/dedup
    repo.py              create_manual_event, list_events, get_event
  impact.py              event -> contour bands + district impact (SQL spatial)
schema.sql               table + index DDL (idempotent: CREATE ... IF NOT EXISTS)
scripts/load_districts.py  one-time district load into PostGIS
```

### SeismicSource interface (`sources.py`)
```python
class SeismicSource(Protocol):
    name: str            # 'USGS' | 'MET'
    def fetch(self, since: datetime) -> list[RawEvent]: ...
```
`RawEvent` is a dataclass: `source, source_event_id, occurred_at, magnitude,
depth_km, lon, lat`. `USGSSource.fetch` GETs the USGS GeoJSON feed
(`all_day`/`all_hour` summary), parses features, filters to `COVERAGE_BBOX`,
and maps to `RawEvent`. `METSource.fetch` raises `NotImplementedError` with a
docstring noting the feed format is TBD.

### Ingestion (`ingest.py`)
`ingest(source) -> IngestResult(fetched, inserted, deduped, errors)`:
fetch → for each `RawEvent`, upsert by `(source, source_event_id)` → run dedup
clustering (find events within 60 s / 50 km via `ST_DWithin` on geography,
assign `cluster_id`, set `is_canonical` to the highest-priority source in the
cluster). Network/parse failures are caught per-source and surfaced in
`IngestResult.errors`; ingestion never raises out.

### Impact (`impact.py`)
`compute_event_impact(event) -> EventImpact`:
1. Run the Plan A engine on the cached Vs30 grid → MMI grid → contour bands
   (`mmi_to_geojson`).
2. **Max band per district (SQL):** insert the bands into a temp table (or pass
   as a values list), `ST_Intersects(district.geom, band.geom)`, group by
   district, `max(mmi_lower)`.
3. **Representative-point MMI:** `SELECT id, ST_X(ST_PointOnSurface(geom)),
   ST_Y(...) FROM district`; run the engine at those 161 points (small array)
   for the representative value.
4. Return `{ bands: GeoJSON, districts: [{name, province, mmi_max, mmi_repr}] }`.

## API (new endpoints, FastAPI)

- `POST /events` — Manual Event Input. Body `{magnitude, depth_km, lat, lon,
  occurred_at?}`; validates Coverage Region (reuse existing validator); inserts
  `source='MANUAL'`; returns the created event.
- `POST /events/ingest` — pull USGS now; returns `IngestResult`.
- `GET /events` — list canonical events (filters: `since`, `min_magnitude`,
  `limit`).
- `GET /events/{id}` — event detail.
- `POST /events/{id}/impact` — compute and return bands + district impact table.

The Plan A `POST /intensity` (ad-hoc, no persistence) is unchanged.

## Frontend (additive)

- An event-list panel (right side) showing recent catalog events with magnitude,
  time, source; each event is a map marker.
- Selecting an event calls `/events/{id}/impact`, renders the bands (reusing the
  Plan A render path) and shows a district impact table (district, max MMI,
  representative MMI), sorted by max MMI.
- The existing manual form can `POST /events` then immediately request impact.

## Error handling

- USGS fetch: timeout (configurable, default 15 s), non-200, and malformed JSON
  are caught; the event is skipped and counted in `errors`; partial ingests
  succeed.
- DB connectivity: a failed connection surfaces as HTTP 503 with a clear message;
  the service does not crash at import time if the DB is down (lazy pool).
- Coverage Region: both manual input and USGS ingestion drop out-of-region
  events (manual → 422; ingest → silently filtered, counted).
- Dedup is idempotent: re-running ingest does not create duplicates or re-cluster
  incorrectly.

## Testing

- **DB tests** use a dedicated test database via `DATABASE_URL_TEST`. A pytest
  fixture connects, applies `schema.sql` once, and wraps each test in a
  transaction rolled back at teardown. If `DATABASE_URL_TEST` is unset, these
  tests `skip` with a clear message (pure-logic tests still run).
- `USGSSource` parsing/filtering tested against a saved GeoJSON fixture (no
  network) — includes an out-of-region feature that must be filtered out.
- Dedup: seed two events 30 s / 10 km apart from USGS+MET → one cluster, MET
  canonical; seed two far apart → two clusters.
- Manual Event Input: in-region inserts (200), out-of-region rejected (422).
- Impact: seed a known event + a couple of synthetic districts (small polygons),
  assert `mmi_max ≥ mmi_repr` and that a district under the epicenter reports a
  high band.
- API: happy-path + error-path per endpoint via `TestClient`.

## Build sequence (for the plan)

1. DB foundation: `db.py`, `schema.sql`, test fixture.
2. District load: `scripts/load_districts.py`.
3. Event repo + Manual Event Input endpoint.
4. `SeismicSource` + `USGSSource` + ingest + dedup + `/events/ingest`.
5. Catalog list/detail endpoints.
6. `impact.py` + `/events/{id}/impact` (spatial SQL).
7. Frontend event list + impact table.

Each step is independently testable and leaves the app runnable.
