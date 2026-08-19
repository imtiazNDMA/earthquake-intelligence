# Earthquake Intensity Platform

Interactive Modified Mercalli Intensity (MMI) mapping for the Coverage Region
(Pakistan, India, Afghanistan, Iran, China, Nepal). An operator enters an
event's magnitude, depth, latitude and longitude; the service computes
site-amplified MMI across the region and renders it as filled contour bands on a
Leaflet map. **No ArcGIS dependency** — the intensity model is vectorized NumPy.

## Setup

```bash
uv sync --group dev
uv run python scripts/rasterize_vs30.py   # one-time: builds data/Vs30.tif (~tens of MB)
uv run uvicorn eqmon.api:app --port 8000
```

Open http://localhost:8000/, enter magnitude / depth / lat / lon, and click
**Calculate intensity**.

## How the data-size problem is solved

The source Vs30 layer is 15.4M polygons (3.5 GB) — a *vectorized raster* at 30
arc-second resolution. `scripts/rasterize_vs30.py` rasterizes it **once** into a
Cloud-Optimized GeoTIFF (tens of MB, lossless — the polygons are a regular
grid). At runtime intensity is computed at full native resolution in NumPy; only
the output — a handful of MMI contour bands (tens of KB) — is sent to the
browser. The heavy grid never leaves the server.

The boundary and seismotectonic layers follow the same discipline. Admin
polygons load into PostGIS **simplified to ~100 m** (`scripts/load_boundaries.py`)
— enough for the km-scale MMI spatial join, not the 287 MB of raw district
vertices. For *display*, `scripts/build_tiles.py` bakes each layer into a
`.pmtiles` vector-tile archive (tippecanoe, run in Docker); the browser fetches
only the byte ranges it needs via `protomaps-leaflet`. Full-resolution geometry
never crosses the wire.

## Intensity model

Ported from the original ArcGIS field calculator (`Expression.cal`):

```
r        = sqrt(haversine_dist(epi, cell)^2 + depth^2) / 1000  # km
pga      = 1.385 * 10^(0.49 + 0.23*(mag-6) - log10(r) - 0.0027*r) * 980  # gal
pga_site = pga * 10^(1.35 - 0.47*log10(vs30))                  # site amplification
MMI      = Wald et al. (1999) PGA->MMI, clamped to [1, 10]
```

Epicentral distance uses the haversine (great-circle) formula. The original
arcpy used a GEODESIC call; haversine is fully vectorized (the request stays
interactive over a 24M-cell grid) and the difference is sub-metre in the near
field where high intensities are decided — at most a few km at the grid's far
corners, where MMI is already at its floor. Where the Vs30 grid has no value,
the Default Site Condition (Vs30 = 760 m/s) is used. See `CONTEXT.md` for the
domain language.

## Layout

```
src/eqmon/
  config.py      constants (defaults, Coverage Region, MMI band levels)
  _proj.py       pins PROJ to rasterio's bundled DB (avoids system proj.db clashes)
  vs30.py        load Vs30 COG -> coordinate-aware Grid
  intensity.py   ported formula: PGA + MMI (vectorized NumPy)
  contours.py    MMI grid -> filled-band GeoJSON
  api.py         FastAPI: /intensity + /events* endpoints + static web/ mount
  boundaries.py  pure shapefile-props -> admin_boundary field mapping
  db.py          PostGIS connection pool + schema helpers
  _env.py        loads local .env (DATABASE_URL) into os.environ
  events/        sources.py (USGS + MET stub), ingest.py (dedup), repo.py
  ai/places.py   spatial-first, duplicate-safe admin place resolution
  impact.py      per-event multi-level impact (province/district/tehsil)
schema.sql                  PostGIS tables (seismic_event, admin_boundary)
scripts/rasterize_vs30.py   one-time shapefile -> COG
scripts/load_boundaries.py  one-time admin-boundary load into PostGIS (simplified)
scripts/build_tiles.py      one-time overlay .pmtiles via tippecanoe-in-Docker
web/             Leaflet map + tile overlays + event form + catalog + impact table
```

