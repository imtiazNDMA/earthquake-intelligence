# Source Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a USGS / Pakistan MET (PMD) / Manual source filter to the Analytics Dashboard, and unify source-filter semantics across the Dashboard and the existing Catalog list so a single-source view shows that agency's full catalogue.

**Architecture:** The `seismic_event.source` column is `'USGS' | 'MET' | 'MANUAL'`. Both the catalog query (`_build_where`) and the analytics query (`analytics_rows`) currently hard-code `is_canonical = TRUE` to dedupe the same quake reported by multiple agencies. That gate only matters when mixing sources, so when a single source is selected we apply `source = %s` and drop the canonical gate. The frontend adds a Dashboard source `<select>` that plumbs a `source` query param through to `GET /analytics`.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostGIS; vanilla-JS Leaflet + Chart.js frontend (no build step); pytest.

## Global Constraints

- Run pytest with the project venv: `.venv/Scripts/python.exe -m pytest` (bare `python` lacks psycopg/deps).
- DB-backed tests are skipped unless `DATABASE_URL_TEST` is set — it must be exported to actually run Tasks 1–3's tests.
- Valid source values are exactly `USGS`, `MET`, `MANUAL`. Any other value (including empty string) means "all sources" (`source=None`).
- UI label for `MET` is **"Pakistan MET (PMD)"** — use this exact wording in both the Catalog and Dashboard dropdowns.
- The magnitude/depth quality gate in `analytics_rows` (`magnitude >= -1`, `magnitude < 10`, `depth_km IS NOT NULL`) is always kept, regardless of source.

---

### Task 1: Conditional canonical gate in `_build_where` (Catalog list + count)

**Files:**
- Modify: `src/eqmon/events/repo.py:99-118`
- Test: `tests/test_repo.py`

**Interfaces:**
- Produces: `_build_where(...)` — unchanged signature; behavior change only. When `source is not None` the returned clauses contain `source = %s` and **omit** `is_canonical = TRUE`; when `source is None` they contain `is_canonical = TRUE` and no source clause. Consumed unchanged by `list_events` and `count_events`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_repo.py` (the module already imports `datetime`, `timezone`, `pytest`, and has the `db_conn` fixture and the module-level skipif):

```python
def _insert_src(conn, source, sid, mag, when, canonical):
    conn.execute(
        "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude,"
        " depth_km, geom, is_canonical, is_mainshock) VALUES "
        "(%s, %s, %s, %s, 10, ST_SetSRID(ST_MakePoint(72,34),4326), %s, TRUE)",
        (source, sid, when, mag, canonical))


def test_count_events_single_source_includes_non_canonical(db_conn):
    from eqmon.events.repo import count_events
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # A shared quake: MET canonical, USGS non-canonical (deduped away).
    _insert_src(db_conn, "MET", "m1", 5.0, t, True)
    _insert_src(db_conn, "USGS", "u1", 5.0, t, False)
    # All-sources counts only canonical rows (the MET one).
    assert count_events(db_conn) == 1
    # USGS-only counts the non-canonical USGS row (full agency catalogue).
    assert count_events(db_conn, source="USGS") == 1
    # MET-only counts the MET row.
    assert count_events(db_conn, source="MET") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py::test_count_events_single_source_includes_non_canonical -v`
Expected: FAIL — `count_events(db_conn, source="USGS")` returns `0` (the non-canonical USGS row is excluded by the current unconditional `is_canonical = TRUE`).

- [ ] **Step 3: Write minimal implementation**

Replace the body of `_build_where` in `src/eqmon/events/repo.py` (lines 99-118) with:

```python
def _build_where(since=None, min_magnitude=None, max_magnitude=None,
                 source=None, search=None,
                 occurred_after=None, occurred_before=None):
    clauses: list = []
    params: list = []
    # Cross-source dedup only matters when mixing sources. Pinning to a single
    # source shows that agency's full catalogue, including quakes deduped away
    # as non-canonical under another source's canonical row.
    if source is not None:
        clauses.append("source = %s"); params.append(source)
    else:
        clauses.append("is_canonical = TRUE")
    if since is not None:
        clauses.append("occurred_at >= %s"); params.append(since)
    if min_magnitude is not None:
        clauses.append("magnitude >= %s"); params.append(min_magnitude)
    if max_magnitude is not None:
        clauses.append("magnitude <= %s"); params.append(max_magnitude)
    if search is not None:
        clauses.append("place ILIKE %s"); params.append(f"%{search}%")
    if occurred_after is not None:
        clauses.append("occurred_at >= %s"); params.append(occurred_after)
    if occurred_before is not None:
        clauses.append("occurred_at <= %s"); params.append(occurred_before)
    return clauses, params
