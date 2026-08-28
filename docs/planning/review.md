# Critical Project Review

Date: 2026-07-15

Scope: senior full-stack, backend/data, frontend, test/ops/performance, and seismology/domain review of the earthquake monitoring platform.

## Executive Assessment

The project has a strong starting shape: a small Python package, `uv`-managed dependencies, focused tests, a vectorized NumPy intensity engine, PostGIS-backed catalog work, and a simple static frontend. The biggest risks are not code style issues. They are operational safety, scientific defensibility, performance under realistic data volume, and public-facing interpretation.

The current system should be treated as an exploratory or operator-facing modeled shaking prototype, not as an authoritative ShakeMap, warning product, or damage/loss estimate.

## Review Team

Parallel specialist reviews were used to avoid one broad pass missing domain-specific problems.

- Backend/data engineering: FastAPI, PostGIS, ingest, migrations, geospatial joins, concurrency.
- Frontend/full-stack engineering: browser UX, API integration, accessibility, async races, client performance.
- Seismology/hazard engineering: PGA/MMI/Vs30 model validity, aftershock modeling, catalog quality, risk communication.
- Testing/DevOps/performance engineering: CI, deployment, artifacts, observability, benchmarks, reproducibility.

## P0 Findings

### 1. Static file path traversal risk

File: `src/eqmon/api.py`, `_serve_file`

The static file server joins the requested path to `web/` without resolving and enforcing that the resolved path remains under `web/`. A traversal request may expose repository files if the path resolves to an existing file.

Todo:
- Resolve `_web` and candidate paths before serving.
- Reject unless the resolved candidate is inside the resolved `web/` directory.
- Add tests for `../`, URL-encoded traversal, and Windows backslash traversal.

### 2. Destructive and operational endpoints are unauthenticated

Files: `src/eqmon/api.py`

Affected endpoints include `POST /events`, event edit/delete, ingest, PMD ingest, USGS refresh, and exports. Anyone with network access can mutate or delete catalog data and trigger expensive external/database work.

Todo:
- Add authentication and authorization before any exposed deployment.
- Separate public read routes from admin/operator routes.
- Add rate limits and audit logging for mutations and ingest.

### 3. Current intensity science is not operational-grade

Files: `src/eqmon/intensity.py`, `README.md`

The model uses a simplified attenuation equation, PGA-only Wald conversion, direct Vs30 multiplier, and hypocentral distance. It lacks tectonic-regime-specific GMPEs, PGV, finite-fault behavior, nonlinear site response, basin terms, and uncertainty.

Risk:
- Biased shaking estimates for Hindu Kush deep events, Makran/subduction events, large near-field ruptures, and soft-soil areas.
- Users may overinterpret modeled MMI contours as official products.

Todo:
- Add persistent UI/API disclaimers: modeled, preliminary, non-official.
- Rename or clarify products so they are not confused with USGS ShakeMap/PAGER.
- Add uncertainty/provenance output before using this operationally.

### 4. Ingest can silently miss upstream updates

Files: `src/eqmon/api.py`, `src/eqmon/events/ingest.py`, `src/eqmon/events/sources.py`

`_ingest_source()` advances sync timestamps after `ingest()` even when `IngestResult.errors` contains fetch or row failures. Upsert uses `ON CONFLICT DO NOTHING`, so revised USGS preliminary events do not update existing catalog rows.

Todo:
- Do not advance sync when fetch or DB errors occur.
- Track sync using max upstream `updated_at`, not local wall-clock time.
- Change upsert to `ON CONFLICT DO UPDATE` for mutable feed fields when upstream `updated_at` is newer.
- Persist ingest run status and errors.

### 5. Clean deployments are not reproducible from source

Files: `Dockerfile`, `.gitignore`, `.dockerignore`, `scripts/*`, `src/eqmon/config.py`

Runtime artifacts such as `data/Vs30.tif` and `web/tiles/*.pmtiles` are generated/ignored. A clean Docker/CI build can produce an image that starts but lacks required runtime data.

