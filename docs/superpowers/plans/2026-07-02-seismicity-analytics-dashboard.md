# Seismicity Analytics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vanity Analytics view with a rigorous, sliceable seismicity/hazard analytics dashboard.

**Architecture:** Hybrid. Declustering (Gardner–Knopoff) and tectonic-zone membership are global/expensive, computed once per ingest and persisted as columns on `seismic_event`. Magnitude-of-completeness, MLE b-value, rates, spatial grid, and zone rollups are computed on-request in NumPy over the filtered set, served by a parameterized `GET /analytics`. The frontend is a filter-bar + drill-down dashboard on Chart.js + Leaflet.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostGIS, NumPy, fiona/shapely; vanilla JS, Chart.js, Leaflet.

## Global Constraints

- Test DB: integration tests use the `db_conn` fixture and are skipped without `DATABASE_URL_TEST`. Run tests with `.venv/Scripts/python.exe -m pytest` (bare `python` lacks deps).
- Migrations live in `migrations/*.sql`, applied in filename order by `apply_schema()`; adding `003_analytics.sql` is picked up automatically at startup and in tests. No manual apply step.
- Quality gate (single source of truth): every statistic excludes rows with `magnitude` outside `[-1, 10)`, or null `depth_km`/`geom`. Same bound `parse_met()` enforces.
- Magnitude: use each event's reported (preferred) `magnitude` as-is; apply no scale conversions. Surface the `mag_type` mixture as a caveat.
- Tunables live in `src/eqmon/config.py`: `GRID_CELL_DEG = 0.25`, `MC_MIN_N = 50`, `BVALUE_MIN_N = 50`, `DEPTH_CRUSTAL_MAX_KM = 35.0`, `DEPTH_INTERMEDIATE_MAX_KM = 70.0`, `MC_CORRECTION = 0.2`, `MAG_BIN_WIDTH = 0.1`.
- Tectonic-zone source shapefile: `data/PAK_Tectoniz_Zones/PAK_Tectonic_Zones.shp` (note the `Tectoniz` directory spelling, verbatim).
- Frontend must remove the placeholder copy: `#dash-title-main` "National Seismic Intelligence Platform" and `#dash-title-sub` "Plain-language earthquake overview for disaster management decisions".
- Existing reusable frontend helpers (do not reimplement): `mk(id, conf)` (creates a Chart, tracks it), `destroyCharts()`, `syncChartTheme()`, `animateCounter(el, target)`, `toast(msg, type)`, `spinnerHTML()`, palette `C_`. The dashboard container is `#dash-main`; the section toggles via the `data-section="dashboard"` rail button and `renderDashboard()` is called on open (`web/app.js:~1679`).

## File Structure

- `migrations/003_analytics.sql` *(new)* — `seismic_event` columns + `tectonic_zone` table.
- `src/eqmon/config.py` *(modify)* — analytics tunables.
- `src/eqmon/analytics.py` *(new)* — pure functions: `mc_maxc`, `b_value_aki`, `decluster_gardner_knopoff`, `spatial_grid`, `depth_regime_split`, `rate_series`, `parse_window`.
- `scripts/load_tectonic_zones.py` *(new)* — zone loader (mirrors `load_boundaries.py`).
- `src/eqmon/events/ingest.py` *(modify)* — `_decluster()`, `_assign_zones()` post-steps.
- `scripts/backfill_analytics.py` *(new)* — one-off backfill over existing catalog.
- `src/eqmon/events/repo.py` *(modify)* — `analytics_rows(...)` filtered fetch; retire `get_event_stats`.
- `src/eqmon/api.py` *(modify)* — `GET /analytics`, `GET /zones`; remove `GET /events/stats`.
- `web/index.html`, `web/app.js`, `web/styles.css` *(modify)* — filter bar, panels, map, drill-down, provenance.
- `tests/test_analytics.py` *(new)*, `tests/test_analytics_api.py` *(new)*, `tests/test_ingest.py` *(modify)*.

---

## Phase 1 — Data foundation

### Task 1: Schema migration (columns + tectonic_zone)

**Files:**
- Create: `migrations/003_analytics.sql`
- Test: `tests/test_analytics_schema.py`

**Interfaces:**
- Produces: columns `seismic_event.is_mainshock BOOLEAN`, `seismic_event.sequence_id BIGINT`, `seismic_event.zone_id BIGINT`; table `tectonic_zone(id BIGSERIAL PK, name TEXT, geom geometry(MultiPolygon,4326))`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics_schema.py
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def test_analytics_columns_and_zone_table_exist(db_conn):
    cols = {r[0] for r in db_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'seismic_event'"
    ).fetchall()}
    assert {"is_mainshock", "sequence_id", "zone_id"} <= cols

    zcols = {r[0] for r in db_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'tectonic_zone'"
    ).fetchall()}
    assert {"id", "name", "geom"} <= zcols
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_schema.py -v`
Expected: FAIL (columns/table missing).

- [ ] **Step 3: Write the migration**

```sql
-- migrations/003_analytics.sql
ALTER TABLE seismic_event ADD COLUMN IF NOT EXISTS is_mainshock BOOLEAN;
ALTER TABLE seismic_event ADD COLUMN IF NOT EXISTS sequence_id  BIGINT;
ALTER TABLE seismic_event ADD COLUMN IF NOT EXISTS zone_id      BIGINT;