## Tests

```bash
uv run pytest -q
```

Evaluate deterministic place resolution against the loaded boundary table:

```bash
uv run python scripts/evaluate_places.py
```

Run the opt-in live LM Studio search-tool benchmark:

```bash
uv run python scripts/evaluate_search_tool.py --repeats 3
```

DB-backed tests require a PostGIS test database; set `DATABASE_URL_TEST`
(see below). Without it, those tests skip cleanly and the pure-logic tests run.

## Event catalog & impact (Plan B)

A PostGIS-backed earthquake catalog with Manual Event Input, USGS feed
ingestion, source dedup, and per-event multi-level impact aggregation
(province/district/tehsil).

**One-time database setup** (PostgreSQL + PostGIS):
```sql
CREATE DATABASE eqmon;       \c eqmon       CREATE EXTENSION IF NOT EXISTS postgis;
CREATE DATABASE eqmon_test;  \c eqmon_test  CREATE EXTENSION IF NOT EXISTS postgis;
```
Create a local `.env` (gitignored) with the connection strings:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/eqmon
DATABASE_URL_TEST=postgresql://user:pass@localhost:5432/eqmon_test
```
Then apply the schema and load boundaries:
```bash
uv run python -c "from eqmon.db import init_schema; init_schema()"
uv run python scripts/load_boundaries.py       # 757 admin units (4/8/167/578) into PostGIS
uv run python scripts/build_tiles.py           # one-time: build web/tiles/*.pmtiles (needs Docker)
```

**Endpoints** (in addition to the ad-hoc `POST /intensity`):

| Endpoint | Purpose |
|---|---|
| `POST /events` | Manual Event Input (Coverage-Region validated) |
| `POST /events/ingest` | Pull the USGS feed (Secondary Seismic Source) now |
| `GET /events` | List canonical catalog events (`since`, `min_magnitude`, `limit`) |
| `POST /events/search` | Validated catalog search with dates, point/radius, and mainshock state |
| `GET /events/{id}` | Event detail |
| `POST /events/{id}/impact` | MMI bands + multi-level impact (province/district/tehsil: max band + representative MMI) |

**Sources:** USGS is fully implemented behind a `SeismicSource` interface; the
Pakistan MET feed (Primary) is a documented stub (`METSource`) pending its
format. **Dedup:** feed events within 60 s / 50 km cluster; the higher-priority
source (MET > USGS) is canonical. **The Vs30 grid stays a GeoTIFF — it is not in
the database.**

## Infra Vulnerability layer (building footprints)

The **Infra** panel renders Pakistan building footprints, banded by height, from
an external [TileServerGL](https://github.com/maptiler/tileserver-gl) instance
serving one vector dataset per district (161 `.mbtiles`, layer id `buildings`).
Height is the only usable attribute in those tiles — it stands in for
vulnerability and is **not** a calculated risk score; the legend says so.

The tile server is not part of this repo. Point the app at a running instance:

```
BUILDINGS_TILE_URL=http://172.19.119.216:8081   # .env; defaults to http://172.19.112.1:8081
```

That host is typically a WSL IP, which changes between reboots — hence the env
var rather than a baked-in frontend URL. To serve the datasets:

```bash
npm install -g tileserver-gl-light
cd <mbtiles-dir> && tileserver-gl --config config.json -p 8081 --bind 0.0.0.0
```

FastAPI proxies both the catalog and the tiles (`src/eqmon/buildings.py`) so the
frontend stays same-origin; `dataset` is checked against the cached catalog
before any upstream request, so the proxy cannot be pointed at arbitrary paths.
Buildings render only at zoom ≥ 12 and only for districts intersecting the
viewport — typically 1–4 live sources instead of all 161.

## Elements at risk (ARC)

`POST /events/{id}/exposure` and `POST /exposure/analyze` report what sits under
each MMI band — population, settlements, hospitals, schools, roads, bridges,
airports — by handing our band layer to **ARC**, an external elements-at-risk
service (`API.md` documents ARC's own API).

This complements `/events/{id}/impact` rather than replacing it: impact rolls up
*which admin units* shake from PostGIS, exposure counts *what is inside* the
shaking. They are computed independently, and ARC being down never affects
impact.

```
ARC_URL=http://172.18.0.12:5002    # .env; the service moves with its container
ARC_TIMEOUT_S=180                  # a full scan is ~12 s, roads is ~375k features
```

Pass `layers` to narrow the scan when only some are needed — population and
hospitals alone returns in ~2 s instead of ~12 s.

**Two things the adapter (`src/eqmon/exposure.py`) is careful about:**

- **Band vocabulary.** ARC dissolves on `mmi_high`; our domain name is
  `mmi_upper` (`contours.py`). `to_arc_bands()` is the only place that
  translation lives — ARC's field names never enter the rest of the codebase.
- **What "MMI 6 and above" means.** ARC keys `cumulative[].mmi_min` on a band's
  *upper* bound, so its `mmi_min: 6` row includes the 5–6 band, which this
  platform labels MMI V. The headline is therefore summed from the bands
  (ARC guarantees they are mutually exclusive), not read from `cumulative`. On a
  real M7 the difference is 9.4M people versus 17.4M.

The response leads with `at_min_mmi` (exposure at or above `EXPOSURE_MIN_MMI`,
default 6). `totals` covers the whole footprint down to MMI 2 — for a large
event that is most of the country and a nine-figure population, so it is
reference data, not a headline.

## Seismic hazard (PGA) overlays

The Layers panel carries probabilistic peak ground acceleration for the region
at four return periods — 95, 475, 975 and 2475 years (41%, 10%, 5% and 2%
probability of exceedance in 50 years). This is the long-run hazard at a place,
independent of whatever event is on the map, so it renders *underneath* the MMI
footprint and carries its own legend.

Source grids live in `data/PGA/` as float32 GeoTIFFs in g. Browsers cannot read
a GeoTIFF, and at 347×250 the grids are far too small to be worth tiling, so
each is classified into its five published bands and written as an RGBA PNG:

```bash
uv run python scripts/build_pga_overlays.py   # -> web/pga/ (gitignored)
```

**The class breaks are not computed.** They are transcribed from
`data/PGA/PGA_Return_Period_Legend.png`, the legend shipped with the data, and
each return period has its own breaks over a shared five-step ramp. Re-deriving
them (equal interval, quantile, Jenks) would produce a map that disagrees with
the published hazard maps these grids came from.

### Zonation

`data/PGA/PGA.shp` is the five-zone building-code seismic zonation (Zone 1, 2A,
2B, 3, 4). It tiles like every other vector overlay (`scripts/build_tiles.py`)
and appears in the Overlays list with its class key beneath it; hovering a zone
names it.

Its fills come from `data/PGA/PGAstyles.sld`, the style shipped with the data,
not from a palette chosen here — same rule as the raster breaks. Note the ramp
is not monotonic in lightness (Zone 2A is darker than Zone 1); that is what the
source says, and reproducing a published map faithfully beats making it prettier.

## Landslide susceptibility

The Layers panel can lazily render the supplied **Very High** landslide
susceptibility masks for AJK, Gilgit-Baltistan, Khyber Pakhtunkhwa, and
Balochistan. The layer is categorical and filtered: transparent pixels are not
automatically a lower susceptibility class and may be outside assessed coverage.

Raw ArcGIS `RasterToPolygon` exports live locally under
`data/LS Susceptability Maps/` and are intentionally ignored. Build the layer in
two stages:

```bash
uv run python scripts/prepare_landslide_data.py  # categorical regional COGs
uv run python scripts/build_landslide_tiles.py   # web/landslides/*.pmtiles
```

Both outputs are reproducible and gitignored. Preparation validates CRS and
`gridcode = 5`, repairs invalid polygon topology, records source SHA-256 values,
and uses nearest-neighbor categorical processing. The approved Very High color
is hazard red `#D73027`; display opacity remains adjustable in the map.
