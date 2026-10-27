# EQ-ARC — MMI Exposure Analysis

An API that takes an MMI (shaking intensity) polygon layer, dissolves and
smooths it on `mmi_high`, and reports the elements sitting underneath each band.

## Quick start

```bat
run_server.bat
```

That builds the layer caches on first run (once, ~2.5 min), starts the API and
opens the demo page. Click **Run analysis**.

The server binds to all interfaces, so it is reachable from other machines on
the network at `http://<server-ip>:5000` — it prints its own address on
startup. If other machines cannot connect, run **`allow_firewall.bat`** once as
administrator to open TCP 5000. To keep the server local only, set
`HOST=127.0.0.1` in `run_server.bat`.

If port 5000 is already taken by another program, `run_server.bat` moves to the
next free port, says so, and opens the browser there — so always read the port
off the startup banner rather than assuming 5000.

Because it is network-reachable, `source: "path"` requests are restricted to
the project directory (`ALLOWED_PATH_ROOTS` in `scripts/eqarc/config.py`).
Uploads are unaffected. Note there is no authentication — this is meant for a
trusted internal network, and it runs Flask's development server.

## Layout

| Path | What it is |
| --- | --- |
| `scripts/server.py` | Flask API |
| `scripts/build_cache.py` | one-time index builder |
| `scripts/eqarc/config.py` | paths, layer registry, **smoothing settings**, GDAL/PROJ setup |
| `scripts/eqarc/vectorio.py` | reads shapefile / GeoJSON / zip → WGS84 |
| `scripts/eqarc/dissolve.py` | dissolve + smoothing pipeline |
| `scripts/eqarc/cachebuild.py` | GeoJSON → compact `.npz` indexes |
| `scripts/eqarc/exposure.py` | the overlay / counting engine |
| `scripts/web/index.html` | demo page |
| `run_server.bat`, `build_cache.bat` | launchers |
| `allow_firewall.bat` | open TCP 5000 for network access (run as admin) |
| `API.md` | how to call the API |

## Why there is a cache step

The element layers are large — `population.geojson` alone is 1.77 GB with
1.33 M features and 53 fields; `roads.geojson` is 576 MB with 640 k lines.
Re-parsing those per request would take minutes.

`build_cache.py` reads each layer once and writes a compact `.npz` to
`data/cache/`:

- point layers → `x`, `y` arrays
- population → `x`, `y`, plus **pre-summed** `pop_f` / `pop_m`
- roads → packed WKB + a bounding-box table for cheap prefiltering

**2.4 GB of GeoJSON → 145 MB of cache, built in ~150 s.** Pre-summing the 36
`glob_[fm]_*` age columns at build time is what makes the population query
0.12 s instead of a 1.33 M × 36 field walk. Rerun `build_cache.bat` (or
`build_cache.bat --force`) whenever a source layer changes.

## Dissolve and smoothing

The sample MMI layer is messy in a specific way: 322 polygons carrying **2942
interior rings**, 83 % of them slivers under 1 km², plus hairline overlaps
between neighbouring bands along shared contour edges.

The pipeline in `dissolve.py`:

1. **repair** — `make_valid()` every part
2. **dissolve** — `union_all()` grouped by `mmi_high`
3. **close** — `buffer(+d).buffer(-d)` heals pinholes and takes the staircase
   edge off the contours
4. **declutter** — drop interior rings and islands below an area threshold
5. **simplify** — Douglas-Peucker, topology preserved
6. **exclusive** — subtract higher bands from lower ones

On the sample data that takes holes **2942 → 280** and vertices 24 571 → 16 209
in ~0.9 s. Tolerances are given in metres / km² and converted to degrees
internally, since the data is EPSG:4326.

### Where the settings live

All of them are server-side, in one place — `DEFAULT_SMOOTHING` in
[`scripts/eqarc/config.py`](scripts/eqarc/config.py). Edit there and restart
the server. The web page never sends them.

