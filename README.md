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
| `GET /events/{id}` | Event detail |
| `POST /events/{id}/impact` | MMI bands + multi-level impact (province/district/tehsil: max band + representative MMI) |

**Sources:** USGS is fully implemented behind a `SeismicSource` interface; the
Pakistan MET feed (Primary) is a documented stub (`METSource`) pending its
format. **Dedup:** feed events within 60 s / 50 km cluster; the higher-priority
source (MET > USGS) is canonical. **The Vs30 grid stays a GeoTIFF — it is not in
the database.**