Todo:
- Define an artifact strategy for Vs30 and PMTiles: release assets, object storage, or reproducible data-build pipeline.
- Add startup readiness checks for required data files.
- Add checksums, CRS validation, file-size checks, and feature-count checks.

## P1 Findings

### Backend and Data

#### Global reclustering and declustering will not scale

Files: `src/eqmon/events/ingest.py`

Every ingest runs global spatial/time reclustering, O(n^2)-style declustering, and zone assignment across the catalog. The scheduler runs frequently, so catalog growth will turn this into a DB/CPU bottleneck.

Todo:
- Add a PostgreSQL advisory lock around ingest.
- Recluster only affected time/space windows.
- Assign tectonic zones only for new or changed rows.
- Move declustering into an offline/background analytics job.
- Add indexes for canonical event queries and geography distance joins.

#### Dedup clustering is not transitive

File: `src/eqmon/events/ingest.py`, `_recluster`

Cluster ID is assigned as the smallest event ID in each row's direct window. Chained duplicates can split into multiple clusters.

Todo:
- Implement connected-component clustering or DBSCAN-like space-time clustering.
- Include magnitude, depth, and quality similarity.
- Add tests for A-B-C duplicate chains.

#### Scheduler is unsafe in multi-worker deployments

File: `src/eqmon/api.py`

Each API process can start its own scheduler. Manual ingest can overlap scheduler ingest. `start_ingest_scheduler()` also assigns `_STOP_SCHEDULER = False` without declaring it global.

Todo:
- Move ingest to a separate worker/cron process.
- Or protect ingest with advisory locks and a single scheduler leader.
- Add env-based scheduler enable/disable and interval configuration.
- Fix and test scheduler stop/start semantics.

#### Migrations lack production safeguards

File: `src/eqmon/db.py`, `migrations/*.sql`

Migrations are run at app startup, lack advisory locking and checksums, and can be applied concurrently by multiple processes.

Todo:
- Use an advisory migration lock.
- Apply each migration in an explicit transaction.
- Store checksum, applied time, and duration.
- Run migrations as a deployment step, not implicitly in every API worker.

### Frontend and Full-Stack

#### Client async races can render stale data

File: `web/app.js`

Rapid filter changes, event switching, dashboard opens, and aftershock runs can let slower previous requests overwrite newer UI state.

Todo:
- Use `AbortController` per request type.
- Use request sequence tokens before committing state.
- Centralize fetch/error handling.

#### Catalog filters create excessive API load

File: `web/app.js`

Search/filter input triggers requests on every keystroke, and each refresh triggers several count requests.

Todo:
- Debounce text/date/number filters.
- Return source counts in the main catalog response or a single aggregate endpoint.
- Add request cancellation.

#### Several server strings are inserted with `innerHTML`

File: `web/app.js`

Some tooltips/options/expanded views interpolate source data without escaping, while other paths use `escapeHtml()` correctly.

Todo:
- Replace unsafe `innerHTML` construction with DOM APIs where practical.
- Escape every server or tile property string before interpolation.
- Add tests or a lint rule for unsafe HTML insertion patterns.

#### Static fallback hides missing assets

File: `src/eqmon/api.py`, `_serve_file`

Missing JS/CSS/PMTiles/images may return `index.html` with HTTP 200, making frontend and tile errors opaque.

Todo:
- Only fall back to `index.html` for HTML navigation requests.
- Return 404 for `/tiles/`, JS, CSS, images, PMTiles, and other asset paths.

### Seismology and Domain

#### Unknown PMD depth is silently converted to 0 km

File: `src/eqmon/events/sources.py`, `parse_pmd`

Unknown or dirty depth values becoming shallow events can massively overestimate shaking, especially for deep Hindu Kush earthquakes.

Todo:
- Preserve unknown depth as null or mark as uncertain.
- Do not compute operational intensity until reviewed depth is available, or use a clearly labeled conservative regional default.

#### PGA-to-MMI should not rely on PGA alone for serious use

File: `src/eqmon/intensity.py`, `pga_to_mmi`

PGA-only GMICE is a weak predictor of felt/damaging intensity at higher MMI. ShakeMap-style workflows commonly use PGA and PGV.

