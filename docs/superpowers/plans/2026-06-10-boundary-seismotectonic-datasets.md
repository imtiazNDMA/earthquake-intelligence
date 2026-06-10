# Boundary & Seismotectonic Datasets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Pakistan admin boundaries (national/province/district/tehsil) and seismotectonic reference layers (faults, plate boundaries, plates) to the platform as toggleable map overlays plus multi-level per-event MMI impact rollups.

**Architecture:** Two planes from one source of truth. A *geometry plane* in PostGIS (`admin_boundary` table, geometry simplified to ~100 m on load) backs the impact spatial joins. A *display plane* of `.pmtiles` vector tiles (built once by tippecanoe-in-Docker, served as static files) backs the map overlays. Faults/plates are display-only. The frontend stays Leaflet and adds `protomaps-leaflet` to render the tiles.

**Tech Stack:** Python 3.12, FastAPI, PostGIS (psycopg 3), fiona/shapely, NumPy, tippecanoe (Docker), Leaflet + protomaps-leaflet.

**Spec:** `docs/superpowers/specs/2026-06-10-boundary-seismotectonic-datasets-design.md`

**Confirmed source facts (via fiona):**
- `pak_national.shp` — Polygon, n=4, name field `Admin01_Na`
- `pak_provinces.shp` — Polygon, n=8, name field `Province`
- `pak_districts.shp` — Polygon, n=167, fields `Districts`/`province`/`division`/`Population`
- `pak_tehsils.shp` — Polygon, n=578, fields `name`/`district`/`province`/`division`
- faults — LineString, n=16121; plate boundaries — **3D** LineString, n=241; plates — Polygon, n=18
- All EPSG:4326.

---

## File Structure

- Create `src/eqmon/boundaries.py` — pure field-mapping (shapefile props → `admin_boundary` columns). No I/O.
- Create `scripts/load_boundaries.py` — load the four admin shapefiles into PostGIS, simplified.
- Create `scripts/build_tiles.py` — build seven `.pmtiles` via tippecanoe-in-Docker.
- Create `tests/test_boundaries.py` — pure mapping tests.
- Modify `schema.sql` — replace `district` table with `admin_boundary`.
- Modify `src/eqmon/impact.py` — generalise to `admin_boundary` + level rollups.
- Modify `tests/test_impact.py`, `tests/test_db.py`, `tests/test_events_api.py` — track schema/shape changes.
- Modify `web/index.html`, `web/app.js` — overlays, layer control, rollups consumption.
- Modify `.gitignore`, `README.md`.
- Delete `scripts/load_districts.py`, `boundary/district.geojson`.

---

## Task 1: Field-mapping module (pure, no DB)

