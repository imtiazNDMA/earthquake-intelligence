# Source filter (USGS / PMD / Manual) across Catalog and Dashboard

**Date:** 2026-07-07
**Status:** Approved design, pending implementation plan

## Goal

Let users restrict both the event Catalog and the Analytics Dashboard to a
single event source — USGS, Pakistan MET (PMD), or Manual — or view all sources
combined (the default). The Catalog already has a working source dropdown; this
work adds the same control to the Dashboard and unifies the filtering semantics
across both surfaces.

## Core semantic

The `seismic_event.source` column holds exactly one of `'USGS'`, `'MET'`,
`'MANUAL'` (the UI labels `MET` as "Pakistan MET (PMD)"). Cross-source
deduplication clusters the same physical quake reported by multiple agencies and
keeps one row as canonical (`is_canonical = TRUE`); MET wins canonical over USGS
for shared quakes. Both the catalog query (`_build_where`) and analytics query
(`analytics_rows`) currently hard-code `is_canonical = TRUE` to avoid
double-counting shared quakes.

That dedup gate only matters when **mixing** sources. When the view is pinned to
a single source, there is no cross-source double-counting to prevent, and keeping
the gate would hide that agency's quakes that were deduped away under another
agency's canonical row (e.g. USGS-only would drop every quake where MET won
canonical). Therefore:

- **Source = All (default)** → keep `is_canonical = TRUE` (dedup, unchanged).
- **Source = USGS / MET / MANUAL** → add `source = %s` **and drop the
  `is_canonical` gate** → the full agency catalogue.

This single rule applies identically to the catalog list, catalog count, and
analytics. It is a deliberate, approved change to existing catalog counts:
single-source catalog numbers will now include rows that were previously hidden
as non-canonical.

## Backend changes (`src/eqmon/`)

1. **`repo._build_where`** (`repo.py:99`) — make the canonical gate conditional.
   Add `is_canonical = TRUE` only when `source is None`. The `source = %s` clause
   already exists (line 110). This covers `list_events` and `count_events` in one
   place.

2. **`repo.analytics_rows`** (`repo.py:173`) — add a `source: str | None = None`
   parameter. When set, add `source = %s` to the clause list and **omit**
   `is_canonical = TRUE`; when `None`, behavior is unchanged (canonical gate
   kept). The magnitude/depth quality gate (`magnitude >= -1`, `magnitude < 10`,
   `depth_km IS NOT NULL`) is retained regardless of source.

3. **`GET /analytics`** (`api.py:378`) — add a `source: str | None = None` query
   parameter. Validate it against `{"USGS", "MET", "MANUAL"}`; treat any other
   value (including empty string) as `None` (all sources). Pass the validated
   value to `analytics_rows`. `GET /events` and `GET /events/export` already
   accept and plumb `source`.

## Frontend changes (`web/`)

4. **Dashboard filter bar** — add a `#f-source` `<select>` to
   `_dashScaffoldHTML()` (`app.js:1465`) with options: **All · USGS · Pakistan
   MET (PMD) · Manual** (values `"" / USGS / MET / MANUAL`). Add `source` to
   `_analyticsState` (`app.js:1297`), include it in the querystring built by
   `_analyticsQuery()` (`app.js:1299`, appended only when non-empty), and wire its
   `change` event in `_wireFilterBar()` (`app.js:1486`) to update state and
   re-render.

5. **Dynamic provenance label** — `renderProvenance()` (`app.js:1306`) hard-codes
   `"USGS + PMD"`. Make the label reflect the active filter: All → "USGS + PMD",
   USGS → "USGS only", MET → "Pakistan MET (PMD) only", MANUAL → "Manual only".

6. **Label parity** — align the existing catalog dropdown option labels
   (`index.html:73`) with the dashboard wording so both read identically
   (e.g. "Pakistan MET (PMD)").

## Testing (`tests/`)

- `analytics_rows(source='USGS')` returns USGS rows that are non-canonical
  (proving the `is_canonical` gate is dropped) and excludes MET rows;
  `analytics_rows(source=None)` still returns only canonical rows.
- `count_events` / `list_events`: a single-source count includes rows previously
  hidden as non-canonical; the all-source count remains deduped.
- Endpoint smoke test: `GET /analytics?source=USGS` returns 200 and analytics
  computed over the USGS-only set; an invalid `source` value falls back to all
  sources.

## Out of scope (YAGNI)

- No global synced filter state between Catalog and Dashboard — each surface keeps
  its own independent dropdown with identical options and semantics.
- No new source values.
- No changes to map markers, ingestion, or dedup/clustering logic.