```

(`list_events` and `count_events` always wrap this in `" WHERE " + " AND ".join(clauses)`, and there is always at least one clause, so the WHERE is never empty.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py -v`
Expected: PASS — the new test passes and the existing `test_repo.py` tests still pass (all-sources paths unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/events/repo.py tests/test_repo.py
git commit -m "feat(repo): single-source catalog queries show full agency catalogue"
```

---

### Task 2: `source` parameter on `analytics_rows`

**Files:**
- Modify: `src/eqmon/events/repo.py:173-198`
- Test: `tests/test_repo.py`

**Interfaces:**
- Consumes: `_insert_src(conn, source, sid, mag, when, canonical)` helper from Task 1.
- Produces: `analytics_rows(conn, from_dt, to_dt, min_mag, zone_id=None, bbox=None, source=None) -> list[dict]`. New trailing keyword `source`. When set: adds `source = %s` and drops `is_canonical = TRUE`; the quality/magnitude/time gates are unchanged. When `None`: identical to today (canonical-gated).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_repo.py`:

```python
def test_analytics_rows_source_drops_canonical_gate(db_conn):
    from eqmon.events.repo import analytics_rows
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    win_lo = datetime(2025, 1, 1, tzinfo=timezone.utc)
    win_hi = datetime(2027, 1, 1, tzinfo=timezone.utc)
    # Shared quake: MET canonical, USGS non-canonical.
    _insert_src(db_conn, "MET", "m1", 5.0, t, True)
    _insert_src(db_conn, "USGS", "u1", 5.0, t, False)

    # source=None: canonical only -> just the MET row.
    all_rows = analytics_rows(db_conn, win_lo, win_hi, min_mag=3.0)
    assert len(all_rows) == 1

    # source="USGS": the non-canonical USGS row is included; MET excluded.
    usgs = analytics_rows(db_conn, win_lo, win_hi, min_mag=3.0, source="USGS")
    assert len(usgs) == 1

    # source="MET": the MET row, excludes USGS.
    met = analytics_rows(db_conn, win_lo, win_hi, min_mag=3.0, source="MET")
    assert len(met) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py::test_analytics_rows_source_drops_canonical_gate -v`
Expected: FAIL — `analytics_rows(..., source="USGS")` raises `TypeError: analytics_rows() got an unexpected keyword argument 'source'`.

- [ ] **Step 3: Write minimal implementation**

Replace `analytics_rows` in `src/eqmon/events/repo.py` (lines 173-198) with:

```python
def analytics_rows(conn: psycopg.Connection, from_dt, to_dt, min_mag,
                   zone_id=None, bbox=None, source=None) -> list[dict]:
    """Quality-gated rows for analytics.

    The gate (-1 <= magnitude < 10, depth present) excludes dirty catalog
    rows such as PMD mag/depth swaps. `bbox` is (minlon, minlat, maxlon,
    maxlat) or None. With `source` set (USGS/MET/MANUAL) the rows are that
    single source's full catalogue (the cross-source canonical gate is
    dropped, since dedup only matters when mixing sources); with `source`
    None only canonical rows are returned.
    """
    clauses = ["magnitude >= -1", "magnitude < 10",
               "depth_km IS NOT NULL", "occurred_at BETWEEN %s AND %s",
               "magnitude >= %s"]
    params = [from_dt, to_dt, min_mag]
    if source is not None:
        clauses.append("source = %s")
        params.append(source)
    else:
        clauses.append("is_canonical = TRUE")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py -v`
Expected: PASS — new test passes; existing `test_analytics_rows_filters_mag_and_gate` still passes (source=None path unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/events/repo.py tests/test_repo.py
git commit -m "feat(repo): analytics_rows source filter with full-catalogue semantics"
```

---

### Task 3: `source` query param on `GET /analytics`

**Files:**
- Modify: `src/eqmon/api.py:378-400`
- Test: `tests/test_analytics_api.py`

**Interfaces:**
- Consumes: `analytics_rows(..., source=...)` from Task 2.
- Produces: `GET /analytics` accepts `source: str | None = None`. Invalid/empty values are coerced to `None`. The validated value is passed to `analytics_rows`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_analytics_api.py` (module already has `_CtxConn`, `_seed`, `db_conn`, `monkeypatch`, and the skipif). Seed the 120 USGS rows via `_seed`, then add 30 MET rows so both single-source branches exercise real (non-empty) data and the counts are distinguishable:

```python
def test_analytics_source_filter(db_conn, monkeypatch):
    from eqmon import api, db
    _seed(db_conn)  # 120 USGS rows
    for i in range(30):
        db_conn.execute(
            "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude,"
            " depth_km, geom, is_canonical, is_mainshock) VALUES ('MET', %s, %s, %s, 20,"
            " ST_SetSRID(ST_MakePoint(72,34),4326), TRUE, TRUE)",
            (f"met{i}", datetime(2026, 1, 1, tzinfo=timezone.utc), 3.0 + (i % 20) * 0.1))
    monkeypatch.setattr(db, "get_conn", lambda: _CtxConn(db_conn))
    client = TestClient(api.app)

    usgs = client.get("/analytics?window=all&min_mag=2&source=USGS")
    met = client.get("/analytics?window=all&min_mag=2&source=MET")
    both = client.get("/analytics?window=all&min_mag=2&source=bogus")  # invalid -> all
    assert usgs.status_code == met.status_code == both.status_code == 200
    n_usgs = usgs.json()["provenance"]["n_used"]
    n_met = met.json()["provenance"]["n_used"]
    n_both = both.json()["provenance"]["n_used"]
    # Single-source counts isolate each agency; the seeded rows are all
    # canonical here, so all-sources ~= their sum.
    assert n_usgs > n_met > 0
    assert n_both >= n_usgs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_api.py::test_analytics_source_filter -v`
Expected: FAIL — `source` currently has no effect, so `n_usgs`, `n_met`, and `n_both` all equal the full 150-row count, and `n_usgs > n_met` is false.

- [ ] **Step 3: Write minimal implementation**

In `src/eqmon/api.py`, change the `analytics` signature (line 378-380) to add `source` and validate it, then pass it to the `analytics_rows` call (line 399-400):

```python
@app.get("/analytics")
def analytics(window: str = "1y", min_mag: str = "mc",
              zone_id: int | None = None, bbox: str | None = None,
              source: str | None = None):
    src = source if source in ("USGS", "MET", "MANUAL") else None
    with db.get_conn() as conn:
        anchor = catalog_max_time(conn)
        if anchor is None:
            raise HTTPException(status_code=404, detail="empty catalog")
```

Then update the `analytics_rows` call (currently lines 399-400) to pass `source=src`:

```python
        rows = analytics_rows(conn, from_dt, to_dt, min_mag=-1,
                              zone_id=zone_id, bbox=box, source=src)
```

(Leave the rest of the function unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_api.py -v`
Expected: PASS — new test passes; existing `test_analytics_endpoint_shape_and_filters` still passes.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/api.py tests/test_analytics_api.py
git commit -m "feat(api): source query param on GET /analytics"
```

---

### Task 4: Dashboard source select + dynamic provenance label + Catalog label parity

**Files:**
- Modify: `web/app.js:1297` (`_analyticsState`), `web/app.js:1299-1304` (`_analyticsQuery`), `web/app.js:1306-1316` (`renderProvenance`), `web/app.js:1465-1484` (`_dashScaffoldHTML`), `web/app.js:1486-1498` (`_wireFilterBar`)
- Modify: `web/index.html:75` (Catalog dropdown label parity)
- Test: manual browser verification (the frontend has no JS test harness)

**Interfaces:**
- Consumes: `GET /analytics?source=...` from Task 3.
- Produces: `_analyticsState.source` (string; `""` = all). The Dashboard sends `source` only when non-empty; `renderProvenance` labels the header from `_analyticsState.source`.

- [ ] **Step 1: Add `source` to dashboard state**

In `web/app.js`, change line 1297 from:

```javascript
const _analyticsState = { window: "1y", minMag: "mc", zoneId: null, bbox: null };
```

to:

```javascript
const _analyticsState = { window: "1y", minMag: "mc", zoneId: null, bbox: null, source: "" };
```

- [ ] **Step 2: Send `source` in the analytics query**

In `web/app.js`, change `_analyticsQuery` (lines 1299-1304) to add the source param when set:

```javascript
function _analyticsQuery() {
  const p = new URLSearchParams({ window: _analyticsState.window, min_mag: _analyticsState.minMag });
  if (_analyticsState.zoneId != null) p.set("zone_id", _analyticsState.zoneId);
  if (_analyticsState.bbox) p.set("bbox", _analyticsState.bbox.join(","));
  if (_analyticsState.source) p.set("source", _analyticsState.source);
  return p.toString();
}
```

- [ ] **Step 3: Dynamic provenance label**

In `web/app.js`, replace `renderProvenance` (lines 1306-1316) so the header reflects the active source. Add a label map and use it for the `sub` text:

```javascript
const SOURCE_LABELS = { "": "USGS + PMD", USGS: "USGS only", MET: "Pakistan MET (PMD) only", MANUAL: "Manual only" };

function renderProvenance(p) {
  const sub = document.getElementById("dash-title-sub");
  const span = `${p.from.slice(0, 10)} → ${p.to.slice(0, 10)}`;
  const srcLabel = SOURCE_LABELS[_analyticsState.source] || "USGS + PMD";
  if (sub) sub.textContent = `${srcLabel} · ${span} · ${p.n_used.toLocaleString()} events used`;
  const foot = document.getElementById("dash-provenance-foot");
  if (foot) {
    const types = Object.entries(p.mag_types).map(([k, v]) => `${k}:${v}`).join(" · ");
    foot.textContent = `${p.n_excluded.toLocaleString()} events below the magnitude floor excluded · magnitude types — ${types} `
      + `(reported magnitudes, no scale conversion) · declustered (Gardner–Knopoff)`;
  }
}
```

- [ ] **Step 4: Add the source `<select>` to the filter bar**

In `web/app.js`, in `_dashScaffoldHTML` (lines 1465-1484), insert a Source label immediately after the Min mag `</label>` (which ends the min-mag select) and before `<span id="f-breadcrumb" ...>`:

```javascript
    <label>Min mag <select id="f-minmag">
      <option value="mc" selected>≥ Mc</option><option value="2">2.0</option>
      <option value="3">3.0</option><option value="4">4.0</option><option value="5">5.0</option></select></label>
    <label>Source <select id="f-source">
      <option value="" selected>All</option>
      <option value="USGS">USGS</option>
      <option value="MET">Pakistan MET (PMD)</option>
      <option value="MANUAL">Manual</option></select></label>
    <span id="f-breadcrumb" class="dash-breadcrumb"></span>
```

- [ ] **Step 5: Wire the source select**

In `web/app.js`, in `_wireFilterBar` (lines 1486-1498), after the `mm` (min-mag) wiring lines and before the `f-reset` handler, add:

```javascript
  const src = document.getElementById("f-source");
  src.value = _analyticsState.source;
  src.addEventListener("change", () => { _analyticsState.source = src.value; renderDashboard(); });
```

- [ ] **Step 6: Catalog label parity**

In `web/index.html`, change the Catalog dropdown option (line 75) from:

```html
            <option value="MET">Pakistan MET</option>
```

to:

```html
            <option value="MET">Pakistan MET (PMD)</option>
```

- [ ] **Step 7: Manual browser verification**

Start the app (see `start.bat` / project run instructions) and open the Dashboard section:
1. Confirm a **Source** dropdown appears in the filter bar (All / USGS / Pakistan MET (PMD) / Manual).
2. Select **USGS** — the panels re-render, the header subtitle reads `USGS only · … · N events used`, and N matches a USGS-only slice.
3. Select **Pakistan MET (PMD)** — header reads `Pakistan MET (PMD) only · …`, panels reflect MET-only data.
4. Select **All** — header returns to `USGS + PMD · …`.
5. Open the Catalog section — confirm its Source dropdown now reads "Pakistan MET (PMD)" and still filters the list.

- [ ] **Step 8: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web): dashboard source filter and dynamic provenance label"
```

---

## Notes for the implementer

- Tasks 1–3 are independent DB/API changes each with their own test; Task 4 (frontend) depends on Task 3's endpoint param being live.
- If `DATABASE_URL_TEST` is not set, the pytest steps will report the DB tests as *skipped* rather than passed — set it before running so the assertions actually execute.
- Do not add `source` to the dashboard Reset button: Reset clears only the drill-down (zone/cell focus), matching how window/min-mag persist across a reset.