CREATE TABLE IF NOT EXISTS tectonic_zone (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS tectonic_zone_geom_gix ON tectonic_zone USING GIST (geom);
CREATE INDEX IF NOT EXISTS seismic_event_zone_ix  ON seismic_event (zone_id);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_schema.py -v`
Expected: PASS (`apply_schema` in the fixture runs the new migration).

- [ ] **Step 5: Commit**

```bash
git add migrations/003_analytics.sql tests/test_analytics_schema.py
git commit -m "feat(db): analytics columns + tectonic_zone table"
```

---

### Task 2: Config tunables

**Files:**
- Modify: `src/eqmon/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: module constants `GRID_CELL_DEG`, `MC_MIN_N`, `BVALUE_MIN_N`, `DEPTH_CRUSTAL_MAX_KM`, `DEPTH_INTERMEDIATE_MAX_KM`, `MC_CORRECTION`, `MAG_BIN_WIDTH`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py — append
def test_analytics_tunables_present():
    from eqmon import config as c
    assert c.GRID_CELL_DEG == 0.25
    assert c.MC_MIN_N == 50 and c.BVALUE_MIN_N == 50
    assert c.DEPTH_CRUSTAL_MAX_KM == 35.0
    assert c.DEPTH_INTERMEDIATE_MAX_KM == 70.0
    assert c.MC_CORRECTION == 0.2 and c.MAG_BIN_WIDTH == 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_analytics_tunables_present -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Add the constants**

```python
# src/eqmon/config.py — append
# --- Seismicity analytics tunables ---
GRID_CELL_DEG = 0.25              # hotspot grid cell size (degrees)
MC_MIN_N = 50                     # min events to estimate Mc
BVALUE_MIN_N = 50                 # min events (>= Mc) to report a b-value
MC_CORRECTION = 0.2               # MAXC completeness correction
MAG_BIN_WIDTH = 0.1               # magnitude bin width
DEPTH_CRUSTAL_MAX_KM = 35.0       # crustal < 35 km
DEPTH_INTERMEDIATE_MAX_KM = 70.0  # intermediate 35-70 km; deep > 70 km
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_analytics_tunables_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/config.py tests/test_config.py
git commit -m "feat(config): seismicity analytics tunables"
```

---

### Task 3: Magnitude-of-completeness (MAXC)

**Files:**
- Create: `src/eqmon/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces: `mc_maxc(mags: Sequence[float]) -> float | None` — returns Mc (peak-bin magnitude + `MC_CORRECTION`, rounded to 0.1), or `None` if fewer than `MC_MIN_N` values.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics.py
import math
import numpy as np
from eqmon.analytics import mc_maxc


def test_mc_maxc_returns_peak_bin_plus_correction():
    # Peak of the non-cumulative FMD at magnitude 3.0 (>= MC_MIN_N samples).
    mags = ([3.0] * 200) + ([3.1] * 120) + ([2.9] * 80) + ([4.0] * 30) + ([5.0] * 10)
    assert mc_maxc(mags) == 3.2  # 3.0 peak + 0.2 correction


def test_mc_maxc_none_when_too_few():
    assert mc_maxc([3.0, 3.1, 3.2]) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -v`
Expected: FAIL (module/function missing).

- [ ] **Step 3: Write the module + function**

```python
# src/eqmon/analytics.py
"""Pure seismicity-analytics functions: magnitude-of-completeness, MLE b-value,
Gardner-Knopoff declustering, spatial grid, depth regimes, rate series, and
time-window parsing. No DB or HTTP dependencies so each is unit-testable."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from .config import (BVALUE_MIN_N, MAG_BIN_WIDTH, MC_CORRECTION, MC_MIN_N)


def mc_maxc(mags) -> float | None:
    """Maximum-Curvature magnitude of completeness: peak bin of the
    non-cumulative FMD plus MC_CORRECTION. None if fewer than MC_MIN_N values."""
    m = np.asarray(mags, dtype=float)
    if m.size < MC_MIN_N:
        return None
    lo = math.floor(m.min() / MAG_BIN_WIDTH) * MAG_BIN_WIDTH
    edges = np.arange(lo, m.max() + MAG_BIN_WIDTH, MAG_BIN_WIDTH)
    counts, _ = np.histogram(m, bins=edges)
    if counts.sum() == 0:
        return None
    peak_left = edges[int(np.argmax(counts))]
    peak_center = peak_left + MAG_BIN_WIDTH / 2.0
    return round(peak_center + MC_CORRECTION, 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/analytics.py tests/test_analytics.py
git commit -m "feat(analytics): Mc via maximum curvature"
```

---

### Task 4: MLE b-value (Aki–Utsu + Shi–Bolt)

**Files:**
- Modify: `src/eqmon/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces: `b_value_aki(mags, mc) -> tuple[float, float, int] | None` — `(b, sigma, n)` rounded to 3 dp, over events with `M >= mc`; `None` if `n < BVALUE_MIN_N` or degenerate.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics.py — append
from eqmon.analytics import b_value_aki


def test_b_value_recovers_known_slope():
    # Synthetic GR sample with true b = 1.0 above Mc = 3.0.
    rng = np.random.default_rng(42)
    mc = 3.0
    # exponential in (M - Mc) with rate b*ln(10) -> b=1.0
    draws = rng.exponential(scale=1.0 / (1.0 * math.log(10)), size=20000)
    mags = np.round((mc + draws) / 0.1) * 0.1
    b, sigma, n = b_value_aki(mags, mc)
    assert abs(b - 1.0) < 0.05
    assert sigma > 0 and n > 10000


def test_b_value_none_when_too_few():
    assert b_value_aki([3.0, 3.1, 3.2, 3.3], 3.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -k b_value -v`
Expected: FAIL (function missing).

- [ ] **Step 3: Implement**

```python
# src/eqmon/analytics.py — append
def b_value_aki(mags, mc) -> tuple[float, float, int] | None:
    """Aki-Utsu maximum-likelihood b-value with Shi & Bolt (1982) uncertainty,
    over events with M >= mc. None if fewer than BVALUE_MIN_N or degenerate."""
    m = np.asarray(mags, dtype=float)
    sample = m[m >= mc - MAG_BIN_WIDTH / 2.0 + 1e-9]
    n = int(sample.size)
    if n < BVALUE_MIN_N:
        return None
    mean_m = float(sample.mean())
    denom = mean_m - (mc - MAG_BIN_WIDTH / 2.0)
    if denom <= 0:
        return None
    b = math.log10(math.e) / denom
    var = float(((sample - mean_m) ** 2).sum()) / (n * (n - 1))
    sigma = 2.30 * b * b * math.sqrt(var)
    return (round(b, 3), round(sigma, 3), n)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -k b_value -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/analytics.py tests/test_analytics.py
git commit -m "feat(analytics): MLE b-value with Shi-Bolt uncertainty"
```

---

### Task 5: Gardner–Knopoff declustering

**Files:**
- Modify: `src/eqmon/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces: `decluster_gardner_knopoff(events) -> list[tuple[bool, int]]` — input is a list of dicts with keys `id:int`, `occurred_at:datetime` (tz-aware), `lat:float`, `lon:float`, `magnitude:float`; output is aligned per-event `(is_mainshock, sequence_id)` where `sequence_id` is the mainshock's `id`. Uses a symmetric time window `|Δt| <= T(M)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics.py — append
from datetime import datetime, timedelta, timezone
from eqmon.analytics import decluster_gardner_knopoff

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_decluster_groups_aftershock_and_separates_distant():
    events = [
        {"id": 1, "occurred_at": T0, "lat": 34.0, "lon": 72.0, "magnitude": 6.0},
        # 2 hours later, 10 km away -> inside M6 window -> aftershock of #1
        {"id": 2, "occurred_at": T0 + timedelta(hours=2), "lat": 34.05, "lon": 72.05, "magnitude": 4.0},
        # far away in space -> its own mainshock
        {"id": 3, "occurred_at": T0 + timedelta(hours=3), "lat": 40.0, "lon": 80.0, "magnitude": 5.0},
    ]
    flags = decluster_gardner_knopoff(events)
    assert flags[0] == (True, 1)
    assert flags[1] == (False, 1)
    assert flags[2] == (True, 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -k decluster -v`
Expected: FAIL (function missing).

- [ ] **Step 3: Implement**

```python
# src/eqmon/analytics.py — append
_EARTH_R_KM = 6371.0088


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_R_KM * math.asin(math.sqrt(a))


def _gk_windows(mag) -> tuple[float, float]:
    """Gardner & Knopoff (1974): interaction distance L (km) and time T (days)."""
    dist_km = 10 ** (0.1238 * mag + 0.983)
    if mag >= 6.5:
        time_days = 10 ** (0.032 * mag + 2.7389)
    else:
        time_days = 10 ** (0.5409 * mag - 0.547)
    return dist_km, time_days


def decluster_gardner_knopoff(events) -> list[tuple[bool, int]]:
    """Flag each event (is_mainshock, sequence_id). Largest-magnitude first;
    events inside a larger event's space-time window inherit its sequence.
    Symmetric time window captures foreshocks and aftershocks."""
    n = len(events)
    order = sorted(range(n), key=lambda i: (-events[i]["magnitude"], events[i]["occurred_at"]))
    assigned = [False] * n
    out: dict[int, tuple[bool, int]] = {}
    for i in order:
        if assigned[i]:
            continue
        assigned[i] = True
        main_id = events[i]["id"]
        out[i] = (True, main_id)
        dist_km, time_days = _gk_windows(events[i]["magnitude"])
        for j in range(n):
            if assigned[j] or j == i:
                continue
            dt = abs((events[j]["occurred_at"] - events[i]["occurred_at"]).total_seconds()) / 86400.0
            if dt > time_days:
                continue
            if _haversine_km(events[i]["lat"], events[i]["lon"],
                             events[j]["lat"], events[j]["lon"]) <= dist_km:
                assigned[j] = True
                out[j] = (False, main_id)
    return [out[i] for i in range(n)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -k decluster -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/analytics.py tests/test_analytics.py
git commit -m "feat(analytics): Gardner-Knopoff declustering"
```

---

### Task 6: Spatial grid, depth regimes, rate series, window parsing

**Files:**
- Modify: `src/eqmon/analytics.py`
- Test: `tests/test_analytics.py`

**Interfaces:**
- Produces:
  - `spatial_grid(rows) -> list[dict]` — rows are dicts with `lat,lon,magnitude,depth_km`; returns `[{lon_low, lat_low, count, max_mag, mean_depth}]` on `GRID_CELL_DEG` cells.
  - `depth_regime_split(rows) -> dict` — `{"crustal": n, "intermediate": n, "deep": n}`.
  - `rate_series(rows) -> list[dict]` — rows include `occurred_at, is_mainshock`; returns monthly `[{month:"YYYY-MM", total, background}]`.
  - `parse_window(window, anchor) -> tuple[datetime, datetime]` — maps `"30d"|"1y"|"5y"|"all"` to `(from_dt, to_dt)` anchored at `anchor` (catalog max time). Raises `ValueError` on bad input.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics.py — append
from eqmon.analytics import (spatial_grid, depth_regime_split, rate_series, parse_window)


def test_spatial_grid_bins_and_aggregates():
    rows = [
        {"lat": 34.1, "lon": 72.1, "magnitude": 4.0, "depth_km": 10.0},
        {"lat": 34.2, "lon": 72.2, "magnitude": 5.0, "depth_km": 20.0},  # same 0.25 cell
        {"lat": 40.0, "lon": 80.0, "magnitude": 3.0, "depth_km": 30.0},  # other cell
    ]
    cells = {(c["lon_low"], c["lat_low"]): c for c in spatial_grid(rows)}
    a = cells[(72.0, 34.0)]
    assert a["count"] == 2 and a["max_mag"] == 5.0 and a["mean_depth"] == 15.0
    assert (80.0, 40.0) in cells


def test_depth_regime_split_boundaries():
    rows = [{"depth_km": d} for d in [0, 34.9, 35.0, 70.0, 70.1, 200]]
    r = depth_regime_split(rows)
    assert r == {"crustal": 2, "intermediate": 2, "deep": 2}


def test_rate_series_total_vs_background():
    rows = [
        {"occurred_at": datetime(2026, 1, 5, tzinfo=timezone.utc), "is_mainshock": True},
        {"occurred_at": datetime(2026, 1, 20, tzinfo=timezone.utc), "is_mainshock": False},
        {"occurred_at": datetime(2026, 2, 3, tzinfo=timezone.utc), "is_mainshock": True},
    ]
    series = {s["month"]: s for s in rate_series(rows)}
    assert series["2026-01"]["total"] == 2 and series["2026-01"]["background"] == 1
    assert series["2026-02"]["total"] == 1 and series["2026-02"]["background"] == 1


def test_parse_window():
    anchor = datetime(2026, 7, 1, tzinfo=timezone.utc)
    f, t = parse_window("1y", anchor)
    assert t == anchor and f == anchor - timedelta(days=365)
    f2, _ = parse_window("all", anchor)
    assert f2.year <= 1970
    import pytest
    with pytest.raises(ValueError):
        parse_window("bogus", anchor)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -k "grid or depth or rate or window" -v`
Expected: FAIL (functions missing).

- [ ] **Step 3: Implement**

```python
# src/eqmon/analytics.py — append
from .config import (DEPTH_CRUSTAL_MAX_KM, DEPTH_INTERMEDIATE_MAX_KM, GRID_CELL_DEG)


def spatial_grid(rows) -> list[dict]:
    if not rows:
        return []
    agg: dict[tuple[float, float], dict] = {}
    for r in rows:
        lon_low = math.floor(r["lon"] / GRID_CELL_DEG) * GRID_CELL_DEG
        lat_low = math.floor(r["lat"] / GRID_CELL_DEG) * GRID_CELL_DEG
        key = (round(lon_low, 4), round(lat_low, 4))
        cell = agg.setdefault(key, {"lon_low": key[0], "lat_low": key[1],
                                    "count": 0, "max_mag": None, "_depth_sum": 0.0})
        cell["count"] += 1
        cell["_depth_sum"] += float(r["depth_km"])
        m = float(r["magnitude"])
        if cell["max_mag"] is None or m > cell["max_mag"]:
            cell["max_mag"] = m
    out = []
    for cell in agg.values():
        cell["mean_depth"] = round(cell.pop("_depth_sum") / cell["count"], 1)
        out.append(cell)
    return out


def depth_regime_split(rows) -> dict:
    res = {"crustal": 0, "intermediate": 0, "deep": 0}
    for r in rows:
        d = float(r["depth_km"])
        if d < DEPTH_CRUSTAL_MAX_KM:
            res["crustal"] += 1
        elif d <= DEPTH_INTERMEDIATE_MAX_KM:
            res["intermediate"] += 1
        else:
            res["deep"] += 1
    return res


def rate_series(rows) -> list[dict]:
    buckets: dict[str, dict] = {}
    for r in rows:
        month = r["occurred_at"].strftime("%Y-%m")
        b = buckets.setdefault(month, {"month": month, "total": 0, "background": 0})
        b["total"] += 1
        if r.get("is_mainshock"):
            b["background"] += 1
    return [buckets[k] for k in sorted(buckets)]


def parse_window(window: str, anchor: datetime) -> tuple[datetime, datetime]:
    if window == "all":
        return (datetime(1900, 1, 1, tzinfo=anchor.tzinfo), anchor)
    spans = {"30d": timedelta(days=30), "1y": timedelta(days=365),
             "5y": timedelta(days=365 * 5)}
    if window not in spans:
        raise ValueError(f"invalid window: {window!r}")
    return (anchor - spans[window], anchor)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics.py -v`
Expected: PASS (all analytics unit tests).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/analytics.py tests/test_analytics.py
git commit -m "feat(analytics): grid, depth regimes, rate series, window parsing"
```

---

### Task 7: Tectonic-zone loader

**Files:**
- Create: `scripts/load_tectonic_zones.py`

**Interfaces:**
- Consumes: `data/PAK_Tectoniz_Zones/PAK_Tectonic_Zones.shp`, `eqmon.db._database_url`, `apply_schema`.
- Produces: populated `tectonic_zone` rows.

- [ ] **Step 1: Inspect the shapefile's name attribute**

Run:
```bash
.venv/Scripts/python.exe -c "import fiona; s=fiona.open('data/PAK_Tectoniz_Zones/PAK_Tectonic_Zones.shp'); print(s.schema['properties']); print(len(s))"
```
Expected: prints the property fields and feature count. Note the field that holds the zone name (e.g. `ZONE`, `NAME`, `Zone_Name`). Use it as `NAME_FIELD` below. If several look plausible, pick the human-readable text field; if none exists, fall back to a synthesized `Zone {id}`.

- [ ] **Step 2: Write the loader**

```python
# scripts/load_tectonic_zones.py
"""Load Pakistan tectonic zones from a shapefile into the PostGIS tectonic_zone
table. Idempotent: skips if tectonic_zone already has rows (use --force to
reload). Mirrors scripts/load_boundaries.py."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — pins PROJ
import fiona  # noqa: E402
import psycopg  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from eqmon.db import _database_url, apply_schema  # noqa: E402

SHP = Path(__file__).resolve().parents[1] / "data" / "PAK_Tectoniz_Zones" / "PAK_Tectonic_Zones.shp"
NAME_FIELD = "ZONE"  # <-- set from Step 1 inspection
SIMPLIFY_DEG = 0.001

INSERT = (
    "INSERT INTO tectonic_zone (name, geom) VALUES (%s, "
    "ST_Multi(ST_SimplifyPreserveTopology("
    "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)))"
)


def main() -> None:
    p = argparse.ArgumentParser(description="Load tectonic zones into PostGIS")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    if not SHP.exists():
        raise SystemExit(f"Zone shapefile not found: {SHP}")
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        existing = conn.execute("SELECT count(*) FROM tectonic_zone").fetchone()[0]
        if existing and not args.force:
            print(f"tectonic_zone already has {existing} rows; skipping (use --force)")
            return
        conn.execute("TRUNCATE tectonic_zone RESTART IDENTITY CASCADE")
        count = 0
        with conn.cursor() as cur, fiona.open(SHP) as src:
            for i, feat in enumerate(src):
                props = dict(feat["properties"])
                name = str(props.get(NAME_FIELD) or f"Zone {i + 1}")
                geom = json.dumps(mapping(shape(feat["geometry"])))
                cur.execute(INSERT, (name, geom, SIMPLIFY_DEG))
                count += 1
        total = conn.execute("SELECT count(*) FROM tectonic_zone").fetchone()[0]
        print(f"loaded {count} zones; tectonic_zone total rows: {total}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the loader against the dev DB**

Run: `.venv/Scripts/python.exe scripts/load_tectonic_zones.py`
Expected: prints `loaded N zones; tectonic_zone total rows: N` (N > 0). Re-running prints the skip message.

- [ ] **Step 4: Commit**

```bash
git add scripts/load_tectonic_zones.py
git commit -m "feat(scripts): tectonic-zone PostGIS loader"
```

---

### Task 8: Ingest wiring — decluster + zone assignment

**Files:**
- Modify: `src/eqmon/events/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `decluster_gardner_knopoff` (Task 5); `tectonic_zone` (Task 1/7); existing `_recluster`, `ingest`.
- Produces: after `ingest()`, canonical events have `is_mainshock`, `sequence_id`, and `zone_id` set. New private funcs `_decluster(conn)`, `_assign_zones(conn)` called at the end of `ingest()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest.py — append (reuses _FakeSource, T0 already in file)
from datetime import timedelta


def test_ingest_sets_mainshock_and_sequence(db_conn):
    from eqmon.events.ingest import ingest
    main = _FakeSource([RawEvent("USGS", "m", T0, 6.0, 10, 72.0, 34.0)])
    after = _FakeSource([RawEvent("USGS", "a", T0 + timedelta(hours=2), 4.0, 10, 72.05, 34.05)])
    ingest(db_conn, main)
    ingest(db_conn, after)
    rows = db_conn.execute(
        "SELECT source_event_id, is_mainshock, sequence_id FROM seismic_event "
        "WHERE source='USGS' ORDER BY magnitude DESC"
    ).fetchall()
    # largest is a mainshock; the smaller one is its aftershock (shares sequence)
    assert rows[0][1] is True
    assert rows[1][1] is False
    assert rows[1][2] == rows[0][2]


def test_ingest_assigns_zone_id(db_conn):
    from eqmon.events.ingest import ingest
    db_conn.execute(
        "INSERT INTO tectonic_zone (name, geom) VALUES ('Z', "
        "ST_SetSRID(ST_GeomFromText('MULTIPOLYGON(((71 33,73 33,73 35,71 35,71 33)))'),4326))"
    )
    ingest(db_conn, _FakeSource([RawEvent("USGS", "z", T0, 5.0, 10, 72.0, 34.0)]))
    zone = db_conn.execute(
        "SELECT zone_id FROM seismic_event WHERE source_event_id='z'"
    ).fetchone()[0]
    assert zone is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ingest.py -k "mainshock or zone" -v`
Expected: FAIL (columns not populated).

- [ ] **Step 3: Implement the post-steps and call them from `ingest()`**

Add near the other helpers in `ingest.py`:

```python
# src/eqmon/events/ingest.py — add
from ..analytics import decluster_gardner_knopoff


def _decluster(conn) -> None:
    rows = conn.execute(
        "SELECT id, occurred_at, ST_Y(geom) AS lat, ST_X(geom) AS lon, magnitude "
        "FROM seismic_event WHERE is_canonical = TRUE "
        "AND magnitude >= -1 AND magnitude < 10"
    ).fetchall()
    events = [{"id": r[0], "occurred_at": r[1], "lat": r[2], "lon": r[3],
               "magnitude": r[4]} for r in rows]
    flags = decluster_gardner_knopoff(events)
    conn.execute("UPDATE seismic_event SET is_mainshock = NULL, sequence_id = NULL")
    for ev, (is_main, seq) in zip(events, flags):
        conn.execute(
            "UPDATE seismic_event SET is_mainshock = %s, sequence_id = %s WHERE id = %s",
            (is_main, seq, ev["id"]),
        )


def _assign_zones(conn) -> None:
    conn.execute(
        "UPDATE seismic_event e SET zone_id = z.id "
        "FROM tectonic_zone z WHERE ST_Contains(z.geom, e.geom)"
    )
```

Then, at the very end of `ingest()` (after the existing `_recluster(conn)` call), add:

```python
    _decluster(conn)
    _assign_zones(conn)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ingest.py -v`
Expected: PASS (new + existing ingest tests).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/events/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): decluster + tectonic-zone assignment post-steps"
```

---

### Task 9: One-off backfill script

**Files:**
- Create: `scripts/backfill_analytics.py`

**Interfaces:**
- Consumes: `_decluster`, `_assign_zones` (Task 8).
- Produces: populated analytics columns over the existing catalog.

- [ ] **Step 1: Write the script**

```python
# scripts/backfill_analytics.py
"""One-off: populate is_mainshock/sequence_id/zone_id over the existing catalog
(run once after deploying the analytics migration + tectonic-zone load)."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401
import psycopg  # noqa: E402

from eqmon.db import _database_url, apply_schema  # noqa: E402
from eqmon.events.ingest import _decluster, _assign_zones  # noqa: E402


def main() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        _decluster(conn)
        _assign_zones(conn)
        mains = conn.execute(
            "SELECT count(*) FROM seismic_event WHERE is_mainshock = TRUE"
        ).fetchone()[0]
        zoned = conn.execute(
            "SELECT count(*) FROM seismic_event WHERE zone_id IS NOT NULL"
        ).fetchone()[0]
        print(f"backfill done: {mains} mainshocks, {zoned} events zoned")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the backfill against the dev DB**

Run: `.venv/Scripts/python.exe scripts/backfill_analytics.py`
Expected: prints `backfill done: <N> mainshocks, <M> events zoned` (both > 0).

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_analytics.py
git commit -m "feat(scripts): one-off analytics backfill"
```

---

## Phase 2 — Analytics API

### Task 10: Filtered fetch in repo

**Files:**
- Modify: `src/eqmon/events/repo.py`
- Test: `tests/test_repo.py`

**Interfaces:**
- Produces: `analytics_rows(conn, from_dt, to_dt, min_mag, zone_id=None, bbox=None) -> list[dict]` — canonical, quality-gated rows with keys `id, occurred_at, lat, lon, magnitude, depth_km, mag_type, place, is_mainshock, zone_id`. `bbox` is `(minlon, minlat, maxlon, maxlat)` or None.
- Produces: `catalog_max_time(conn) -> datetime | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_repo.py — append (uses db_conn; insert via ingest or raw SQL)
import os
from datetime import datetime, timezone
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def _insert(conn, sid, mag, lon, lat, when):
    conn.execute(
        "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude, "
        "depth_km, geom, is_canonical, is_mainshock) VALUES "
        "('USGS', %s, %s, %s, 10, ST_SetSRID(ST_MakePoint(%s,%s),4326), TRUE, TRUE)",
        (sid, when, mag, lon, lat))


def test_analytics_rows_filters_mag_and_gate(db_conn):
    from eqmon.events.repo import analytics_rows
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _insert(db_conn, "a", 5.0, 72.0, 34.0, t)
    _insert(db_conn, "b", 2.0, 72.0, 34.0, t)   # below min_mag
    _insert(db_conn, "c", 317.0, 72.0, 34.0, t)  # quality-gated out
    rows = analytics_rows(db_conn, datetime(2025,1,1,tzinfo=timezone.utc),
                          datetime(2027,1,1,tzinfo=timezone.utc), min_mag=3.0)
    ids = {r["magnitude"] for r in rows}
    assert 5.0 in ids and 2.0 not in ids and 317.0 not in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py -k analytics_rows -v`
Expected: FAIL (function missing).

- [ ] **Step 3: Implement**

```python
# src/eqmon/events/repo.py — append
def catalog_max_time(conn):
    r = conn.execute("SELECT MAX(occurred_at) FROM seismic_event").fetchone()
    return r[0]


def analytics_rows(conn, from_dt, to_dt, min_mag, zone_id=None, bbox=None) -> list[dict]:
    clauses = ["is_canonical = TRUE", "magnitude >= -1", "magnitude < 10",
               "depth_km IS NOT NULL", "occurred_at BETWEEN %s AND %s",
               "magnitude >= %s"]
    params = [from_dt, to_dt, min_mag]
    if zone_id is not None:
        clauses.append("zone_id = %s")
        params.append(zone_id)
    if bbox is not None:
        clauses.append("geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)")
        params.extend(bbox)
    sql = ("SELECT id, occurred_at, ST_Y(geom) AS lat, ST_X(geom) AS lon, "
           "magnitude, depth_km, mag_type, place, is_mainshock, zone_id "
           "FROM seismic_event WHERE " + " AND ".join(clauses))
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_repo.py -k analytics_rows -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/events/repo.py tests/test_repo.py
git commit -m "feat(repo): quality-gated analytics_rows fetch"
```

---

### Task 11: `GET /analytics` composite endpoint

**Files:**
- Modify: `src/eqmon/api.py`
- Test: `tests/test_analytics_api.py`

**Interfaces:**
- Consumes: `analytics_rows`, `catalog_max_time` (Task 10); all `analytics.py` functions.
- Produces: `GET /analytics?window&min_mag&zone_id&bbox` returning JSON with keys `provenance, kpis, grid, zones, fmd, depth, rate`. `min_mag` accepts a number or the literal `mc`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics_api.py
import os
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def _seed(conn):
    # 120 events at M3.0-5.0 in one zone/time so Mc + b-value are computable.
    for i in range(120):
        mag = 3.0 + (i % 20) * 0.1
        conn.execute(
            "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude,"
            " depth_km, geom, is_canonical, is_mainshock) VALUES ('USGS', %s, %s, %s, 20,"
            " ST_SetSRID(ST_MakePoint(72,34),4326), TRUE, TRUE)",
            (f"e{i}", datetime(2026, 1, 1, tzinfo=timezone.utc), mag))


def test_analytics_endpoint_shape_and_filters(db_conn, monkeypatch):
    from eqmon import api, db
    _seed(db_conn)
    monkeypatch.setattr(db, "get_conn", lambda: _CtxConn(db_conn))
    client = TestClient(api.app)
    r = client.get("/analytics?window=all&min_mag=mc")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"provenance", "kpis", "grid", "fmd", "depth", "rate", "zones"}
    assert body["kpis"]["mc"] is not None
    # bad window -> 400
    assert client.get("/analytics?window=nope").status_code == 400


class _CtxConn:
    """Wrap the test transaction so `with db.get_conn() as c` yields it without closing."""
    def __init__(self, conn): self._c = conn
    def __enter__(self): return self._c
    def __exit__(self, *a): return False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_api.py -v`
Expected: FAIL (route missing → 404).

- [ ] **Step 3: Implement the endpoint**

```python
# src/eqmon/api.py — add near the other event routes
from fastapi import Query
from . import analytics as ana
from .events.repo import analytics_rows, catalog_max_time


@app.get("/analytics")
def analytics(window: str = "1y", min_mag: str = "mc",
              zone_id: int | None = None, bbox: str | None = None):
    with db.get_conn() as conn:
        anchor = catalog_max_time(conn)
        if anchor is None:
            raise HTTPException(status_code=404, detail="empty catalog")
        try:
            from_dt, to_dt = ana.parse_window(window, anchor)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        box = None
        if bbox:
            try:
                box = tuple(float(x) for x in bbox.split(","))
                assert len(box) == 4
            except Exception:
                raise HTTPException(status_code=400, detail="bad bbox")

        # First pass with a floor of 0 to estimate Mc; then honour min_mag.
        rows = analytics_rows(conn, from_dt, to_dt, min_mag=-1, zone_id=zone_id, bbox=box)
        mags = [r["magnitude"] for r in rows]
        mc = ana.mc_maxc(mags)
        if min_mag == "mc":
            floor = mc if mc is not None else -1.0
        else:
            try:
                floor = float(min_mag)
            except ValueError:
                raise HTTPException(status_code=400, detail="bad min_mag")
        used = [r for r in rows if r["magnitude"] >= floor]

        b = ana.b_value_aki([r["magnitude"] for r in used], mc) if mc is not None else None
        n_years = max((to_dt - from_dt).days / 365.25, 1e-9)
        mains = [r for r in used if r["is_mainshock"]]
        largest = max(used, key=lambda r: r["magnitude"], default=None)
        seqs = {r["sequence_id"] for r in used if not r["is_mainshock"] and r.get("sequence_id")}
        magtypes: dict[str, int] = {}
        for r in used:
            magtypes[r.get("mag_type") or "unknown"] = magtypes.get(r.get("mag_type") or "unknown", 0) + 1

        # Per-zone rollup (only when not already drilled into one zone).
        zone_rows = []
        if zone_id is None:
            zmap: dict[int, list] = {}
            for r in used:
                if r.get("zone_id"):
                    zmap.setdefault(r["zone_id"], []).append(r)
            znames = dict(conn.execute("SELECT id, name FROM tectonic_zone").fetchall())
            for zid, zr in zmap.items():
                zmags = [x["magnitude"] for x in zr]
                zmc = ana.mc_maxc(zmags)
                zb = ana.b_value_aki(zmags, zmc) if zmc is not None else None
                depths = sorted(x["depth_km"] for x in zr)
                zone_rows.append({
                    "zone_id": zid, "name": znames.get(zid, f"Zone {zid}"),
                    "n": len(zr), "b": zb[0] if zb else None, "sigma": zb[1] if zb else None,
                    "mc": zmc, "median_depth": depths[len(depths) // 2],
                    "max_mag": max(zmags),
                    "pct_aftershocks": round(1 - sum(1 for x in zr if x["is_mainshock"]) / len(zr), 2),
                })
            zone_rows.sort(key=lambda z: z["n"], reverse=True)

        return {
            "provenance": {
                "from": from_dt.isoformat(), "to": to_dt.isoformat(),
                "n_used": len(used), "n_excluded": len(rows) - len(used),
                "mag_types": magtypes,
            },
            "kpis": {
                "b": b[0] if b else None, "b_sigma": b[1] if b else None,
                "b_n": b[2] if b else None, "mc": mc,
                "background_rate": round(len(mains) / n_years, 1),
                "total_rate": round(len(used) / n_years, 1),
                "pct_aftershocks": round(1 - (len(mains) / len(used)), 2) if used else None,
                "active_sequences": len(seqs),
                "largest": None if largest is None else {
                    "magnitude": largest["magnitude"], "place": largest.get("place"),
                    "occurred_at": largest["occurred_at"].isoformat()},
            },
            "grid": ana.spatial_grid(used),
            "zones": zone_rows,
            "fmd": _fmd_payload(used, mc),
            "depth": {"regimes": ana.depth_regime_split(used),
                      "scatter": [{"mag": r["magnitude"], "depth": r["depth_km"]}
                                  for r in used[:1000]]},
            "rate": ana.rate_series(used),
        }


def _fmd_payload(rows, mc):
    """Cumulative + incremental FMD for the Gutenberg-Richter plot."""
    import numpy as np
    from .config import MAG_BIN_WIDTH
    if not rows:
        return {"bins": [], "incremental": [], "cumulative": [], "mc": mc}
    mags = np.asarray([r["magnitude"] for r in rows], dtype=float)
    lo = np.floor(mags.min() / MAG_BIN_WIDTH) * MAG_BIN_WIDTH
    edges = np.arange(lo, mags.max() + MAG_BIN_WIDTH, MAG_BIN_WIDTH)
    inc, _ = np.histogram(mags, bins=edges)
    cum = inc[::-1].cumsum()[::-1]
    centers = [round(float(e + MAG_BIN_WIDTH / 2), 2) for e in edges[:-1]]
    return {"bins": centers, "incremental": inc.tolist(),
            "cumulative": cum.tolist(), "mc": mc}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/api.py tests/test_analytics_api.py
git commit -m "feat(api): GET /analytics composite endpoint"
```

---

### Task 12: `GET /zones` + retire `/events/stats`

**Files:**
- Modify: `src/eqmon/api.py`, `src/eqmon/events/repo.py`
- Test: `tests/test_analytics_api.py`

**Interfaces:**
- Produces: `GET /zones` → GeoJSON `FeatureCollection` of tectonic zones (`properties.zone_id`, `properties.name`). Removes `GET /events/stats` and `get_event_stats`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_analytics_api.py — append
def test_zones_geojson_and_stats_gone(db_conn, monkeypatch):
    from eqmon import api, db
    db_conn.execute(
        "INSERT INTO tectonic_zone (name, geom) VALUES ('Z1', "
        "ST_SetSRID(ST_GeomFromText('MULTIPOLYGON(((71 33,73 33,73 35,71 35,71 33)))'),4326))")
    monkeypatch.setattr(db, "get_conn", lambda: _CtxConn(db_conn))
    client = TestClient(api.app)
    r = client.get("/zones")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["features"]
    assert fc["features"][0]["properties"]["name"] == "Z1"
    # retired
    assert client.get("/events/stats").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_api.py -k zones -v`
Expected: FAIL (`/zones` 404; `/events/stats` still 200).

- [ ] **Step 3: Implement `/zones`, delete `/events/stats`**

Add to `api.py`:

```python
@app.get("/zones")
def zones():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, ST_AsGeoJSON(geom) FROM tectonic_zone"
        ).fetchall()
    import json
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"zone_id": r[0], "name": r[1]},
         "geometry": json.loads(r[2])} for r in rows]}