**Files:**
- Create: `src/eqmon/boundaries.py`
- Test: `tests/test_boundaries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_boundaries.py
import pytest
from eqmon.boundaries import map_feature


def test_district_maps_all_columns():
    props = {"Districts": "Bagh", "province": "Azad Kashmir",
             "division": "Poonch Division", "Population": "530861.6", "country": "Pakistan"}
    row = map_feature("district", props)
    assert row == {"level": "district", "name": "Bagh", "parent": "Azad Kashmir",
                   "division": "Poonch Division", "population": 530861.6}


def test_tehsil_has_no_population():
    props = {"name": "Bagh", "district": "Bagh", "province": "Azad Kashmir",
             "division": "Poonch Division", "country": "Pakistan"}
    row = map_feature("tehsil", props)
    assert row["level"] == "tehsil"
    assert row["name"] == "Bagh"
    assert row["parent"] == "Bagh"          # parent of a tehsil is its district
    assert row["division"] == "Poonch Division"
    assert row["population"] is None


def test_national_minimal():
    row = map_feature("national", {"Admin01_Na": "Pakistan"})
    assert row == {"level": "national", "name": "Pakistan",
                   "parent": None, "division": None, "population": None}


def test_unknown_level_raises():
    with pytest.raises(ValueError, match="unknown level"):
        map_feature("galaxy", {"name": "x"})


def test_missing_name_raises():
    with pytest.raises(ValueError, match="missing name"):
        map_feature("province", {"OBJECTID": "1"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_boundaries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eqmon.boundaries'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/eqmon/boundaries.py
"""Pure field-mapping from each boundary shapefile's properties to
admin_boundary columns. No I/O — unit-testable in isolation.

Field names are the shapefile DBF column names confirmed via fiona; the DBF
format truncates names to 10 chars, which is why e.g. the national name column
is ``Admin01_Na``."""
from __future__ import annotations

# level -> {column: source DBF field name (or None if absent for this level)}
_LEVEL_FIELDS: dict[str, dict[str, str | None]] = {
    "national": {"name": "Admin01_Na", "parent": None,       "division": None,       "population": None},
    "province": {"name": "Province",   "parent": None,       "division": None,       "population": None},
    "district": {"name": "Districts",  "parent": "province", "division": "division", "population": "Population"},
    "tehsil":   {"name": "name",       "parent": "district", "division": "division", "population": None},
}


def map_feature(level: str, props: dict) -> dict:
    """Map one shapefile feature's properties to admin_boundary column values."""
    if level not in _LEVEL_FIELDS:
        raise ValueError(f"unknown level: {level!r}")
    fields = _LEVEL_FIELDS[level]

    def src(col: str):
        field = fields[col]
        return props.get(field) if field is not None else None

    name = src("name")
    if name in (None, ""):
        raise ValueError(f"feature missing name field {fields['name']!r} for level {level!r}")
    population = src("population")
    parent = src("parent")
    division = src("division")
    return {
        "level": level,
        "name": str(name),
        "parent": str(parent) if parent is not None else None,
        "division": str(division) if division is not None else None,
        "population": float(population) if population not in (None, "") else None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_boundaries.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/boundaries.py tests/test_boundaries.py
git commit -m "feat: pure admin-boundary field mapping (national/province/district/tehsil)"
```

---

## Task 2: Schema + impact generalisation (kept green together)

The `admin_boundary` table and its consumers (`impact.py`, three tests) change as one commit so the suite stays green.

**Files:**
- Modify: `schema.sql:22-28` (the `district` block)
- Modify: `src/eqmon/impact.py` (whole file)
- Modify: `tests/test_impact.py:35-52`
- Modify: `tests/test_db.py:16,19`
- Modify: `tests/test_events_api.py:19,23`

- [ ] **Step 1: Replace the district table in `schema.sql`**

Replace lines 22-28 (the `CREATE TABLE ... district ...` block and its index) with:

```sql
CREATE TABLE IF NOT EXISTS admin_boundary (
    id         BIGSERIAL PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN ('national','province','district','tehsil')),
    name       TEXT NOT NULL,
    parent     TEXT,
    division   TEXT,
    population DOUBLE PRECISION,
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS admin_boundary_geom_gix ON admin_boundary USING GIST (geom);
CREATE INDEX IF NOT EXISTS admin_boundary_level_ix ON admin_boundary (level);
```

- [ ] **Step 2: Update the failing DB tests first (write the new expectations)**

In `tests/test_db.py`, change the table-set assertion (lines 16 and 19):

```python
        "WHERE table_schema='public' AND table_name IN ('seismic_event','admin_boundary')"
    ).fetchall()}
    assert names == {"seismic_event", "admin_boundary"}
```

In `tests/test_events_api.py`, change both `TRUNCATE` statements (lines 19 and 23):

```python
        conn.execute("TRUNCATE seismic_event, admin_boundary RESTART IDENTITY")
```

Replace the DB test in `tests/test_impact.py` (lines 28-52) with:

```python
@pytest_db
def test_compute_event_impact_reports_rollups_per_level(db_conn):
    from eqmon.vs30 import load_grid
    from eqmon.config import VS30_TIF
    from eqmon.events.repo import create_manual_event
    from eqmon.impact import compute_event_impact

    # one district + its enclosing province, both over the epicenter
    for level, name in [("province", "TestProv"), ("district", "Epi")]:
        db_conn.execute(
            "INSERT INTO admin_boundary (level, name, parent, geom) VALUES "
            "(%s, %s, 'TestProv', ST_Multi(ST_SetSRID("
            "ST_MakeEnvelope(72.0, 33.5, 73.0, 34.5), 4326)))",
            (level, name),
        )
    grid = load_grid(VS30_TIF)
    ev = create_manual_event(db_conn, magnitude=6.5, depth_km=10, lon=72.5, lat=34.0)
    impact = compute_event_impact(db_conn, ev, grid)

    assert impact["bands"]["type"] == "FeatureCollection"
    assert set(impact["rollups"]) == {"province", "district", "tehsil"}
    assert impact["rollups"]["tehsil"] == []          # none loaded
    epi = next(d for d in impact["rollups"]["district"] if d["name"] == "Epi")
    assert epi["parent"] == "TestProv"
    # worst-case band >= floored precise reading at the representative point
    assert epi["mmi_max"] >= int(epi["mmi_repr"])
    assert epi["mmi_repr"] >= 1.0
    assert isinstance(epi["mmi_repr"], float)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_impact.py tests/test_db.py -v`
