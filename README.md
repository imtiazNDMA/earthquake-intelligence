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
  api.py         FastAPI /intensity endpoint + static web/ mount
scripts/rasterize_vs30.py   one-time shapefile -> COG
web/             Leaflet map + event form
```

## Tests

```bash
uv run pytest -q
```

## Not yet built (next phase)

Event catalog and feeds are a separate subsystem: Postgres/PostGIS for the
earthquake event catalog, Manual Event Input persistence, MET (Primary) / USGS
(Secondary) feed ingestion, and district impact aggregation against
`boundary/district.geojson`. The Vs30 grid stays a GeoTIFF — it does **not**
belong in the database.