```

Delete the `@app.get("/events/stats")` route and its `event_stats` function from `api.py`, and remove `get_event_stats` from `repo.py` (and its import in `api.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_analytics_api.py -v`
Expected: PASS. Then run the whole suite to confirm nothing referenced the removed function:
Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all pass (delete `tests/test_stats.py` if it targeted `get_event_stats`; the quality gate now covers that regression).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/api.py src/eqmon/events/repo.py tests/
git commit -m "feat(api): GET /zones; retire /events/stats"
```

---

## Phase 3 — Frontend core

### Task 13: Dashboard shell — identity, filter bar, state, fetch

**Files:**
- Modify: `web/index.html`, `web/app.js`, `web/styles.css`

**Interfaces:**
- Consumes: `GET /analytics`.
- Produces: `_analyticsState = {window, minMag, zoneId, bbox}`; `renderDashboard()` rewritten to read state, fetch `/analytics`, and call `renderAnalytics(data)` (panel functions added in later tasks). A filter bar in `#dash-main`.

- [ ] **Step 1: Replace the placeholder hero in `index.html`**

Change `web/index.html:22-25` to:

```html
      <h2 id="dash-title">
        <span id="dash-title-main">Seismicity Analytics</span>
        <span id="dash-title-sub" class="dash-provenance">—</span>
      </h2>
```