| Setting | Default | Effect |
| --- | ---: | --- |
| `field` | `mmi_high` | attribute the bands are dissolved on |
| `closing_m` | 600 | morphological closing distance, metres |
| `min_hole_km2` | 1.0 | interior rings smaller than this are filled |
| `min_part_km2` | 0.5 | islands smaller than this are dropped |
| `simplify_m` | 200 | Douglas-Peucker tolerance, metres |
| `enforce_exclusive` | `true` | subtract higher bands from lower ones |

## Counting rule

Bands are walked strongest-first and each element is claimed by the **highest
MMI band it falls in**, then removed from the pool. That gives:

- no double counting where bands touch,
- nothing lost on a shared boundary (unlike a strict `contains()` test),
- a road spanning several bands attributed to its worst-case shaking.

Because per-band figures are mutually exclusive, the cumulative "MMI ≥ X" view
is just a running total. This rule is what makes counts *independent of*
`enforce_exclusive` — turning that flag off changes the reported area and the
map geometry, but not a single count.

Metrics: **population** is the sum of `glob_f_*` (female) and `glob_m_*` (male)
age columns, with total = male + female. **Every other layer is a feature
count.**

## API

See **[API.md](API.md)** for how to send a request and read the response.

The short version — everything else has a default:

```bat
curl -X POST http://127.0.0.1:5000/api/analyze ^
  -H "Content-Type: application/json" ^
  -d "{\"source\":\"sample\"}"
```

| Endpoint | Purpose |
| --- | --- |
| `POST /api/analyze` | analyse a server-side or inline MMI layer |
| `POST /api/analyze/upload` | analyse an uploaded shapefile / zip / GeoJSON |
| `GET /api/health` | service + cache status |
| `GET /api/layers` | element layer registry |
| `GET /api/mmi/sample` | raw sample bands as GeoJSON |

## Results on the sample layer

| Band | Area km² | Population | Male | Female | Settl. | Hosp. | Schools | Roads | Bridges | Airports |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 9–10 | 52 | 35 999 | 18 499 | 17 499 | 9 | 0 | 2 | 2 | 0 | 0 |
| 8–9 | 584 | 819 669 | 419 943 | 399 726 | 188 | 33 | 249 | 858 | 2 | 1 |
| 7–8 | 1 508 | 1 742 037 | 894 088 | 847 949 | 472 | 49 | 296 | 2 199 | 2 | 1 |
| 6–7 | 3 672 | 4 198 332 | 2 196 066 | 2 002 266 | 1 235 | 134 | 1 015 | 12 119 | 9 | 1 |
| 5–6 | 9 279 | 10 556 614 | 5 546 385 | 5 010 229 | 4 064 | 292 | 1 795 | 40 827 | 12 | 3 |
| 4–5 | 32 338 | 22 562 322 | 11 607 164 | 10 955 158 | 13 988 | 961 | 4 304 | 75 368 | 37 | 7 |
| 3–4 | 98 097 | 37 415 990 | 19 407 527 | 18 008 463 | 21 291 | 1 479 | 5 290 | 55 666 | 58 | 6 |
| 2–3 | 169 045 | 60 902 009 | 32 156 983 | 28 745 026 | 21 262 | 1 597 | 5 096 | 173 355 | 83 | 5 |
| **Total** | **314 574** | **138 232 972** | **72 246 656** | **65 986 316** | **62 509** | **4 545** | **18 047** | **360 394** | **203** | **24** |

End to end: ~6.9 s round trip (0.9 s dissolve, 5.9 s exposure, of which roads
are 5.7 s — every other layer is under 0.15 s).

## Environment

Python 3.11 venv at `.venv` (3.11 specifically — the GDAL wheel is `cp311`):

```bat
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install "D:\Software\GDAL-3.4.3-cp311-cp311-win_amd64.whl"
.venv\Scripts\python -m pip install numpy "shapely>=2.0" flask flask-cors
```

`eqarc/config.py` force-sets `PROJ_LIB` / `GDAL_DATA` to the data bundled in the
GDAL wheel. This is deliberate: this machine already exports a system-wide
`PROJ_LIB=C:\OSGeo4W\share\proj` and a PostgreSQL `GDAL_DATA`, and deferring to
them makes every CRS lookup fail with `Cannot find proj.db`.