Todo:
- Add PGV prediction and a modern GMICE.
- Prefer official ShakeMap grids/contours when available.
- Label local model as fallback/scenario mode.

#### "Impact" currently means admin shaking intersection

File: `src/eqmon/impact.py`, frontend impact rendering

The product reports maximum intersecting MMI and representative-point MMI, not actual impact, exposure, damage, casualties, or loss.

Todo:
- Rename to "Admin shaking summary" or "Exposure proxy".
- Add area fraction and population fraction by MMI band.
- Report population exposed to MMI >= VI, VII, VIII when population grids are integrated.

#### Aftershock model excludes larger follow-on events

File: `src/eqmon/aftershock.py`, `_cap_target_mags`

The code states an aftershock cannot be larger than its mainshock. In operational seismology, a later larger event can occur and the original event may be reclassified as a foreshock.

Todo:
- Remove categorical language.
- Do not cap larger-event probabilities solely by current mainshock magnitude, or clearly label the forecast scope.
- Expose parameter provenance, calibration period, completeness threshold, and uncertainty.

### Testing, DevOps, and Observability

#### No CI/CD or enforced quality gates

Files: repository root, `pyproject.toml`

No `.github/` workflows exist. DB tests skip if `DATABASE_URL_TEST` is absent. There is no automated linting, type checking, coverage, Docker smoke test, artifact validation, or security scanning.

Todo:
- Add CI with pure tests, DB tests against PostGIS, Docker build smoke, and artifact checks.
- Add `ruff`, formatter check, coverage, and type checking.
- Fail DB CI if DB tests are unexpectedly skipped.

#### Observability is minimal

Files: `src/eqmon/api.py`, `src/eqmon/events/*`, scripts

There is no clear `/healthz`, `/readyz`, `/metrics`, structured ingest logging, DB pool visibility, or data freshness SLO.

Todo:
- Add `/healthz` and `/readyz`.
- Add Prometheus-style metrics for ingest, external source errors, request latency, DB pool use, and data freshness.
- Log source, fetched count, inserted/updated count, duration, error type, and sync watermark.

#### Performance-critical paths lack benchmarks

Files: `src/eqmon/vs30.py`, `src/eqmon/intensity.py`, `src/eqmon/contours.py`, `src/eqmon/impact.py`, `src/eqmon/events/ingest.py`

Full-grid MMI, contouring, impact joins, and ingest reclustering can allocate large arrays and perform expensive spatial work without concurrency limits or performance budgets.

Todo:
- Add benchmark scripts or `pytest-benchmark` for grid load, `/intensity`, contour generation, impact, and ingest at 1k/10k/100k events.
- Add API-side concurrency limits for grid-heavy routes.
- Cache recent event impact/intensity results.
- Reduce Vs30 memory footprint by avoiding full 2-D lon/lat arrays where feasible.

## P2 Findings

### API validation is incomplete

Files: `src/eqmon/api.py`, `src/eqmon/events/repo.py`

Some query parameters allow negative or huge limits/offsets, unknown export formats silently fall back, bbox validation is weak, and partial lat/lon updates can be ambiguous.

Todo:
- Use `Query(ge=..., le=...)` and enums.
- Cap list/export sizes.
- Validate bbox length, coordinate ranges, and min/max order.
- Reject partial geometry updates.

### Frontend accessibility needs work

Files: `web/index.html`, `web/styles.css`, `web/app.js`

Several controls use visual spans rather than real labels. Hidden delete buttons are invisible to keyboard focus. Full-screen/expanded views lack robust focus management and Escape handling.

Todo:
- Convert field labels to `<label for="...">`.
- Add `:focus-visible` behavior for hidden action buttons.
- Manage focus on expanded view open/close and support Escape.
- Add accessible chart summaries/tables.

### The frontend is becoming too large and stateful

File: `web/app.js`

The single JavaScript file mixes map, catalog, aftershock, dashboard, exports, overlays, theme, and accessibility behavior with shared global state.