- [ ] **Step 2: Add state + filter bar + fetch in `app.js`**

Replace the body of `renderDashboard()` (currently `web/app.js:~1313`) with:

```javascript
const _analyticsState = { window: "1y", minMag: "mc", zoneId: null, bbox: null };

function _analyticsQuery() {
  const p = new URLSearchParams({ window: _analyticsState.window, min_mag: _analyticsState.minMag });
  if (_analyticsState.zoneId != null) p.set("zone_id", _analyticsState.zoneId);
  if (_analyticsState.bbox) p.set("bbox", _analyticsState.bbox.join(","));
  return p.toString();
}

async function renderDashboard() {
  const main = document.getElementById("dash-main");
  main.innerHTML = `<div style="padding:48px;text-align:center;color:var(--text-muted)">${spinnerHTML()} Loading analytics…</div>`;
  let resp;
  try { resp = await fetch("/analytics?" + _analyticsQuery()); }
  catch (e) { main.innerHTML = `<div style="padding:20px;color:var(--text-muted)">Network error: ${e.message}</div>`; return; }
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    main.innerHTML = `<div style="padding:20px;color:var(--text-muted)">Failed to load analytics (HTTP ${resp.status}: ${t.slice(0,160)})</div>`;
    return;
  }
  const data = await resp.json();
  destroyCharts();
  syncChartTheme();
  main.innerHTML = _dashScaffoldHTML();
  _wireFilterBar();
  renderProvenance(data.provenance);   // Task 18
  renderKpis(data.kpis);               // Task 14
  renderFmd(data.fmd);                 // Task 15
  renderDepth(data.depth);             // Task 16
  renderRate(data.rate);               // Task 16
  renderHotspotMap(data.grid);         // Task 17
  renderZoneTable(data.zones);         // Task 17
}

function _dashScaffoldHTML() {
  return `
  <div class="dash-filterbar">
    <label>Time <select id="f-window">
      <option value="30d">30 days</option><option value="1y" selected>1 year</option>
      <option value="5y">5 years</option><option value="all">All</option></select></label>
    <label>Min mag <select id="f-minmag">
      <option value="mc" selected>≥ Mc</option><option value="2">2.0</option>
      <option value="3">3.0</option><option value="4">4.0</option><option value="5">5.0</option></select></label>
    <span id="f-breadcrumb" class="dash-breadcrumb"></span>
    <button id="f-reset" class="btn-secondary" style="width:auto;margin:0">⟲ Reset</button>
  </div>
  <div id="dash-kpis" class="dash-stat-grid"></div>
  <div class="dash-row"><div class="dash-card" style="flex:1.4"><div id="hotspot-map" style="height:340px"></div></div>
    <div class="dash-card" style="flex:1"><div id="zone-table"></div></div></div>
  <div class="dash-row"><div class="dash-card" style="flex:1.3"><canvas id="ch-fmd"></canvas></div>
    <div class="dash-card" style="flex:1"><canvas id="ch-depth"></canvas></div></div>
  <div class="dash-row"><div class="dash-card"><canvas id="ch-rate"></canvas></div></div>
  <div class="dash-foot" id="dash-provenance-foot"></div>`;
}

function _wireFilterBar() {
  const win = document.getElementById("f-window");
  const mm = document.getElementById("f-minmag");
  win.value = _analyticsState.window; mm.value = _analyticsState.minMag;
  win.addEventListener("change", () => { _analyticsState.window = win.value; renderDashboard(); });
  mm.addEventListener("change", () => { _analyticsState.minMag = mm.value; renderDashboard(); });
  document.getElementById("f-reset").addEventListener("click", () => {
    _analyticsState.zoneId = null; _analyticsState.bbox = null; renderDashboard();
  });
  const bc = document.getElementById("f-breadcrumb");
  bc.textContent = _analyticsState.zoneId != null ? "▸ zone focus"
    : _analyticsState.bbox ? "▸ cell focus" : "";
}
```