Expected: FAIL — `test_compute_event_impact_*` errors with `KeyError: 'rollups'` (impact.py still returns `districts`); `test_schema_creates_tables` fails on the table set.
(If `DATABASE_URL_TEST` is unset the DB tests skip — then this step's "fail" is a clean skip; proceed.)

- [ ] **Step 4: Rewrite `src/eqmon/impact.py`**

Replace the whole file with:

```python
"""Per-event admin-boundary impact. Reuses the Plan A engine for the MMI
surface, then for each admin level:
- max-band-intersecting MMI per unit via a PostGIS spatial join;
- representative-point MMI per unit by sampling the MMI grid at each unit's
  point-on-surface."""
from __future__ import annotations
import json

import numpy as np
import psycopg
from psycopg.rows import dict_row

from .config import MMI_BAND_LEVELS
from .contours import mmi_to_geojson
from .intensity import compute_mmi_grid
from .vs30 import Grid

# Levels rolled up per event (national is overlay-only, not aggregated).
ROLLUP_LEVELS = ("province", "district", "tehsil")


def sample_grid_at(grid_array: np.ndarray, transform, lons: np.ndarray,
                   lats: np.ndarray) -> np.ndarray:
    """Value of the raster cell that contains each geographic point.

    Points outside the raster extent are clipped to the edge cell."""
    inv = ~transform
    cols, rows = inv * (np.asarray(lons), np.asarray(lats))
    cols = np.clip(np.floor(cols).astype(int), 0, grid_array.shape[1] - 1)
    rows = np.clip(np.floor(rows).astype(int), 0, grid_array.shape[0] - 1)
    return grid_array[rows, cols]


def _rollup_for_level(conn: psycopg.Connection, level: str,
                      mmi: np.ndarray, grid: Grid) -> list[dict]:
    """Max-band + representative MMI for every admin unit at `level`.

    Assumes a temp `_bands` table (mmi int, geom) with a GIST index already
    exists in this transaction."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.id, a.name, a.parent,
                   ST_X(ST_PointOnSurface(a.geom)) AS rlon,
                   ST_Y(ST_PointOnSurface(a.geom)) AS rlat,
                   COALESCE(MAX(b.mmi), 0) AS mmi_max
            FROM admin_boundary a
            LEFT JOIN _bands b ON ST_Intersects(a.geom, b.geom)
            WHERE a.level = %s
            GROUP BY a.id, a.name, a.parent, a.geom
            ORDER BY mmi_max DESC, a.name
            """,
            (level,),
        )
        rows = cur.fetchall()

    rlons = np.array([r["rlon"] for r in rows], dtype="float64")
    rlats = np.array([r["rlat"] for r in rows], dtype="float64")
    repr_mmi = (sample_grid_at(mmi, grid.transform, rlons, rlats)
                if rows else np.array([]))
    return [
        {"id": r["id"], "name": r["name"], "parent": r["parent"],
         "mmi_max": int(r["mmi_max"]), "mmi_repr": round(float(rm), 1)}
        for r, rm in zip(rows, repr_mmi)
    ]


def compute_event_impact(conn: psycopg.Connection, event: dict, grid: Grid) -> dict:
    mmi = compute_mmi_grid(
        grid.lon, grid.lat, grid.vs30,
        mag=event["magnitude"], depth_km=event["depth_km"],
        epi_lon=event["lon"], epi_lat=event["lat"],
    )
    bands = mmi_to_geojson(mmi, grid.transform, levels=MMI_BAND_LEVELS)

    # Build the band surface once; reused across every level's spatial join.
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

    rollups = {lvl: _rollup_for_level(conn, lvl, mmi, grid) for lvl in ROLLUP_LEVELS}
    return {"bands": bands, "rollups": rollups}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_impact.py tests/test_db.py tests/test_events_api.py -v`
Expected: PASS (DB tests pass with `DATABASE_URL_TEST` set, otherwise skip cleanly).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `uv run pytest -q`
Expected: all pass/skip; no failures.

- [ ] **Step 7: Commit**

```bash
git add schema.sql src/eqmon/impact.py tests/test_impact.py tests/test_db.py tests/test_events_api.py
git commit -m "feat: admin_boundary table + multi-level impact rollups (replaces district)"
```

---

## Task 3: Boundary loader script

**Files:**
- Create: `scripts/load_boundaries.py`
- Delete: `scripts/load_districts.py`

- [ ] **Step 1: Write the loader**

```python
# scripts/load_boundaries.py
"""One-time: load Pakistan admin boundaries (national/province/district/tehsil)
from shapefiles into the PostGIS admin_boundary table.

Geometry is simplified with ST_SimplifyPreserveTopology (~0.001 deg ~= 100 m) on
insert so the impact spatial join stays fast. Full-resolution *display* geometry
is produced separately as vector tiles by scripts/build_tiles.py.

Usage: uv run python scripts/load_boundaries.py
Requires DATABASE_URL and applies the schema itself."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — import side effect: pins PROJ
import fiona  # noqa: E402
import psycopg  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from eqmon.boundaries import map_feature  # noqa: E402
from eqmon.db import _database_url, apply_schema  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "Boundaries_Data"
SOURCES = {
    "national": DATA / "pak_national.shp",
    "province": DATA / "pak_provinces.shp",
    "district": DATA / "pak_districts.shp",
    "tehsil":   DATA / "pak_tehsils.shp",
}
EXPECTED = {"national": 4, "province": 8, "district": 167, "tehsil": 578}
SIMPLIFY_DEG = 0.001  # ~100 m; coarse vs km-scale MMI bands, keeps joins fast

INSERT = (
    "INSERT INTO admin_boundary (level, name, parent, division, population, geom) "
    "VALUES (%s, %s, %s, %s, %s, "
    "ST_Multi(ST_SimplifyPreserveTopology("
    "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)))"
)


def main() -> None:
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
        conn.execute("TRUNCATE admin_boundary RESTART IDENTITY")
        with conn.cursor() as cur:
            for level, path in SOURCES.items():
                count = 0
                with fiona.open(path) as src:
                    for feat in src:
                        cols = map_feature(level, dict(feat["properties"]))
                        geom = json.dumps(mapping(shape(feat["geometry"])))
                        cur.execute(INSERT, (cols["level"], cols["name"], cols["parent"],
                                             cols["division"], cols["population"],
                                             geom, SIMPLIFY_DEG))
                        count += 1
                assert count == EXPECTED[level], \
                    f"{level}: loaded {count}, expected {EXPECTED[level]}"
                print(f"loaded {count} {level}")
        total = conn.execute("SELECT count(*) FROM admin_boundary").fetchone()[0]
        print(f"admin_boundary total rows: {total}")
        assert total == sum(EXPECTED.values()), "total row count mismatch"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Delete the obsolete district loader**

```bash
git rm scripts/load_districts.py
```

- [ ] **Step 3: Run the loader against the dev database**

Run: `uv run python scripts/load_boundaries.py`
Expected output (order may vary only in timing):
```
loaded 4 national
loaded 8 province
loaded 167 district
loaded 578 tehsil
admin_boundary total rows: 757
```
If it errors on a missing field name, re-check that level's mapping in `src/eqmon/boundaries.py` against `fiona.open(path).schema` — do not guess.

- [ ] **Step 4: Spot-check the data**

Run:
```bash
uv run python -c "import os,psycopg; c=psycopg.connect(os.environ['DATABASE_URL']); print(c.execute(\"SELECT level,count(*),count(population) FROM admin_boundary GROUP BY level ORDER BY 1\").fetchall())"
```
Expected: district has non-null populations; province/tehsil/national have 0 populations; counts 4/8/167/578.

- [ ] **Step 5: Commit**

```bash
git add scripts/load_boundaries.py
git commit -m "feat: load_boundaries.py — admin shapefiles into PostGIS (simplified on load)"
```

---

## Task 4: Vector-tile build script

**Files:**
- Create: `scripts/build_tiles.py`

- [ ] **Step 1: Write the tile builder**

```python
# scripts/build_tiles.py
"""One-time: build vector tiles (.pmtiles) for the map overlays.

Runs tippecanoe inside Docker (no native Windows build needed) and writes one
archive per layer into web/tiles/. Admin layers tile directly from their GeoJSON;
faults and plates are first converted shp->GeoJSON (forced 2D) into a temp dir.
Each archive's internal tile layer is named with `-l <id>` so the frontend can
reference it. Tiles are gitignored derived artifacts — regenerate any time.

Usage: uv run python scripts/build_tiles.py   (requires Docker Desktop running)"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import eqmon  # noqa: E402,F401 — pins PROJ
import fiona  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402
from shapely import force_2d  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TILES = ROOT / "web" / "tiles"
TMP = DATA / "_tiles_src"          # gitignored temp GeoJSON for shp-only layers
DOCKER_IMAGE = "ghcr.io/felt/tippecanoe"

# id, source path (relative to ROOT), extra tippecanoe args
ADMIN_LAYERS = [
    ("national",  "data/Boundaries_Data/Pakistan_National.geojson",  ["-z8"]),
    ("provinces", "data/Boundaries_Data/Pakistan_Provinces.geojson", ["-z9"]),
    ("districts", "data/Boundaries_Data/Pakistan_Districts.geojson", ["-z11", "--drop-densest-as-needed"]),
    ("tehsils",   "data/Boundaries_Data/Pakistan_Tehsils.geojson",   ["-z12", "--drop-densest-as-needed"]),
]
# id, source shapefile (relative to ROOT), extra args — converted to GeoJSON first
SHP_LAYERS = [
    ("faults",           "data/Global_Active_Earthquake_Faults-shp/Global_Active_Earthquake_Faults.shp", ["-z10", "--drop-densest-as-needed"]),
    ("plate_boundaries", "data/Tectonic Plate Boundaries/Tectonic_Plate_Boundaries.shp",                  ["-z8"]),
    ("plates",           "data/Tectonic Plates/Tectonic_Plates.shp",                                      ["-z6"]),
]


def _require_docker() -> None:
    try:
        subprocess.run(["docker", "--version"], check=True,
                       capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise SystemExit("Docker is required to build tiles (start Docker Desktop). "
                         f"docker --version failed: {e}")


def _shp_to_geojson(shp_rel: str, layer_id: str) -> str:
    """Convert a shapefile to a 2D GeoJSON FeatureCollection under TMP.
    Returns the new path relative to ROOT (for the Docker mount)."""
    out = TMP / f"{layer_id}.geojson"
    feats = []
    with fiona.open(ROOT / shp_rel) as src:
        for f in src:
            geom = mapping(force_2d(shape(f["geometry"])))
            feats.append({"type": "Feature", "properties": dict(f["properties"]),
                          "geometry": geom})
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return str(out.relative_to(ROOT)).replace("\\", "/")


def _tippecanoe(layer_id: str, src_rel: str, extra: list[str]) -> None:
    """Run tippecanoe in Docker. Paths are relative to ROOT, mounted at /data."""
    out_rel = f"web/tiles/{layer_id}.pmtiles"
    cmd = [
        "docker", "run", "--rm", "-v", f"{ROOT}:/data", DOCKER_IMAGE,
        "tippecanoe", "-o", f"/data/{out_rel}", "-l", layer_id, "-f",
        *extra, f"/data/{src_rel}",
    ]
    print("›", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    _require_docker()
    TILES.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)

    for layer_id, src_rel, extra in ADMIN_LAYERS:
        _tippecanoe(layer_id, src_rel, extra)
    for layer_id, shp_rel, extra in SHP_LAYERS:
        gj_rel = _shp_to_geojson(shp_rel, layer_id)
        _tippecanoe(layer_id, gj_rel, extra)

    built = sorted(p.name for p in TILES.glob("*.pmtiles"))
    print(f"built {len(built)} tile archives: {built}")
    assert len(built) == 7, "expected 7 .pmtiles archives"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the builder (Docker Desktop running)**

Run: `uv run python scripts/build_tiles.py`
Expected: seven `docker run … tippecanoe …` lines, then
`built 7 tile archives: ['districts.pmtiles', 'faults.pmtiles', 'national.pmtiles', 'plate_boundaries.pmtiles', 'plates.pmtiles', 'provinces.pmtiles', 'tehsils.pmtiles']`

- [ ] **Step 3: Verify archives are non-trivial**

Run: `ls -la web/tiles/`
Expected: seven `.pmtiles` files, each > 0 bytes (districts/tehsils a few hundred KB, not hundreds of MB).

- [ ] **Step 4: Commit (script only — tiles are gitignored in Task 6)**

```bash
git add scripts/build_tiles.py
git commit -m "feat: build_tiles.py — seven overlay .pmtiles via tippecanoe-in-Docker"
```

---

## Task 5: Frontend overlays + layer control + rollups

**Files:**
- Modify: `web/index.html:7-10,42-44` (head/scripts)
- Modify: `web/app.js` (add overlays; update `showImpact`)

- [ ] **Step 1: Add the protomaps-leaflet script to `index.html`**

After the Leaflet `<script>` block (currently lines 42-44) and before `<script src="app.js"></script>`, insert:

```html
  <script src="https://unpkg.com/protomaps-leaflet@4.0.0/dist/protomaps-leaflet.min.js"
          crossorigin="anonymous"></script>
```

Then pin its integrity hash. Run this and paste the result into an `integrity="…"` attribute on that tag:

```bash
curl -sL https://unpkg.com/protomaps-leaflet@4.0.0/dist/protomaps-leaflet.min.js \
  | openssl dgst -sha256 -binary | openssl base64 -A | sed 's/^/sha256-/'
```

- [ ] **Step 2: Add the overlay layers + control in `app.js`**

Insert after the base `L.tileLayer(...).addTo(map);` block (currently ends line 4):

```javascript
// --- Vector-tile reference overlays (protomaps-leaflet over pmtiles) ---
// `dataLayer` MUST equal the tippecanoe -l layer id used in scripts/build_tiles.py.
const Line = (color, width) => new protomapsL.LineSymbolizer({ color, width });
const Outline = (color, width) =>
  new protomapsL.PolygonSymbolizer({ fill: "#000000", opacity: 0, stroke: color, width });

function overlay(id, symbolizer) {
  return protomapsL.leafletLayer({
    url: `/tiles/${id}.pmtiles`,
    paintRules: [{ dataLayer: id, symbolizer }],
    backgroundColor: "rgba(0,0,0,0)",
  });
}

const OVERLAYS = {
  National: overlay("national", Outline("#444", 1.5)),
  Provinces: overlay("provinces", Outline("#666", 1.0)),
  Districts: overlay("districts", Outline("#999", 0.6)),
  Tehsils: overlay("tehsils", Outline("#bbb", 0.4)),
  Faults: overlay("faults", Line("#d00000", 1.2)),
  "Plate boundaries": overlay("plate_boundaries", Line("#ff8800", 1.6)),
  Plates: overlay("plates",
    new protomapsL.PolygonSymbolizer({ fill: "#ffcc66", opacity: 0.12 })),
};

// Default-on overlays (others toggle via the control to avoid clutter).
OVERLAYS.National.addTo(map);
OVERLAYS.Provinces.addTo(map);
L.control.layers(null, OVERLAYS, { collapsed: true }).addTo(map);
```

- [ ] **Step 3: Update `showImpact` to consume `rollups`**

Replace the body of `showImpact` (currently `app.js:86-99`) with:

```javascript
async function showImpact(id) {
  impactEl.textContent = "Computing impact…";
  const resp = await fetch(`/events/${id}/impact`, { method: "POST" });
  if (!resp.ok) { impactEl.textContent = "Impact failed"; return; }
  const data = await resp.json();
  if (intensityLayer) map.removeLayer(intensityLayer);
  intensityLayer = L.geoJSON(data.bands, { style }).addTo(map);
  if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  renderRollup(data.rollups, "district");
  impactEl._rollups = data.rollups;
}

// Render one admin level's rollup as a table with a level switcher.
function renderRollup(rollups, level) {
  const top = (rollups[level] || []).filter(d => d.mmi_max > 0).slice(0, 12);
  const opts = ["province", "district", "tehsil"]
    .map(l => `<option value="${l}"${l === level ? " selected" : ""}>${l}</option>`).join("");
  impactEl.innerHTML =
    `<strong>Impact</strong> by <select id="rollup-level">${opts}</select>` +
    "<table style='width:100%'><tr><th align=left>Name</th><th>Max</th><th>Repr</th></tr>" +
    top.map(d => `<tr><td>${escapeHtml(d.name ?? "?")}</td>` +
                 `<td align=center>${d.mmi_max}</td>` +
                 `<td align=center>${d.mmi_repr}</td></tr>`).join("") +
    "</table>";
  document.getElementById("rollup-level").addEventListener("change", (e) =>
    renderRollup(impactEl._rollups, e.target.value));
}

// Minimal HTML escaper for server-supplied names rendered via innerHTML.
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
```

- [ ] **Step 4: Manual verification in the browser**

Run: `uv run uvicorn eqmon.api:app --port 8000` and open `http://localhost:8000/`.
Confirm:
- The layer control (top-right) lists all seven overlays; National + Provinces are on by default.
- Toggling Faults / Plate boundaries / Districts / Tehsils draws each overlay.
- Click "Pull USGS feed", click a catalog event → MMI bands render, the impact table appears, and the level `<select>` switches between province / district / tehsil.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: vector-tile overlays + layer control + multi-level impact table"
```

---

## Task 6: Docs, gitignore, cleanup

**Files:**
- Modify: `.gitignore`
- Modify: `README.md`
- Delete: `boundary/district.geojson`

- [ ] **Step 1: Extend `.gitignore`**

Append:

```
# Raw boundary/seismotectonic source data — kept locally, loaded/tiled via scripts
data/Boundaries_Data/
data/Global_Active_Earthquake_Faults-shp/
data/Tectonic Plate Boundaries/
data/Tectonic Plates/
data/_tiles_src/

# Generated vector tiles (regenerate via scripts/build_tiles.py)
web/tiles/
```

- [ ] **Step 2: Remove the obsolete district GeoJSON**

```bash
git rm boundary/district.geojson
```
(If `boundary/` is now empty, that's fine — git tracks files, not dirs.)

- [ ] **Step 3: Update `README.md`**

- In the "How the data-size problem is solved" section, add a paragraph after the Vs30 one:

```markdown
The boundary and seismotectonic layers follow the same discipline. Admin
polygons load into PostGIS **simplified to ~100 m** (`scripts/load_boundaries.py`)
— enough for the km-scale MMI spatial join, not the 287 MB of raw district
vertices. For *display*, `scripts/build_tiles.py` bakes each layer into a
`.pmtiles` vector-tile archive (tippecanoe, run in Docker); the browser fetches
only the byte ranges it needs via `protomaps-leaflet`. Full-resolution geometry
never crosses the wire.
```

- Replace the Plan B setup line `uv run python scripts/load_districts.py        # 161 districts into PostGIS` with:

```markdown
uv run python scripts/load_boundaries.py       # 757 admin units (4/8/167/578) into PostGIS
uv run python scripts/build_tiles.py           # one-time: build web/tiles/*.pmtiles (needs Docker)
```

- In the Layout block, replace the two lines:
```
schema.sql                  PostGIS tables (seismic_event, district)
scripts/load_districts.py   one-time district load into PostGIS
```
with:
```
schema.sql                  PostGIS tables (seismic_event, admin_boundary)
src/eqmon/boundaries.py     pure shapefile-props -> admin_boundary field mapping
scripts/load_boundaries.py  one-time admin-boundary load into PostGIS (simplified)
scripts/build_tiles.py      one-time overlay .pmtiles via tippecanoe-in-Docker
```

- In the `impact.py` Layout line, change `per-event district impact` to `per-event multi-level impact (province/district/tehsil)`.

- [ ] **Step 4: Run the full suite once more**

Run: `uv run pytest -q`
Expected: all pass/skip, no failures.

- [ ] **Step 5: Commit**

```bash
git add .gitignore README.md
git commit -m "docs: boundary/tile setup + gitignore raw sources and tiles; retire district loader"
```

---

## Self-Review

**Spec coverage:**
- Two-plane architecture → Tasks 2 (PostGIS) + 4 (tiles). ✓
- `admin_boundary` replaces `district` → Task 2. ✓
- Field mapping (verbatim source values) → Task 1. ✓
- Simplify-on-load (~100 m) → Task 3 (`ST_SimplifyPreserveTopology`, `SIMPLIFY_DEG`). ✓
- tippecanoe-in-Docker, faults/plates 2D conversion, layer ids → Task 4. ✓
- Multi-level rollups (province/district/tehsil), national overlay-only → Task 2 (`ROLLUP_LEVELS`). ✓
- protomaps-leaflet overlays + layer control, MMI bands unchanged → Task 5. ✓
- Faults/plates display-only (not in PostGIS) → only appear in Task 4/5, never in schema/loader. ✓
- Raw sources + tiles gitignored, README updated, old artifacts removed → Task 6. ✓
- Tests: pure mapping (Task 1) + DB rollups (Task 2). ✓

**Placeholder scan:** No TBD/TODO. The one computed value (protomaps SRI hash) is produced by an exact command in Task 5 Step 1, not left blank.

**Type/name consistency:** `map_feature(level, props) -> {level,name,parent,division,population}` defined in Task 1, consumed identically in Task 3. `compute_event_impact -> {bands, rollups:{province,district,tehsil}}` defined in Task 2, asserted in the Task 2 test and consumed in Task 5 (`data.rollups`, `renderRollup`). Tile layer ids (`national/provinces/districts/tehsils/faults/plate_boundaries/plates`) match between Task 4 (`-l <id>`, output filename) and Task 5 (`/tiles/${id}.pmtiles`, `dataLayer: id`). ✓
