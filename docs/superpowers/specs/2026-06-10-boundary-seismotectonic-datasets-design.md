# Boundary & Seismotectonic Datasets — Design

**Date:** 2026-06-10
**Branch:** `feat/boundary-datasets`
**Status:** Approved design (pending implementation plan)

## Goal

Add the datasets dropped into `data/` to the platform "like a professional
software engineer, in the most efficient possible way":

- **Admin boundaries** (`data/Boundaries_Data/`): national (4 features),
  provinces (8), districts (167, with `division` + `Population`), tehsils (578).
  Available as both shapefiles and GeoJSON; the district/tehsil GeoJSON are
  **287 MB / 295 MB** (extreme vertex density).
- **Seismotectonic reference** : Global Active Earthquake Faults
  (`data/Global_Active_Earthquake_Faults-shp/`, ~6.4 MB lines), Tectonic Plate
  Boundaries (220 KB lines), Tectonic Plates (36 KB polygons).

All sources are **WGS84 (EPSG:4326)** — matches existing `geom ... 4326`; no
reprojection needed.

These must enable two things (decided with the user):
1. **Toggleable map overlays** for every layer.
2. **Multi-level impact aggregation** — per-event MMI rollups at province /
   district / tehsil level (generalising today's district-only impact).

## Guiding principle (from README)

> Heavy data stays server-side; only small outputs reach the browser.

The Vs30 layer already follows this (3.5 GB of polygons → a tens-of-MB COG →
KB of contour bands per request). This design extends the same discipline to
vector data: full-resolution geometry never reaches the browser.

## Architecture — two planes, one source of truth

| Plane | Tech | Purpose | Datasets |
|---|---|---|---|
| **Geometry plane** | PostGIS | spatial joins for impact aggregation | national, province, district, tehsil polygons |
| **Display plane** | pmtiles (static, range-served) | map overlays | all admin levels **+ faults + plate boundaries + plates** |

Faults and plates are **display-only**: nothing queries them, so they go to
tiles but **not** PostGIS. Adding "distance to nearest fault" analytics later is
a deliberate YAGNI deferral (would add faults to the geometry plane then).

Admin polygons live in **both** planes — PostGIS for aggregation, tiles for
display — generated from the **same shapefile source** so the two planes never
drift.

## 1. Data model — generic `admin_boundary` replaces `district`

```sql
CREATE TABLE admin_boundary (
    id         BIGSERIAL PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN ('national','province','district','tehsil')),
    name       TEXT NOT NULL,
    parent     TEXT,                 -- province for a district; district for a tehsil
    division   TEXT,                 -- present on district & tehsil sources
    population DOUBLE PRECISION,      -- present on district source only
    geom       geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX admin_boundary_geom_gix ON admin_boundary USING GIST (geom);
CREATE INDEX admin_boundary_level_ix ON admin_boundary (level);
```

One table parameterised by `level` — adding a level later is **data, not
schema**. The existing `district` table, `boundary/district.geojson`, and
`scripts/load_districts.py` are **retired**.

### Field mapping (per level)

Field names are read from each shapefile's `fiona` schema at implementation
time (shapefile DBF truncates to 10 chars); the mapping below is the intent,
verified against the live schema before insert — **not** hardcoded blind.

| level | name ← | parent ← | division ← | population ← |
|---|---|---|---|---|
| national | `Admin01_Na` | — | — | — |
| province | `Province` | — | — | — |
| district | `Districts` | `province` | `division` | `Population` |
| tehsil | `name` | `district` | `division` | — |

Source values are preserved **verbatim** (including politically-worded province
names); editorial relabeling is out of scope.

## 2. Load pipeline — `scripts/load_boundaries.py`

One-time loader (mirrors `load_districts.py` conventions: `sys.path` shim,
`apply_schema`, `TRUNCATE ... RESTART IDENTITY`, row-count assert).

- Reads the **shapefiles** via `fiona` (already a dependency) — not the 287 MB
  GeoJSON.
- **Simplifies on load** with `ST_SimplifyPreserveTopology` at a configurable
  tolerance (~0.001° ≈ 100 m) before insert.
  - *Why:* MMI bands are km-scale and coarse. Sub-100 m district vertices add
    nothing to an `ST_Intersects` join but make every impact request crawl over
    287 MB of geometry. Display fidelity is preserved separately by the tiles
    (tippecanoe simplifies per zoom). This is the same "right resolution for the
    job" trade-off as the Vs30 rasterisation.
- Wraps to `ST_Multi(ST_SetSRID(..., 4326))` so mixed Polygon/MultiPolygon
  sources land in the `MultiPolygon` column.
- Idempotent; loads all four levels in one run; asserts per-level counts
  (4 / 8 / 167 / 578).

## 3. Tile build pipeline — `scripts/build_tiles.py`

One-time build (peer of `rasterize_vs30.py`). Emits one `.pmtiles` per layer
into `web/tiles/`.

- Generation via **tippecanoe in Docker** (`docker run --rm -v <repo>:/data
  ghcr.io/felt/tippecanoe ...`) — OS-independent on the user's Windows host,
  best per-zoom simplification. tippecanoe collapses the 287 MB district source
  to a few hundred KB of tiles.
- Source for tiles is the **GeoJSON** files (tippecanoe's native input); faults
  and plates are converted shp→GeoJSON first (via `fiona`) since they have no
  GeoJSON sibling.
- A small per-layer config (id, source path, min/max zoom, simplification)
  drives the loop — no copy-paste per layer.
- Build tool is **dev-time only**; the runtime never needs Docker.

`web/tiles/*.pmtiles` are **gitignored** (derived artifacts, like
`data/Vs30.tif`); `build_tiles.py` regenerates them and the README documents the
step.

### Serving

`web/tiles/` is under the existing `StaticFiles` mount at `/`. FastAPI's
`StaticFiles` honours HTTP **Range** requests, which is exactly how the pmtiles
client fetches byte ranges — no new endpoint or middleware required.

## 4. API — generalise impact to admin levels

`impact.compute_event_impact` today returns `{"bands", "districts"}` via a
temp-table spatial join against `district`. Change:

- Join target becomes `admin_boundary` filtered by `level`.
- A helper runs the existing max-band-per-unit + representative-point logic for
  a **given level**; `compute_event_impact` calls it for `province`, `district`,
  `tehsil` and returns:

```jsonc
{
  "bands": { /* GeoJSON FeatureCollection, unchanged */ },
  "rollups": {
    "province": [ {"id","name","parent","mmi_max","mmi_repr"}, ... ],
    "district": [ ... ],
    "tehsil":   [ ... ]
  }
}
```

The temp `_bands` table is built **once** per request and reused across all
three level joins (it does not depend on level). `POST /events/{id}/impact` and
the ad-hoc path return the new shape.

*Future extension (out of scope):* `population` is now available, enabling a
population-weighted exposure metric ("people in MMI ≥ 6"). Noted, not built.

## 5. Frontend — keep Leaflet, add `protomaps-leaflet`

The base map, MMI bands, and epicenter are **unchanged** (still API GeoJSON).

- Add `protomaps-leaflet` via CDN (unpkg, SRI-pinned, matching the existing
  Leaflet pin style).
- A small client-side manifest maps each layer to its `/tiles/<id>.pmtiles` URL
  and a paint rule (province/national: outline only; districts: thin lines;
  tehsils: lighter lines; faults: red lines; plate boundaries: orange; plates:
  faint fill).
- A Leaflet **layer control** (`L.control.layers`) toggles all seven overlays.
  Default-on: national + provinces (others off to avoid clutter on load).
- The MMI band layer renders **above** the overlays.
- Ties into the earlier UI review: impact-table rows can highlight their matching
  district (deferred polish, not required for this task's acceptance).

## 6. Source data in git

Mirror the Vs30 precedent: **raw heavy sources stay local and gitignored**;
provenance is documented in the README. Committing ~600 MB of raw GeoJSON is a
non-starter. Derived forms (PostGIS rows, `.pmtiles`) are not in git either
(DB is external; tiles are gitignored). `.gitignore` adds:

```
# Raw boundary/seismotectonic source data — kept locally, loaded/tiled via scripts
data/Boundaries_Data/
data/Global_Active_Earthquake_Faults-shp/
data/Tectonic Plate Boundaries/
data/Tectonic Plates/

# Generated vector tiles (regenerate via scripts/build_tiles.py)
web/tiles/
```

## 7. Testing

- **Pure** (no DB): the field→column mapping function per level — table-driven,
  fast, covers the truncated-name and missing-field cases.
- **DB-backed** (skip without `DATABASE_URL_TEST`, matching existing pattern):
  load a tiny multi-level fixture, run `compute_event_impact`, assert the
  `rollups` shape and that a known event yields expected `mmi_max` ordering per
  level.
- **Tile build:** not unit-tested (Docker dependency); `build_tiles.py` does a
  preflight check that Docker is available and fails with a clear message
  otherwise.

## 8. Migration & docs

- `schema.sql`: drop `district`, add `admin_boundary`.
- Delete `scripts/load_districts.py` and `boundary/district.geojson`.
- Update `impact.py` (and any `district`-table references) to `admin_boundary`.
- README: extend "How the data-size problem is solved" to cover tiles; replace
  the load-districts step with `load_boundaries.py` + `build_tiles.py`; fix the
  "161 districts" line; update the Layout block.
- `web/app.js` impact rendering consumes `rollups.district` (plus province/tehsil
  tables/toggles).

## Out of scope (YAGNI)

- Faults/plates in PostGIS; nearest-fault analytics.
- Population-weighted exposure metric.
- MapLibre migration (Leaflet + protomaps-leaflet suffices).
- Vector-tile *serving* infra beyond static files (no tile server).
- Impact-table → map highlight interaction (UI-review polish, separate task).

## Build / acceptance sequence

1. Schema + `admin_boundary`.
2. `load_boundaries.py` → 4/8/167/578 rows loaded & simplified.
3. `impact.py` generalised; tests green.
4. `build_tiles.py` → seven `.pmtiles` in `web/tiles/`.
5. Frontend overlays + layer control render all seven layers; MMI bands still work.
6. README + cleanup; old district artifacts removed.