- [ ] **Step 3: Add filter-bar styles in `styles.css`**

```css
/* Analytics dashboard */
.dash-filterbar { display:flex; align-items:center; gap:14px; margin-bottom:12px;
  flex-wrap:wrap; font-size:var(--fs-sm); color:var(--text-muted); }
.dash-filterbar select { padding:4px 6px; border:1px solid var(--border);
  background:var(--surface-2); color:var(--text); border-radius:var(--r-sm); }
.dash-breadcrumb { color:var(--brand); font-weight:600; }
.dash-provenance { font-size:var(--fs-sm); font-weight:400; color:var(--text-muted); }
```

- [ ] **Step 4: Add temporary panel stubs so the page renders**

At the top of the dashboard section in `app.js`, add no-op stubs (replaced in later tasks) so Step 2 references resolve:

```javascript
function renderProvenance(){} function renderKpis(){} function renderFmd(){}
function renderDepth(){} function renderRate(){} function renderHotspotMap(){}
function renderZoneTable(){}
```

- [ ] **Step 5: Manual verify + commit**

Start the server (`$env:PYTHONPATH="src"; .venv/Scripts/python.exe -m uvicorn eqmon.api:app --port 8020`), open Analytics: the filter bar renders, changing filters re-fetches without error (panels empty for now).

