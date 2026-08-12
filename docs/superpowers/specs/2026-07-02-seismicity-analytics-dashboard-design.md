# Seismicity Analytics Dashboard — Design

**Date:** 2026-07-02
**Status:** Approved for planning
**Scope:** Backend (`src/eqmon/`, `scripts/`, `migrations/`) + Frontend (`web/`) + tests

## Problem

The current Analytics view (`renderDashboard` in `web/app.js`, backed by
`GET /events/stats`) presents six summary stat-boxes and seven charts computed
over the **entire multi-year catalog across the whole Iran→China coverage box**.
These are catalog-description "vanity" metrics, not decision-support:

- Headline numbers ("Recorded Earthquakes 11,986", "Average Strength 3.88",
  "Activity Pattern 0.319") describe the file, not the hazard.
- The b-value (labelled "Activity Pattern") is computed by a crude linear fit
  over an incomplete, partly-dirty catalog — it is not a defensible number.
- Charts like "Time of Day", "Day of Week", and a raw "Estimated Energy" ramp
  carry no analytical value for hazard.
- The hero copy ("National Seismic Intelligence Platform / Plain-language
  earthquake overview for disaster management decisions") reads as placeholder
  marketing and undermines credibility.

## Goal

Turn the section into a **serious analytical seismicity/hazard intelligence
dashboard** for analysts and planners: rigorous magnitude-frequency statistics,
spatial hotspots, tectonic-zone hazard character, depth regimes, and temporal
rate behaviour — all sliceable by an analyst.

## Decisions (from brainstorming)

1. **Purpose:** analytical seismicity/hazard intelligence (not operational
   "what's happening now").
2. **Spatial framing:** *combination* — a data-driven hotspot grid over the full
   coverage region **plus** a per-tectonic-zone hazard breakdown for Pakistan.
3. **Interactivity:** filters (time window / minimum magnitude / zone) **plus**
   click-to-drill on hotspot cells and zones, with linked (cross-filtered)
   panels and a breadcrumb reset.
4. **Rigor:** full seismological rigor — magnitude-of-completeness (Mc),
   maximum-likelihood b-value with uncertainty, Gardner–Knopoff declustering,
   background-vs-total rate, mainshock/aftershock split, sequence detection.
5. **Architecture:** *hybrid* — declustering + spatial-zone membership are global
   and expensive, computed once per ingest and persisted; Mc / b-value / rates /
   grid / zone rollups are computed on-request in NumPy over the filtered set.
6. **Magnitude handling:** use each event's reported (preferred) magnitude as-is
   regardless of `mag_type`, apply **no** ad-hoc scale conversions; surface the
   `mag_type` mixture as a documented caveat in the provenance panel.

## Non-Goals

- No operational/real-time alerting view (that is the PAGER section's job).
- No ad-hoc magnitude-scale conversion regressions (documented caveat instead).
- No new charting/mapping dependency — reuse Chart.js and Leaflet.
- No change to intensity/contour computation.

## Identity & Layout

Replace the marketing hero with the section title **"Seismicity Analytics"** and
a factual **provenance line**, e.g.:

```
USGS + PMD · 2015–2026 · 11,942 events · Mc 3.2 · declustered 12 Jul 2026
```

A persistent **filter bar** drives every panel: `Time window`, `Min magnitude`
(number or `≥Mc`), `Zone`, and a drill breadcrumb when a cell/zone is selected.

```
┌ Seismicity Analytics ────────────────────────────────────────────┐
│ USGS+PMD · 2015–2026 · 11,942 ev · Mc 3.2 · declustered 12 Jul    │
│ [ Time: 1y ▾ ] [ Min mag: ≥Mc ▾ ] [ Zone: All ▾ ]   ⟲ reset      │
├───────────────────────────────────────────────────────────────────┤
│ KPI STRIP (contextual, with Δ vs previous window)                 │
│  b 0.92±0.04 │ Mc 3.2 │ Bkgd rate 118/yr ▲ │ Aftershocks 41%      │
│  Largest M6.3 (Hindu Kush) │ Active sequences 3                    │
├──────────────────────────────────────┬────────────────────────────┤
│ HOTSPOT MAP (grid; toggle:           │ TECTONIC-ZONE TABLE (PK)   │
│  density / max-mag / mean-depth)     │  zone·N·b±σ·Mc·med.depth·  │
│  + tectonic-zone overlay             │  maxM·rate·%aftershk       │
│  click cell/zone → drill everything  │  (sortable; row → focus)   │
├──────────────────────────────────────┴────────────────────────────┤
│ MAGNITUDE–FREQUENCY (Gutenberg–Richter)   │ DEPTH REGIME           │
│  cumulative + incremental, Mc marked,     │  crustal/intermediate/ │
│  MLE fit line, b=0.92±0.04 annotated      │  deep split + depth–mag│
├───────────────────────────────────────────┴────────────────────────┤
│ SEISMICITY RATE OVER TIME                                          │
│  total vs declustered (background); sequences shaded; quiescence   │
├───────────────────────────────────────────────────────────────────┤
│ PROVENANCE / DATA HEALTH: source split · completeness · last ingest│
└───────────────────────────────────────────────────────────────────┘
```

Every panel obeys the filter bar. Clicking a hotspot cell or a zone row
cross-filters all panels and drops a breadcrumb to reset. Dropped from the old
dashboard: the six vanity stat-boxes, "Time of Day", "Day of Week", and the raw
"Estimated Energy" ramp.

## Methodology

All statistics are computed on the **filtered** set per request, except
declustering and zone membership, which are global and persisted at ingest.

### 0. Quality gate (before anything)

Exclude non-physical rows: magnitude outside `[-1, 10)` (the same bound
`parse_met()` enforces — kills the M10/M317 garbage), null depth or geom. This
gate is the single source of truth; the excluded count is shown in the
provenance panel.

### 1. Magnitude of completeness (Mc)

Maximum-Curvature (MAXC): Mc = the magnitude bin (Δ = 0.1) with the peak count in
the **non-cumulative** frequency-magnitude distribution, plus the standard
**+0.2** correction. Guarded by `MC_MIN_N`; below that, Mc is "insufficient data"
and dependent statistics are suppressed rather than fabricated.

### 2. b-value

Aki–Utsu maximum-likelihood (not a linear fit), over events with M ≥ Mc:

```
b = log10(e) / (M̄ − (Mc − Δ/2)),   Δ = 0.1
```

Uncertainty via Shi & Bolt (1982):

```
σ_b = 2.30 · b² · sqrt( Σ(Mᵢ − M̄)² / (N (N − 1)) )
```

Reported as `b = 0.92 ± 0.04 (Mc 3.2, N 4,120)`; suppressed when N < `BVALUE_MIN_N`
(= 50). The same estimator drives each zone in the tectonic-zone table (a zone
with N < 50 shows "—").

### 3. Declustering — Gardner & Knopoff (1974)

Space–time windows, applied to the whole catalog processed largest-magnitude
first:

- distance `L(M) = 10^(0.1238·M + 0.983)` km
- time `T(M) = 10^(0.032·M + 2.7389)` days for M ≥ 6.5,
  else `10^(0.5409·M − 0.547)` days

Events inside a larger event's window (before → foreshock, after → aftershock)
inherit that event's `sequence_id`; the largest keeps `is_mainshock = TRUE`.
Deterministic and standard. Persisted as columns on `seismic_event` at ingest.

### 4. Rates & clustering

- `background_rate` = mainshocks with M ≥ Mc per year within the window.
- `total_rate` = all events with M ≥ Mc per year within the window.
- Both shown with **Δ vs the previous equal-length window**.
- `% aftershocks` = 1 − mainshocks / total.
- The rate-over-time plot overlays total vs background so sequences and
  quiescence are visible.

### 5. Spatial

Hotspot map bins events into `GRID_CELL_DEG` (0.25°) cells; per-cell metric is
count/density, max magnitude, or mean depth (toggle). Per-cell and per-zone
membership is precomputed at ingest (`zone_id` via PostGIS `ST_Contains` against
the loaded tectonic zones), so on-request grouping is a NumPy group-by. b-value
is shown only at zone level (cells rarely reach N ≥ 50).

### 6. Depth regimes

Crustal < 35 km · intermediate 35–70 km · deep > 70 km (the Hindu Kush deep zone
matters here). Depth histogram + depth-vs-magnitude scatter coloured by regime.

### Magnitude harmonization (caveat)

The catalog mixes `mag_type` (mb, mwr, ml, …). Each event already carries a single
preferred magnitude from its source; we use that value as-is and apply no
scale conversions. The `mag_type` mixture is surfaced as a documented caveat in
the provenance panel.

## Data Model

One migration (`migrations/003_analytics.sql`):

- `seismic_event` gains three nullable columns: `is_mainshock BOOLEAN`,
  `sequence_id BIGINT`, `zone_id BIGINT`.
- New table `tectonic_zone (id BIGSERIAL PK, name TEXT, geom
  geometry(MultiPolygon, 4326))` + GIST index on `geom`.

## Data Flow / Architecture

**Ingest (`src/eqmon/events/ingest.py`).** After the existing dedup
`_recluster()`, add two global, idempotent post-steps over the canonical catalog:

1. `_decluster()` — Gardner–Knopoff → sets `is_mainshock` / `sequence_id`.
2. `_assign_zones()` — `UPDATE … SET zone_id` via `ST_Contains(tectonic_zone.geom,
   event.geom)`.

Both recompute each ingest (matching the `_recluster` pattern). A one-off backfill
runs them over the current catalog.

**Zone loader (`scripts/load_tectonic_zones.py`, new).** Mirrors
`load_boundaries.py`: reads `data/PAK_Tectoniz_Zones/PAK_Tectonic_Zones.shp` into
`tectonic_zone`, idempotent with a row-count guard and `--force`.

**Analytics module (`src/eqmon/analytics.py`, new).** Pure, unit-testable
functions with no DB/HTTP dependency:

- `mc_maxc(mags) -> float | None`
- `b_value_aki(mags, mc) -> (b, sigma, n) | None`
- `decluster_gardner_knopoff(events) -> list[flag]` (imported by ingest + tests)
- `spatial_grid(rows, cell_deg) -> cells`
- `depth_regime_split(rows) -> counts`
- `rate_series(rows, mainshock_flags, window) -> series`

Tunables in `config.py`: `GRID_CELL_DEG = 0.25`, `MC_MIN_N`,
`BVALUE_MIN_N = 50`, depth-regime thresholds (35 km, 70 km).

**API (`src/eqmon/api.py`).**

- `GET /analytics` replaces the dashboard's use of `/events/stats`. Query params:
  `window` (`30d|1y|5y|all` or explicit `from`/`to`), `min_mag` (number or `mc`),
  `zone_id` (optional), `bbox` (optional, for cell drill-down). Handler runs one
  filtered `SELECT`, computes in NumPy, and returns a composite JSON:
  `{ provenance, kpis, grid, zones, fmd, depth, rate }`. Sub-second on ~12k rows.
  Drill-down is the same endpoint with `zone_id` / `bbox` set.
- `GET /zones` returns the tectonic zones as GeoJSON for the map overlay + zone
  selector.
- `GET /events/stats` is retired (the dashboard is its only consumer, verified).

**Frontend (`web/app.js`, `web/index.html`, `web/styles.css`).** A small
dashboard state module holds `{ window, minMag, zoneId, bbox }`; any change
re-queries `/analytics` and redraws. Charts stay on Chart.js, map on Leaflet
(both already dependencies). The hotspot grid renders as coloured GeoJSON cells;
tectonic zones render as an overlay from `/zones`. Clicking a cell or zone sets
state + breadcrumb; reset clears the drill.

## Error / Edge Handling

- Empty window or zero events after filtering → panels render an explicit empty
  state, not an error.
- N below `MC_MIN_N` / `BVALUE_MIN_N` → Mc / b-value show "insufficient data";
  dependent panels degrade gracefully rather than showing fabricated numbers.
- Any statistic that could overflow (e.g. moment/energy proxies) clamps the
  magnitude exponent to the physical max, consistent with the quality gate.
- `/analytics` validates params and returns HTTP 400 on malformed `window`,
  `min_mag`, or `zone_id`.

## Testing (TDD)

**Unit — `tests/test_analytics.py` (pure functions, no DB):**

- `mc_maxc`: synthetic FMD with a known peak bin → expected Mc (incl. +0.2).
- `b_value_aki`: magnitudes drawn from a known-b exponential → recovers b within
  tolerance; verify Shi–Bolt σ; N < 50 → suppressed.
- `decluster_gardner_knopoff`: hand-built mainshock + aftershocks inside its L/T
  window → tagged aftershocks sharing `sequence_id`; event outside → own
  mainshock; boundary cases at the window edges.
- `spatial_grid`, `depth_regime_split` (edges at 35 / 70 km), `rate_series`
  (background vs total from known daily counts).

**Integration — DB (`db_conn` fixture, skips without `DATABASE_URL_TEST`):**

- Ingest wiring: after `ingest()`, `is_mainshock` / `sequence_id` / `zone_id` are
  populated (insert a small `tectonic_zone` polygon in-transaction for the join).
- `GET /analytics` via TestClient: correct composite structure; `window` /
  `min_mag` / `zone_id` demonstrably change the result; empty-window and low-N
  cases handled gracefully.
- `load_tectonic_zones.py` idempotency (row-count guard, `--force`).
- Quality gate: an out-of-range magnitude row is excluded from every statistic.

## Phasing (5 vertical slices, each independently shippable & verifiable)

1. **Data foundation** — migration (3 columns + `tectonic_zone`), loader script,
   `analytics.py` (Mc, b-value, decluster) with unit tests, ingest `_decluster` +
   `_assign_zones` + one-off backfill. Verify via tests + DB inspection.
2. **Analytics API** — `GET /analytics` (params → composite JSON) + `GET /zones`,
   with API tests. Verify via TestClient / curl.
3. **Frontend core** — filter bar + contextual KPI strip + G-R (Mc/MLE) +
   depth-regime + rate panels on `/analytics`; removes the vanity boxes and
   placeholder copy. Browser-verify.
4. **Spatial + drill-down** — hotspot map + zone table + click-to-drill linked
   state + breadcrumb reset. Browser-verify.
5. **Polish** — provenance line, mag-type caveat, empty/low-N states, retire
   `/events/stats`. Browser-verify both themes.

## Files Touched

- `migrations/003_analytics.sql` *(new)* — columns + `tectonic_zone`.
- `scripts/load_tectonic_zones.py` *(new)* — zone loader.
- `src/eqmon/analytics.py` *(new)* — pure analytics functions.
- `src/eqmon/events/ingest.py` — `_decluster()`, `_assign_zones()`, backfill.
- `src/eqmon/api.py` — `GET /analytics`, `GET /zones`; retire `/events/stats`.
- `src/eqmon/config.py` — grid/Mc/b-value/depth tunables.
- `web/app.js`, `web/index.html`, `web/styles.css` — filter bar, panels, map,
  drill-down, provenance; remove vanity content and placeholder copy.
- `tests/test_analytics.py` *(new)*, plus API/ingest integration tests.

## Open Questions

None blocking.
