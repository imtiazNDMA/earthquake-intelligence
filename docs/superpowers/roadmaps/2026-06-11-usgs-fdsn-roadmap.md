# USGS FDSN Event API — Feature Roadmap

**Date:** 2026-06-11
**API:** USGS FDSN event web service — https://earthquake.usgs.gov/fdsnws/event/1/
**Status:** Roadmap approved; Phase 0 in progress.

## Context: where the project stands today

The platform currently ingests events from the USGS **real-time feed**
(`https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson`),
not the FDSN `query` API. Implications of the current approach:

- **Last 24 hours only** — the `all_day` feed is a rolling window; there is no
  historical depth.
- **Global fetch, client-side filter** — `USGSSource.fetch` downloads the whole
  feed and `parse_usgs` filters to `COVERAGE_BBOX` (44.0, 8.0, 105.0, 56.0) in
  Python.
- **Seven fields captured** — `RawEvent` keeps only `source`, `source_event_id`,
  `occurred_at`, `magnitude`, `depth_km`, `lon`, `lat`. Everything else USGS
  provides (place, magType, event type, review status, tsunami flag, DYFI
  `felt`/`cdi`, ShakeMap `mmi`, PAGER `alert`, `sig`, `gap`, product links) is
  discarded.
- **Manual ingest** — the "Pull USGS feed" button calls `POST /events/ingest`,
  which upserts by `(source, source_event_id)` and re-clusters/dedups
  (priority MET > USGS > MANUAL). `METSource` is a stub.

Relevant code: `src/eqmon/events/sources.py` (feed + parse), `events/ingest.py`
(upsert + recluster), `events/repo.py` (reads), `schema.sql` (`seismic_event`),
`api.py` (`/events*` endpoints), `config.py` (`COVERAGE_BBOX`).

## Key technical facts about the FDSN `query` API

- Endpoint: `https://earthquake.usgs.gov/fdsnws/event/1/query` plus methods
  `count`, `version`, `catalogs`, `contributors`, `application.json`.
- Output formats: quakeml/xml (default), **geojson**, csv, kml, text. The
  **geojson output matches the real-time feed's GeoJSON schema**, so the existing
  `parse_usgs` logic is reusable.
- Filtering parameters relevant here: `starttime`, `endtime`, `updatedafter`;
  rectangle (`minlatitude`/`maxlatitude`/`minlongitude`/`maxlongitude`) or circle
  (`latitude`/`longitude`/`maxradiuskm`); `mindepth`/`maxdepth`;
  `minmagnitude`/`maxmagnitude`; `eventtype`, `reviewstatus`, `catalog`,
  `contributor`; `limit` (1–20000), `offset` (1+), `orderby`
  (time | time-asc | magnitude | magnitude-asc).
- Impact/intensity extensions: `alertlevel`/`min/maxalertlevel` (PAGER),
  `min/maxcdi` + `minfelt` (DYFI), `min/maxmmi` (ShakeMap), `min/maxsig`,
  `min/maxgap`, `producttype` (moment-tensor, focal-mechanism, shakemap,
  losspager, dyfi), `productcode`.
- **Hard limit: 20,000 results per request** (HTTP 400 if exceeded) — historical
  pulls MUST be windowed/paged.

## Phased plan

Each phase is a self-contained vertical slice, ordered by risk and dependency.
Every phase ships working, testable value and builds on the prior one.

### Phase 0 — Swap feed → FDSN `query` (enabler, low risk) — IN PROGRESS
Add an FDSN client that builds `query?format=geojson` with the region bounding
box, `minmagnitude`, and time parameters; reuse `parse_usgs` (identical GeoJSON
schema). Replace the global-fetch-then-filter pattern with server-side region +
magnitude filtering. The existing ingest/dedup/recluster pipeline and
`POST /events/ingest` are unchanged in behavior — only the data acquisition layer
changes. **Tests:** query-URL construction (region/time/magnitude params), fixture
parse, since→starttime mapping.

### Phase 1 — Historical backfill
`scripts/backfill_usgs.py` that walks a date range in time-windowed chunks
respecting the 20,000-result cap, using `orderby=time-asc` and `offset`/`limit`
paging. Idempotent upserts make re-runs/resume safe. **Tests:** window chunking,
cap handling, resume from watermark.

### Phase 2 — Rich metadata (schema + model expansion)
Extend `RawEvent` and `seismic_event` with nullable columns: `place`, `mag_type`,
`event_type`, `status`, `tsunami`, `felt`, `cdi`, `mmi`, `sig`, `gap`, `usgs_url`,
`alert`. Capture them in `parse_usgs`; expose via `repo` reads, `GET /events`, and
the Catalog panel (place, magType, reviewed/automatic badge). **Tests:** rich-field
parse, repo round-trip.

### Phase 3 — Server-side filtering + query surface
Add filters to `GET /events` (bbox, time range, min/max magnitude, eventtype,
minmmi, alertlevel, reviewstatus, orderby, offset) and a `GET /events/count`,
mirroring FDSN semantics but served from our DB. Frontend: filter controls in the
Catalog panel (magnitude slider, date range, "reviewed only"). **Tests:** repo
filtering combinations.

### Phase 4 — Authoritative products (ShakeMap / PAGER / DYFI)
Per-event enrichment via the event `detail` GeoJSON to pull USGS ShakeMap `mmi`,
PAGER `alert`, and DYFI. Display alongside our computed intensity in the Impact
panel as a cross-check; add `producttype`/`minmmi`/`alertlevel` filters. **Tests:**
product parse, missing-product handling.

### Phase 5 — Automation / near-real-time
Scheduled incremental polling using `updatedafter` + a stored watermark, becoming
the primary ingest path (the manual button remains for on-demand pulls). Handle
`reviewstatus` upgrades (automatic→reviewed updates the existing row). Optional:
alerts for significant events (`minsig`/`alertlevel`). **Tests:** watermark advance,
update-existing-event, review-status upgrade.

## Sequencing rationale

Phase 0 is the foundation every later phase depends on (all need the `query` API).
Phases 1–3 deepen the catalog (history → metadata → explorability). Phase 4 adds
authoritative cross-checks once rich metadata exists. Phase 5 automates once the
data model and query surface are stable.