```bash
git add web/index.html web/app.js web/styles.css
git commit -m "feat(web): analytics dashboard shell + filter bar + state"
```

---

### Task 14: KPI strip

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `data.kpis`.
- Produces: `renderKpis(kpis)` filling `#dash-kpis`.

- [ ] **Step 1: Implement `renderKpis` (replace the stub)**

```javascript
function renderKpis(k) {
  const grid = document.getElementById("dash-kpis");
  const box = (val, lbl) => `<div class="dash-stat-box"><div class="dash-stat-val">${val}</div><div class="dash-stat-lbl">${lbl}</div></div>`;
  const b = k.b != null ? `${k.b}±${k.b_sigma}` : "—";
  const largest = k.largest ? `M${k.largest.magnitude.toFixed(1)}` : "—";
  grid.innerHTML =
    box(b, k.b_n != null ? `b-value (N ${k.b_n})` : "b-value") +
    box(k.mc ?? "—", "Completeness Mc") +
    box(k.background_rate ?? "—", "Background rate /yr") +
    box(k.pct_aftershocks != null ? Math.round(k.pct_aftershocks * 100) + "%" : "—", "Aftershocks") +
    box(largest, "Largest event") +
    box(k.active_sequences ?? 0, "Active sequences");
}
```

- [ ] **Step 2: Manual verify**