Todo:
- Split into modules: `api.js`, `map.js`, `catalog.js`, `impact.js`, `aftershock.js`, `dashboard.js`, `ui.js`.
- Centralize API base path, JSON parsing, error handling, abort support, and constants.

### Docker is local-dev oriented

Files: `Dockerfile`, `docker-compose.yml`

The image runs as root, hardcodes local DB credentials, lacks a healthcheck, and copies generated data artifacts opportunistically.

Todo:
- Run as non-root.
- Add healthcheck.
- Externalize secrets and runtime artifacts.
- Separate local compose from production deployment manifests.

## Phased Todo Plan

### Phase 0: Safety, Scientific Honesty, and Deployment Blockers

- Fix static path traversal.
- Add UI/API disclaimer that outputs are modeled, preliminary, and non-official.
- Rename "Impact" to "Admin shaking summary" or "Exposure proxy".
- Add auth/roles for write, delete, ingest, refresh, and export endpoints.
- Stop silently converting unknown PMD depth to `0.0 km`.
- Fix ingest sync advancement and upstream update handling.
- Define and validate runtime artifacts: `Vs30.tif`, PMTiles, boundary data.
- Add `/healthz` and `/readyz`.

### Phase 1: Catalog Correctness and API Hardening

- Implement `ON CONFLICT DO UPDATE` for upstream event revisions.
- Add event quality/provenance fields: review status, magnitude type, depth quality, location uncertainty, source update time.
- Replace priority-only canonical selection with quality-weighted canonical selection.
- Implement connected-component dedup clustering.
- Add advisory locks for ingest and migrations.
- Validate query parameters with Pydantic/FastAPI constraints and enums.
- Add pagination/export caps and rate limits.

### Phase 2: Frontend Robustness, Security, and Accessibility

- Add debounced filters and request cancellation.
- Fix stale async rendering with request tokens.
- Escape all server/tile strings or use DOM construction.
- Return 404 for missing assets/tiles instead of SPA fallback.
- Add client-side validation for coordinates, magnitude, depth, dates, and min/max ranges.
- Convert visual field labels to real labels.
- Add focus management for overlays and accessible chart alternatives.

### Phase 3: Performance and Scale

- Add benchmarks for grid load, intensity, contouring, impact, and ingest at realistic catalog sizes.
- Add concurrency limits for full-grid compute routes.
- Cache event intensity/impact results by event ID/model version.
- Optimize `Grid` memory representation: prefer 1-D coordinate vectors/precomputed radians instead of full 2-D lon/lat arrays where possible.
- Replace global recluster/decluster work with incremental/background jobs.
- Add DB indexes for canonical time queries, source/magnitude filters, text search, and geography distance joins.

### Phase 4: Seismology Upgrade Path

- Add tectonic-regime-specific GMPE framework.
- Add PGV and modern GMICE support.
- Add uncertainty outputs: median, 16th/84th percentile, and model provenance.
- Add finite-fault or magnitude-dependent near-source saturation.
- Ingest official USGS ShakeMap products when available and label them separately from local model output.
- Validate against historical regional events, station observations, DYFI, and USGS ShakeMap.

### Phase 5: Operational Maturity

- Move scheduler out of the API process or implement a single distributed scheduler leader.
- Add CI with pure tests, PostGIS integration tests, lint, type check, coverage, Docker smoke, and security scan.
- Add data manifest with source URLs, licenses, checksums, CRS, expected counts, and output checksums.
- Add structured logs, metrics, dashboards, and runbooks.
- Add migration checksum tracking and dirty-state handling.
- Add deployment docs, backup/restore plan, and SLOs for data freshness and API latency.

## Suggested First Sprint

- Fix `_serve_file()` traversal and asset fallback behavior.
- Add admin auth middleware or API-key dependency for mutation/ingest routes.
- Add disclaimer and rename "Impact" UI text.
- Fix ingest sync advancement and upstream update upsert behavior.
- Add GitHub Actions or equivalent CI for `uv sync --group dev --frozen` and `uv run pytest -q`.
- Add a PostGIS CI job so DB-backed tests cannot silently disappear.
- Add request debouncing/cancellation in `web/app.js` for catalog filters.