Reload Analytics: six KPI boxes show real values; `b-value` shows `—` when a filter yields too few events (low-N suppression).

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): analytics KPI strip"
```

---

### Task 15: Gutenberg–Richter panel (Mc + cumulative/incremental)

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `data.fmd` (`{bins, incremental, cumulative, mc}`).
- Produces: `renderFmd(fmd)` drawing `#ch-fmd` via `mk()`.

- [ ] **Step 1: Implement `renderFmd`**

```javascript
function renderFmd(f) {
  if (!f.bins.length) return;
  mk("ch-fmd", {
    type: "bar",
    data: { labels: f.bins.map(m => m.toFixed(1)), datasets: [
      { label: "Cumulative (≥ M)", data: f.cumulative, type: "line", borderColor: C_.orange,
        backgroundColor: "rgba(201,122,36,0.08)", fill: true, tension: 0, pointRadius: 0, order: 1 },
      { label: "Incremental", data: f.incremental, backgroundColor: "rgba(15,76,129,0.35)",
        borderColor: C_.blue, borderWidth: 1, order: 2, borderRadius: 2 },
    ]},
    options: {
      plugins: {
        legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
        title: { display: true, text: `Gutenberg–Richter${f.mc != null ? " · Mc " + f.mc : ""}`, font: { size: 12, weight: "600" } },
      },
      scales: { y: { type: "logarithmic", title: { display: true, text: "Count", font: { size: 10 } } },
                x: { title: { display: true, text: "Magnitude", font: { size: 10 } }, ticks: { font: { size: 9 }, maxTicksLimit: 20 } } },
    },
  });
}
```

Note: Mc is annotated in the chart title (no extra Chart.js annotation plugin needed — none is bundled). The log-y axis makes the G-R slope readable.

- [ ] **Step 2: Manual verify**

Reload Analytics: the G-R chart shows a log-y cumulative curve + incremental bars, titled with Mc. Switching `Min mag` to `4.0` reshapes it.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): Gutenberg-Richter panel with Mc"
```

---

### Task 16: Depth-regime and rate panels

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `data.depth` (`{regimes, scatter}`), `data.rate` (`[{month,total,background}]`).
- Produces: `renderDepth(depth)` → `#ch-depth`; `renderRate(rate)` → `#ch-rate`.

- [ ] **Step 1: Implement both**

```javascript
function renderDepth(d) {
  const r = d.regimes;
  mk("ch-depth", {
    type: "bar",
    data: { labels: ["Crustal <35", "Intermediate 35–70", "Deep >70"],
      datasets: [{ label: "Events", data: [r.crustal, r.intermediate, r.deep],
        backgroundColor: [C_.teal, C_.blue, C_.purple], borderRadius: 3 }] },
    options: { plugins: { legend: { display: false },
      title: { display: true, text: "Depth regime (km)", font: { size: 12, weight: "600" } } },
      scales: { x: { ticks: { font: { size: 9 } } }, y: { title: { display: true, text: "Events", font: { size: 10 } } } } },
  });
}

function renderRate(series) {
  mk("ch-rate", {
    type: "line",
    data: { labels: series.map(s => s.month), datasets: [
      { label: "Total", data: series.map(s => s.total), borderColor: C_.gray,
        backgroundColor: "rgba(148,163,184,0.15)", fill: true, tension: .2, pointRadius: 0 },
      { label: "Background (declustered)", data: series.map(s => s.background),
        borderColor: C_.blue, backgroundColor: "rgba(15,76,129,0.10)", fill: true, tension: .2, pointRadius: 0 },
    ]},
    options: { plugins: { legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
      title: { display: true, text: "Monthly seismicity rate — total vs background", font: { size: 12, weight: "600" } } },
      scales: { x: { ticks: { font: { size: 8 }, maxTicksLimit: 12 } },
        y: { title: { display: true, text: "Events / month", font: { size: 10 } } } } },
  });
}
```

- [ ] **Step 2: Manual verify**

Reload Analytics: depth-regime bars and the total-vs-background rate line render; the background series sits at/below total (aftershocks removed).

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): depth-regime and rate panels"
```

---

## Phase 4 — Spatial + drill-down

### Task 17: Hotspot map + zone table + drill-down

**Files:**
- Modify: `web/app.js`, `web/styles.css`

**Interfaces:**
- Consumes: `data.grid` (`[{lon_low,lat_low,count,max_mag,mean_depth}]`), `data.zones`, `GET /zones`.
- Produces: `renderHotspotMap(grid)` and `renderZoneTable(zones)`; clicks set `_analyticsState.bbox` / `.zoneId` and call `renderDashboard()`.

- [ ] **Step 1: Implement the hotspot map (own Leaflet instance)**

```javascript
let _hotspotMap = null, _zonesLayer = null;

async function renderHotspotMap(grid) {
  const host = document.getElementById("hotspot-map");
  if (!host) return;
  if (_hotspotMap) { _hotspotMap.remove(); _hotspotMap = null; }
  _hotspotMap = L.map(host, { attributionControl: false }).setView([30.4, 69.3], 4);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png").addTo(_hotspotMap);

  const cell = 0.25;
  const max = grid.reduce((m, c) => Math.max(m, c.count), 1);
  grid.forEach(c => {
    const t = c.count / max;
    L.rectangle([[c.lat_low, c.lon_low], [c.lat_low + cell, c.lon_low + cell]], {
      stroke: false, fillColor: "#C97A24", fillOpacity: 0.15 + 0.6 * t,
    }).addTo(_hotspotMap)
      .bindPopup(`${c.count} events · max M${c.max_mag} · mean depth ${c.mean_depth} km`)
      .on("click", () => {
        _analyticsState.bbox = [c.lon_low, c.lat_low, c.lon_low + cell, c.lat_low + cell];
        _analyticsState.zoneId = null; renderDashboard();
      });
  });

  // tectonic-zone overlay (click → drill into zone)
  try {
    const fc = await (await fetch("/zones")).json();
    _zonesLayer = L.geoJSON(fc, {
      style: { color: "#0F4C81", weight: 1, fill: false },
      onEachFeature: (feat, lyr) => lyr.on("click", () => {
        _analyticsState.zoneId = feat.properties.zone_id;
        _analyticsState.bbox = null; renderDashboard();
      }),
    }).addTo(_hotspotMap);
  } catch (e) { /* zones optional */ }
}
```

- [ ] **Step 2: Implement the zone table**

```javascript
function renderZoneTable(zones) {
  const host = document.getElementById("zone-table");
  if (!host) return;
  if (!zones || !zones.length) { host.innerHTML = `<div style="color:var(--text-muted);padding:8px">No zone data in this view.</div>`; return; }
  const rows = zones.map(z => `<tr data-zone="${z.zone_id}">
    <td>${z.name}</td><td align=right>${z.n}</td>
    <td align=right>${z.b != null ? z.b + "±" + z.sigma : "—"}</td>
    <td align=right>${z.mc ?? "—"}</td><td align=right>${z.median_depth}</td>
    <td align=right>M${z.max_mag.toFixed(1)}</td><td align=right>${Math.round(z.pct_aftershocks*100)}%</td></tr>`).join("");
  host.innerHTML = `<table class="zone-table"><thead><tr>
    <th align=left>Zone</th><th>N</th><th>b±σ</th><th>Mc</th><th>med.z</th><th>maxM</th><th>aft%</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  host.querySelectorAll("tr[data-zone]").forEach(tr => tr.addEventListener("click", () => {
    _analyticsState.zoneId = parseInt(tr.dataset.zone); _analyticsState.bbox = null; renderDashboard();
  }));
}
```

- [ ] **Step 3: Zone-table styles**

```css
.zone-table { width:100%; border-collapse:collapse; font-size:var(--fs-xs); }
.zone-table th, .zone-table td { padding:4px 6px; border-bottom:1px solid var(--border); }
.zone-table tbody tr { cursor:pointer; }
.zone-table tbody tr:hover { background: var(--brand-tint); }
```

- [ ] **Step 4: Manual verify (drill-down)**

Reload Analytics: hotspot rectangles shade by density; zones overlay draws. Click a zone (map or table row) → breadcrumb shows "zone focus" and every panel refocuses; click a cell → "cell focus"; Reset clears. Verify the map instance is recreated cleanly on each `renderDashboard` (no leaked Leaflet containers — Step 1 removes the prior map).

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "feat(web): hotspot map, zone table, drill-down"
```

---

## Phase 5 — Polish

### Task 18: Provenance line, caveats, empty/low-N states, cleanup

**Files:**
- Modify: `web/app.js`, `web/styles.css`

**Interfaces:**
- Consumes: `data.provenance` (`{from, to, n_used, n_excluded, mag_types}`).
- Produces: `renderProvenance(p)` filling `#dash-title-sub` and `#dash-provenance-foot`.

- [ ] **Step 1: Implement `renderProvenance`**

```javascript
function renderProvenance(p) {
  const sub = document.getElementById("dash-title-sub");
  const span = `${p.from.slice(0,10)} → ${p.to.slice(0,10)}`;
  if (sub) sub.textContent = `USGS + PMD · ${span} · ${p.n_used.toLocaleString()} events used`;
  const foot = document.getElementById("dash-provenance-foot");
  if (foot) {
    const types = Object.entries(p.mag_types).map(([k,v]) => `${k}:${v}`).join(" · ");
    foot.textContent = `${p.n_excluded} out-of-range/incomplete excluded · magnitude types — ${types} `
      + `(reported magnitudes, no scale conversion) · declustered (Gardner–Knopoff)`;
  }
}
```

- [ ] **Step 2: Empty-state guard**

In `renderDashboard()`, after parsing `data`, add before rendering panels:

```javascript
  if (data.provenance.n_used === 0) {
    main.innerHTML = _dashScaffoldHTML(); _wireFilterBar();
    renderProvenance(data.provenance);
    document.getElementById("dash-kpis").innerHTML =
      `<div style="padding:20px;color:var(--text-muted)">No events match this filter. Widen the time window or lower the minimum magnitude.</div>`;
    return;
  }
```

- [ ] **Step 3: Verify placeholder copy is gone**

Grep the repo for the retired strings; expect no matches in `web/`:
Run: `grep -rn "Plain-language earthquake overview\|National Seismic Intelligence Platform" web/`
Expected: no results.

- [ ] **Step 4: Full manual verification (both themes)**

Start the server; in dark and light: open Analytics; confirm provenance line + footer read correctly, KPIs/G-R/depth/rate render, hotspot map + zones + drill-down work, empty state appears for `30d`+`M5` if sparse, and low-N suppresses b-value/Mc. Screenshot dark + light for the PR.

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "feat(web): provenance line, caveats, empty/low-N states"
```

---

## Self-Review Notes

- **Spec coverage:** quality gate (Task 8/10 gate), Mc (T3), MLE b-value (T4), declustering (T5+T8), rates/background (T6+T11+T16), spatial grid (T6+T11+T17), tectonic zones (T1/T7/T11/T12/T17), depth regimes (T6+T11+T16), filters + drill-down (T13+T17), provenance + mag-type caveat (T18), retire `/events/stats` (T12), remove placeholder copy (T13+T18). All spec sections mapped.
- **Backfill** (T9) covers the existing catalog; **ingest wiring** (T8) covers future ingests.
- **Types:** `analytics_rows` dict keys used by `/analytics` (T11) match Task 10's Produces; frontend panel functions match the `/analytics` payload keys defined in T11.
- **Assumption to confirm during T7:** the tectonic-zone shapefile's name attribute (`NAME_FIELD`) — Step 1 of Task 7 inspects it before coding.
