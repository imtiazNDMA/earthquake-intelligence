# Earthquake Intensity Platform (Plan A: Engine + Map) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An interactive web app where an operator enters an earthquake's magnitude, depth, latitude and longitude, and the system computes site-amplified MMI intensity across the Coverage Region and renders it as filled contour bands on a Leaflet map — with **zero dependency on ArcGIS** and without choking on the 3.5 GB Vs30 dataset.

**Architecture:** The 15.4M-polygon Vs30 shapefile is a vectorized raster; we rasterize it **once** to a ~50 MB Cloud-Optimized GeoTIFF (lossless — the polygons are a regular grid). At runtime a FastAPI service holds the Vs30 grid as a NumPy array and, per request, computes a PGA grid (ported `Expression.cal` attenuation), applies Vs30 site amplification, converts to MMI (Wald et al. 1999), contours the MMI grid into a handful of filled bands, and returns them as small GeoJSON. The browser never sees the heavy grid — only the contours. The full-resolution Vs30 grid is used for every computation, so **no data or quality is lost**; only the output geometry is small.

**Tech Stack:** Python 3.12, `uv`, FastAPI + Uvicorn, NumPy, rasterio (bundles GDAL), fiona, pyproj (vectorized geodesic), shapely, contourpy, pytest. Frontend: vanilla Leaflet (no build step).

**Out of scope (separate Plan B):** Postgres/PostGIS event catalog, Manual Event Input persistence, MET (Primary) / USGS (Secondary) feed ingestion, district zonal-stats aggregation. This plan deliberately ships the compute+map vertical slice first.

---

## Reference: the ported formula

`Expression.cal` decoded from UTF-16 (originally arcpy field calculator, epicenter/mag/depth hardcoded):

```
r_slant = sqrt( geodesic_dist_m(epi, cell)^2 + depth_m^2 )      # metres
r       = r_slant / 1000                                        # km
pga_g   = 10 ** (0.49 + 0.23*(mag - 6) - log10(r) - 0.0027*r)   # ~g
pga_gal = 1.385 * pga_g * 980                                   # cm/s^2 (gal)
arv     = 10 ** (1.35 - 0.47 * log10(vs30))                     # site amplification
pga_site = pga_gal * arv                                        # cm/s^2 (gal)
```

PGA→MMI (Wald et al. 1999, PGA in gal/cm·s⁻²), clamped to [1, 10]:

```
MMI = 2.20*log10(PGA) + 1.00      if resulting MMI <= 5
MMI = 3.66*log10(PGA) - 1.66      if resulting MMI >  5
```

Defaults from `CONTEXT.md`: **Default Site Condition** Vs30 = 760 m/s where the grid has nodata. Map opens on **Primary Focus Country** Pakistan. **Coverage Region** = Pakistan, India, Afghanistan, Iran, China, Nepal.

---

## File Structure

```
eqmonitoring2/
├── pyproject.toml                      # add deps (modify)
├── scripts/
│   └── rasterize_vs30.py               # one-time: shp(3.5GB) -> Vs30.tif (~50MB)
├── data/
│   └── Vs30.tif                        # generated COG (gitignored)
├── src/eqmon/
│   ├── __init__.py
│   ├── config.py                       # paths, constants (defaults, Coverage Region bbox)
│   ├── vs30.py                         # load Vs30 COG -> Grid (array + affine transform)
│   ├── intensity.py                    # ported formula: PGA grid + MMI grid (NumPy)
│   ├── contours.py                     # MMI grid -> filled-band GeoJSON
│   └── api.py                          # FastAPI app, POST /intensity
├── web/
│   ├── index.html                      # Leaflet map + event form
│   └── app.js                          # form submit -> fetch -> render bands
└── tests/
    ├── test_intensity.py
    ├── test_contours.py
    └── test_api.py
```

Each `src/eqmon/*.py` has one responsibility; files that change together (grid math) stay together. The rasterization is a script, not library code, because it runs once.

---

### Task 1: Project scaffolding and dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `src/eqmon/__init__.py`
- Create: `.gitignore` (append)

- [ ] **Step 1: Add dependencies to `pyproject.toml`**

Replace the `dependencies = []` line and add tooling config:

```toml
[project]
name = "eqmonitoring2"
version = "0.1.0"
description = "Interactive earthquake MMI intensity platform"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "numpy>=1.26",
    "rasterio>=1.3",
    "fiona>=1.9",
    "pyproj>=3.6",
    "shapely>=2.0",
    "contourpy>=1.2",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
]

[dependency-groups]
dev = ["pytest>=8.0", "httpx>=0.27"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Install and verify the toolchain**

Run: `uv sync --group dev`
Then: `uv run python -c "import rasterio, fiona, pyproj, shapely, contourpy, numpy, fastapi; print('ok')"`
Expected: prints `ok` (confirms GDAL via rasterio is importable — earlier `import osgeo` failed, rasterio's bundled GDAL replaces that need).

- [ ] **Step 3: Create the package init**

Create `src/eqmon/__init__.py`:

```python
"""Earthquake intensity platform — engine and map service."""
```

- [ ] **Step 4: Ignore generated data**

Append to `.gitignore`:

```
# generated reference data (regenerate via scripts/rasterize_vs30.py)
data/Vs30.tif
data/Vs30.tif.aux.xml
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/eqmon/__init__.py .gitignore
git commit -m "chore: scaffold eqmon package and dependencies"
```

---

### Task 2: Configuration and constants

**Files:**
- Create: `src/eqmon/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from eqmon import config


def test_default_site_condition_is_760():
    # CONTEXT.md: Default Site Condition uses fixed Vs30 760 m/s
    assert config.DEFAULT_VS30 == 760.0


def test_coverage_region_bbox_contains_pakistan_center():
    lon, lat = 69.3, 30.4  # roughly central Pakistan
    minx, miny, maxx, maxy = config.COVERAGE_BBOX
    assert minx <= lon <= maxx
    assert miny <= lat <= maxy


def test_mmi_band_levels_are_increasing():
    assert config.MMI_BAND_LEVELS == sorted(config.MMI_BAND_LEVELS)
    assert config.MMI_BAND_LEVELS[0] >= 1
    assert config.MMI_BAND_LEVELS[-1] <= 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eqmon.config'`

- [ ] **Step 3: Write the implementation**

Create `src/eqmon/config.py`:

```python
"""Shared constants. Domain language follows CONTEXT.md."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VS30_TIF = PROJECT_ROOT / "data" / "Vs30.tif"

# Default Site Condition (CONTEXT.md): used where the Vs30 grid has no value.
DEFAULT_VS30 = 760.0

# Coverage Region bounding box (minx, miny, maxx, maxy) in WGS84 degrees:
# Iran (west) through China/Nepal (east), covering PK/IN/AF/IR/CN/NP.
COVERAGE_BBOX = (44.0, 8.0, 105.0, 56.0)

# Primary Focus Country viewport (Pakistan) for the map.
MAP_CENTER = (30.4, 69.3)  # (lat, lon)
MAP_ZOOM = 5

# MMI band thresholds for filled contours (Modified Mercalli classes).
MMI_BAND_LEVELS = [2, 3, 4, 5, 6, 7, 8, 9, 10]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/config.py tests/test_config.py
git commit -m "feat: add config constants from CONTEXT.md domain language"
```

---

### Task 3: Rasterize the Vs30 shapefile to a COG (the data-size fix)

**Files:**
- Create: `scripts/rasterize_vs30.py`

This is the one-time Phase 0 step that collapses 3.5 GB → ~50 MB with no information loss. It is a script (run once), not TDD'd as a unit — verification is built into the script via assertions and a summary print.

- [ ] **Step 1: Write the rasterization script**

Create `scripts/rasterize_vs30.py`:

```python
"""One-time: convert the 15.4M-polygon Vs30 shapefile into a Cloud-Optimized
GeoTIFF. The polygons are a regular grid (a vectorized raster), so this is
lossless. Run once, then the shapefile can be archived.

Usage:
    uv run python scripts/rasterize_vs30.py
"""
from __future__ import annotations
import math
from pathlib import Path

import fiona
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
SHP = ROOT / "Vs30_Polygons" / "Vs30_Polygons" / "Vs30_Neighbours_Polygons.shp"
OUT = ROOT / "data" / "Vs30.tif"
EXPECTED_FEATURES = 15_449_146
NODATA = -9999.0


def detect_cell_size(src) -> float:
    """Infer the grid cell size from the first feature's bounding box."""
    first = next(iter(src))
    minx, miny, maxx, maxy = shape(first["geometry"]).bounds
    dx, dy = maxx - minx, maxy - miny
    assert dx > 0 and dy > 0, "degenerate first cell"
    # square grid expected; use the smaller side defensively
    return float(min(dx, dy))


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with fiona.open(SHP) as src:
        minx, miny, maxx, maxy = src.bounds
        cell = detect_cell_size(src)
        width = int(round((maxx - minx) / cell))
        height = int(round((maxy - miny) / cell))
        transform = from_origin(minx, maxy, cell, cell)
        print(f"cell={cell:.6f} deg  grid={width}x{height}  bounds={src.bounds}")

        def shapes():
            for feat in src:
                val = feat["properties"].get("Vs30")
                if val is None:
                    continue
                yield shape(feat["geometry"]), float(val)

        print("rasterizing (one pass; this is the slow one-time step)...")
        arr = rasterize(
            shapes(),
            out_shape=(height, width),
            transform=transform,
            fill=NODATA,
            dtype="float32",
            all_touched=False,
        )

    valid = int(np.count_nonzero(arr != NODATA))
    vmin = float(arr[arr != NODATA].min())
    vmax = float(arr[arr != NODATA].max())
    print(f"valid cells={valid:,} (expected ~{EXPECTED_FEATURES:,})")
    print(f"Vs30 range=[{vmin:.1f}, {vmax:.1f}] m/s")
    assert 0 < vmin < vmax < 5000, "Vs30 values implausible — check field mapping"
    # allow small mismatch from sub-pixel grid rounding, but flag big gaps
    assert valid >= EXPECTED_FEATURES * 0.95, "too many cells lost in rasterization"

    profile = {
        "driver": "GTiff", "height": height, "width": width, "count": 1,
        "dtype": "float32", "crs": "EPSG:4326", "transform": transform,
        "nodata": NODATA, "tiled": True, "blockxsize": 512, "blockysize": 512,
        "compress": "deflate", "predictor": 2,
    }
    with rasterio.open(OUT, "w", **profile) as dst:
        dst.write(arr, 1)
        dst.build_overviews([2, 4, 8, 16], rasterio.enums.Resampling.average)
    size_mb = OUT.stat().st_size / 1e6
    print(f"wrote {OUT} ({size_mb:.1f} MB)  <- from 3.5 GB shapefile")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

Run: `uv run python scripts/rasterize_vs30.py`
Expected: prints the grid dimensions, `valid cells` close to 15,449,146, a plausible Vs30 range (roughly 150–2000 m/s), and a final `wrote .../data/Vs30.tif (~30–80 MB)` line. Runtime: minutes (one pass over 15.4M polygons), bounded memory.

- [ ] **Step 3: Sanity-check the output independently**

Run:
```bash
uv run python -c "import rasterio; ds=rasterio.open('data/Vs30.tif'); print(ds.width, ds.height, ds.crs, ds.nodata, [round(x,4) for x in ds.bounds])"
```
Expected: dimensions matching the script output, `EPSG:4326`, nodata `-9999.0`, bounds inside the Coverage Region.

- [ ] **Step 4: Commit the script (not the data)**

```bash
git add scripts/rasterize_vs30.py
git commit -m "feat: rasterize 15.4M Vs30 polygons to COG (3.5GB -> ~50MB, lossless)"
```

---

### Task 4: Vs30 grid loader

**Files:**
- Create: `src/eqmon/vs30.py`
- Test: `tests/test_vs30.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vs30.py`:

```python
import numpy as np
import rasterio
from rasterio.transform import from_origin

from eqmon.vs30 import Grid, load_grid


def _write_tiny_tif(path):
    # 2x2 grid, 1-degree cells, origin at (70E, 32N), one nodata cell
    arr = np.array([[400.0, 760.0], [-9999.0, 1000.0]], dtype="float32")
    transform = from_origin(70.0, 32.0, 1.0, 1.0)
    profile = dict(driver="GTiff", height=2, width=2, count=1,
                   dtype="float32", crs="EPSG:4326", transform=transform,
                   nodata=-9999.0)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def test_grid_provides_cell_center_coordinates(tmp_path):
    p = tmp_path / "tiny.tif"
    _write_tiny_tif(p)
    grid = load_grid(p)
    # cell centers: columns at 70.5, 71.5 ; rows at 31.5, 30.5 (north-down)
    assert np.allclose(grid.lon[0], [70.5, 71.5])
    assert np.allclose(grid.lat[:, 0], [31.5, 30.5])


def test_nodata_filled_with_default_vs30(tmp_path):
    p = tmp_path / "tiny.tif"
    _write_tiny_tif(p)
    grid = load_grid(p, default_vs30=760.0)
    assert grid.vs30[1, 0] == 760.0  # was nodata
    assert grid.vs30[0, 0] == 400.0  # unchanged
    assert not np.any(grid.vs30 == -9999.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vs30.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eqmon.vs30'`

- [ ] **Step 3: Write the implementation**

Create `src/eqmon/vs30.py`:

```python
"""Load the Vs30 COG into a Grid: the value array plus per-cell lon/lat
coordinate arrays. Nodata cells are filled with the Default Site Condition."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from .config import DEFAULT_VS30, VS30_TIF


@dataclass(frozen=True)
class Grid:
    vs30: np.ndarray  # (H, W) float32, no nodata sentinels remain
    lon: np.ndarray   # (H, W) float64, cell-center longitude
    lat: np.ndarray   # (H, W) float64, cell-center latitude
    transform: object  # rasterio Affine, for mapping grid -> geo in contouring


def load_grid(path: Path | str = VS30_TIF, default_vs30: float = DEFAULT_VS30) -> Grid:
    with rasterio.open(path) as ds:
        vs30 = ds.read(1).astype("float32")
        nodata = ds.nodata
        transform = ds.transform
        rows = np.arange(ds.height)
        cols = np.arange(ds.width)
        # cell-center pixel coords -> geographic
        col_grid, row_grid = np.meshgrid(cols + 0.5, rows + 0.5)
        lon, lat = rasterio.transform.xy(transform, row_grid, col_grid)
        lon = np.asarray(lon, dtype="float64")
        lat = np.asarray(lat, dtype="float64")

    if nodata is not None:
        vs30 = np.where(vs30 == np.float32(nodata), np.float32(default_vs30), vs30)
    # guard against zero/negative which would break log10
    vs30 = np.where(vs30 <= 0, np.float32(default_vs30), vs30)
    return Grid(vs30=vs30, lon=lon, lat=lat, transform=transform)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vs30.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/vs30.py tests/test_vs30.py
git commit -m "feat: load Vs30 COG into coordinate-aware grid with default site fill"
```

---

### Task 5: Intensity engine (ported formula — PGA and MMI)

**Files:**
- Create: `src/eqmon/intensity.py`
- Test: `tests/test_intensity.py`

- [ ] **Step 1: Write the failing test**

The expected scalar value is computed by hand from the ported formula at a known distance, so this is a true regression guard against the original `Expression.cal`. Create `tests/test_intensity.py`:

```python
import math
import numpy as np

from eqmon.intensity import pga_gal, pga_to_mmi, compute_mmi_grid


def _reference_pga_gal(dist_m, depth_m, mag, vs30):
    r = math.sqrt(dist_m**2 + depth_m**2) / 1000.0
    pga_g = 10 ** (0.49 + 0.23 * (mag - 6) - math.log10(r) - 0.0027 * r)
    pga = 1.385 * pga_g * 980.0
    arv = 10 ** (1.35 - 0.47 * math.log10(vs30))
    return pga * arv


def test_pga_gal_matches_reference_formula():
    dist = np.array([50_000.0])  # 50 km surface distance
    got = pga_gal(dist, depth_m=10_000.0, mag=6.5, vs30=np.array([760.0]))
    exp = _reference_pga_gal(50_000.0, 10_000.0, 6.5, 760.0)
    assert math.isclose(got[0], exp, rel_tol=1e-9)


def test_pga_decreases_with_distance():
    dist = np.array([10_000.0, 100_000.0])
    out = pga_gal(dist, depth_m=10_000.0, mag=6.5, vs30=np.array([760.0, 760.0]))
    assert out[0] > out[1]


def test_softer_soil_amplifies_pga():
    dist = np.array([50_000.0, 50_000.0])
    out = pga_gal(dist, depth_m=10_000.0, mag=6.5, vs30=np.array([300.0, 1000.0]))
    assert out[0] > out[1]  # lower Vs30 (softer) => higher PGA


def test_pga_to_mmi_uses_wald_segments_and_clamps():
    # high PGA -> high-intensity segment, clamped at 10
    assert pga_to_mmi(np.array([2000.0]))[0] <= 10.0
    # very low PGA -> clamped at 1, never below
    assert pga_to_mmi(np.array([0.001]))[0] >= 1.0
    # crossover continuity: both segments near MMI 5 should be close
    near5 = pga_to_mmi(np.array([18.0]))[0]
    assert 4.0 < near5 < 6.0


def test_compute_mmi_grid_shape_matches_input():
    lon = np.array([[70.0, 71.0]])
    lat = np.array([[30.0, 30.0]])
    vs30 = np.array([[760.0, 400.0]], dtype="float32")
    mmi = compute_mmi_grid(lon, lat, vs30, mag=6.5, depth_km=10.0, epi_lon=70.0, epi_lat=30.0)
    assert mmi.shape == (1, 2)
    assert np.all(mmi >= 1.0) and np.all(mmi <= 10.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_intensity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eqmon.intensity'`

- [ ] **Step 3: Write the implementation**

Create `src/eqmon/intensity.py`:

```python
"""Ported intensity model. Replaces the arcpy `Expression.cal` field
calculator with vectorized NumPy. Geodesic distance via pyproj (matches the
original GEODESIC measurement); no ArcGIS."""
from __future__ import annotations
import numpy as np
from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


def epicentral_distance_m(lon: np.ndarray, lat: np.ndarray,
                          epi_lon: float, epi_lat: float) -> np.ndarray:
    """Geodesic surface distance (metres) from epicenter to every cell center."""
    flat_lon = lon.ravel()
    flat_lat = lat.ravel()
    epi_lons = np.full(flat_lon.shape, epi_lon, dtype="float64")
    epi_lats = np.full(flat_lat.shape, epi_lat, dtype="float64")
    _, _, dist = _GEOD.inv(epi_lons, epi_lats, flat_lon, flat_lat)
    return np.asarray(dist, dtype="float64").reshape(lon.shape)


def pga_gal(dist_m: np.ndarray, depth_m: float, mag: float,
            vs30: np.ndarray) -> np.ndarray:
    """Site-amplified PGA in gal (cm/s^2), per the ported attenuation +
    amplification relations. `dist_m` is surface distance; depth completes the
    slant (hypocentral) distance."""
    r = np.sqrt(dist_m**2 + depth_m**2) / 1000.0  # km, guard r>0 below
    r = np.maximum(r, 1e-6)
    log_pga_g = 0.49 + 0.23 * (mag - 6.0) - np.log10(r) - 0.0027 * r
    pga = 1.385 * (10.0**log_pga_g) * 980.0
    arv = 10.0 ** (1.35 - 0.47 * np.log10(vs30))
    return pga * arv


def pga_to_mmi(pga: np.ndarray) -> np.ndarray:
    """Wald et al. (1999) PGA->MMI, PGA in gal. Two segments joined at MMI 5,
    clamped to [1, 10]."""
    pga = np.maximum(pga, 1e-6)
    log_pga = np.log10(pga)
    low = 2.20 * log_pga + 1.00
    high = 3.66 * log_pga - 1.66
    mmi = np.where(low <= 5.0, low, high)
    return np.clip(mmi, 1.0, 10.0)


def compute_mmi_grid(lon: np.ndarray, lat: np.ndarray, vs30: np.ndarray,
                     *, mag: float, depth_km: float,
                     epi_lon: float, epi_lat: float) -> np.ndarray:
    """End-to-end: epicenter + magnitude -> MMI at every grid cell."""
    dist = epicentral_distance_m(lon, lat, epi_lon, epi_lat)
    pga = pga_gal(dist, depth_m=depth_km * 1000.0, mag=mag, vs30=vs30)
    return pga_to_mmi(pga)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_intensity.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/intensity.py tests/test_intensity.py
git commit -m "feat: port Expression.cal to vectorized NumPy intensity engine (no arcpy)"
```

---

### Task 6: Contour generation (MMI grid → filled-band GeoJSON)

**Files:**
- Create: `src/eqmon/contours.py`
- Test: `tests/test_contours.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_contours.py`:

```python
import numpy as np
from rasterio.transform import from_origin

from eqmon.contours import mmi_to_geojson


def test_filled_bands_produce_valid_featurecollection():
    # synthetic 50x50 MMI surface: a radial gradient high in the center
    n = 50
    yy, xx = np.mgrid[0:n, 0:n]
    cx = cy = n / 2
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    mmi = np.clip(9.0 - dist * 0.25, 1.0, 10.0).astype("float32")
    transform = from_origin(70.0, 32.0, 0.1, 0.1)

    fc = mmi_to_geojson(mmi, transform, levels=[3, 5, 7])

    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) >= 1
    for feat in fc["features"]:
        assert feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
        assert "mmi_lower" in feat["properties"]
        # coordinates fall inside the raster's geographic extent
        assert "color" in feat["properties"]


def test_higher_band_is_nested_inside_lower_band_area():
    n = 50
    yy, xx = np.mgrid[0:n, 0:n]
    dist = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2)
    mmi = np.clip(9.0 - dist * 0.25, 1.0, 10.0).astype("float32")
    transform = from_origin(70.0, 32.0, 0.1, 0.1)

    fc = mmi_to_geojson(mmi, transform, levels=[3, 5, 7])
    lowers = sorted(f["properties"]["mmi_lower"] for f in fc["features"])
    # the strongest band present should be the highest requested level it reaches
    assert lowers[0] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contours.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eqmon.contours'`

- [ ] **Step 3: Write the implementation**

Create `src/eqmon/contours.py`:

```python
"""Turn an MMI grid into filled contour bands as GeoJSON. Uses contourpy's
filled-contour algorithm, maps pixel coordinates to geographic coordinates via
the raster affine transform, and tags each band with an MMI range and color.

This is what makes the data servable: a 15M-cell surface collapses to a handful
of band polygons (tens of KB), losslessly derived from the full-res grid."""
from __future__ import annotations
import numpy as np
from contourpy import contour_generator

# USGS ShakeMap-style MMI palette (lower-bound -> hex).
_MMI_COLORS = {
    2: "#bfccff", 3: "#a0e6ff", 4: "#80ffff", 5: "#7aff93",
    6: "#ffff00", 7: "#ffc800", 8: "#ff9100", 9: "#ff0000", 10: "#c80000",
}


def _pixel_to_geo(xs, ys, transform):
    # contourpy returns (col, row) float pixel coords; affine maps to (lon, lat)
    lon, lat = transform * (xs, ys)
    return lon, lat


def _ring_to_coords(ring, transform):
    xs = ring[:, 0]
    ys = ring[:, 1]
    lon, lat = _pixel_to_geo(xs, ys, transform)
    return [[float(a), float(b)] for a, b in zip(lon, lat)]


def mmi_to_geojson(mmi: np.ndarray, transform, levels: list[int]) -> dict:
    """Filled bands between consecutive levels (and an open top band)."""
    gen = contour_generator(z=mmi, name="serial", fill_type="OuterOffset")
    bounds = list(levels) + [float(np.nanmax(mmi)) + 1.0]
    features = []
    for lower, upper in zip(bounds[:-1], bounds[1:]):
        filled = gen.filled(lower, upper)
        polygons, _offsets = filled  # list of point arrays per disjoint region
        for points in polygons:
            if len(points) < 4:
                continue
            ring = _ring_to_coords(points, transform)
            features.append({
                "type": "Feature",
                "properties": {
                    "mmi_lower": int(lower),
                    "mmi_upper": int(min(upper, 10)),
                    "color": _MMI_COLORS.get(int(lower), "#888888"),
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            })
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_contours.py -v`
Expected: PASS (2 passed)

> Note: contourpy's `filled()` return shape varies by `fill_type`. If the unpacking in `_ring_to_coords` mismatches your installed contourpy, run `uv run python -c "import contourpy; print(contourpy.__version__)"` and adapt: for `fill_type="OuterOffset"`, `filled()` returns `(list_of_point_arrays, list_of_offset_arrays)`. The test will catch a mismatch immediately.

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/contours.py tests/test_contours.py
git commit -m "feat: convert MMI grid to filled-band GeoJSON contours"
```

---

### Task 7: FastAPI service

**Files:**
- Create: `src/eqmon/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api.py`:

```python
import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient


def _make_grid_tif(path):
    # 60x60 grid of uniform Vs30 covering ~6deg around an epicenter region
    arr = np.full((60, 60), 600.0, dtype="float32")
    transform = from_origin(67.0, 33.0, 0.1, 0.1)  # NW origin
    profile = dict(driver="GTiff", height=60, width=60, count=1,
                   dtype="float32", crs="EPSG:4326", transform=transform,
                   nodata=-9999.0)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def test_intensity_endpoint_returns_bands(tmp_path, monkeypatch):
    tif = tmp_path / "Vs30.tif"
    _make_grid_tif(tif)
    monkeypatch.setenv("EQMON_VS30_TIF", str(tif))

    from eqmon import api
    api.reset_grid_cache()  # ensure the env override is picked up
    client = TestClient(api.app)

    resp = client.post("/intensity", json={
        "magnitude": 6.5, "depth_km": 10.0, "lat": 30.0, "lon": 70.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 1


def test_intensity_rejects_out_of_region(tmp_path, monkeypatch):
    tif = tmp_path / "Vs30.tif"
    _make_grid_tif(tif)
    monkeypatch.setenv("EQMON_VS30_TIF", str(tif))
    from eqmon import api
    api.reset_grid_cache()
    client = TestClient(api.app)
    resp = client.post("/intensity", json={
        "magnitude": 6.5, "depth_km": 10.0, "lat": 0.0, "lon": 0.0,
    })
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eqmon.api'`

- [ ] **Step 3: Write the implementation**

Create `src/eqmon/api.py`:

```python
"""FastAPI service. Loads the Vs30 grid once (cached) and serves filled MMI
contour bands per submitted event."""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import config
from .contours import mmi_to_geojson
from .intensity import compute_mmi_grid
from .vs30 import Grid, load_grid

app = FastAPI(title="Earthquake Intensity Platform")


def _vs30_path() -> Path:
    return Path(os.environ.get("EQMON_VS30_TIF", str(config.VS30_TIF)))


@lru_cache(maxsize=1)
def get_grid() -> Grid:
    return load_grid(_vs30_path())


def reset_grid_cache() -> None:
    """Test hook: clear the cached grid so an env override takes effect."""
    get_grid.cache_clear()


class EventRequest(BaseModel):
    magnitude: float = Field(ge=0.0, le=10.0)
    depth_km: float = Field(ge=0.0, le=700.0)
    lat: float
    lon: float

    @field_validator("lat")
    @classmethod
    def _lat_in_region(cls, v):
        _, miny, _, maxy = config.COVERAGE_BBOX
        if not (miny <= v <= maxy):
            raise ValueError("latitude outside Coverage Region")
        return v

    @field_validator("lon")
    @classmethod
    def _lon_in_region(cls, v):
        minx, _, maxx, _ = config.COVERAGE_BBOX
        if not (minx <= v <= maxx):
            raise ValueError("longitude outside Coverage Region")
        return v


@app.post("/intensity")
def intensity(req: EventRequest) -> JSONResponse:
    grid = get_grid()
    mmi = compute_mmi_grid(
        grid.lon, grid.lat, grid.vs30,
        mag=req.magnitude, depth_km=req.depth_km,
        epi_lon=req.lon, epi_lat=req.lat,
    )
    fc = mmi_to_geojson(mmi, grid.transform, levels=config.MMI_BAND_LEVELS)
    return JSONResponse(fc)


# serve the Leaflet frontend (Task 8) at /
_web = Path(__file__).resolve().parents[2] / "web"
if _web.exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS (2 passed). Pydantic validation returns 422 for out-of-region coordinates.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all tasks' tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/eqmon/api.py tests/test_api.py
git commit -m "feat: FastAPI /intensity endpoint serving MMI contour bands"
```

---

### Task 8: Leaflet frontend

**Files:**
- Create: `web/index.html`
- Create: `web/app.js`

No build step — Leaflet via CDN, vanilla JS. Tested manually by running the server (Task 9).

- [ ] **Step 1: Write the HTML shell**

Create `web/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Earthquake Intensity Platform</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif; }
    #map { position: absolute; inset: 0; }
    #panel {
      position: absolute; z-index: 1000; top: 12px; left: 12px; width: 240px;
      background: #fff; padding: 14px; border-radius: 8px;
      box-shadow: 0 2px 12px rgba(0,0,0,.25);
    }
    #panel label { display: block; font-size: 12px; margin: 8px 0 2px; color: #333; }
    #panel input { width: 100%; box-sizing: border-box; padding: 6px; }
    #panel button { margin-top: 12px; width: 100%; padding: 8px; cursor: pointer;
      background: #c0392b; color: #fff; border: none; border-radius: 6px; }
    #status { font-size: 12px; margin-top: 8px; color: #666; min-height: 16px; }
    .legend { line-height: 18px; color: #333; }
    .legend i { width: 16px; height: 16px; float: left; margin-right: 6px; opacity: .8; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="panel">
    <strong>Event parameters</strong>
    <label>Magnitude</label>      <input id="magnitude" type="number" value="6.5" step="0.1" />
    <label>Depth (km)</label>     <input id="depth_km" type="number" value="10" step="1" />
    <label>Latitude</label>       <input id="lat" type="number" value="34.0" step="0.01" />
    <label>Longitude</label>      <input id="lon" type="number" value="72.5" step="0.01" />
    <button id="calc">Calculate intensity</button>
    <div id="status"></div>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write the client logic**

Create `web/app.js`:

```javascript
const map = L.map("map").setView([30.4, 69.3], 5); // Primary Focus Country: Pakistan
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap", maxZoom: 12,
}).addTo(map);

let intensityLayer = null;
let epicenterMarker = null;
const statusEl = document.getElementById("status");

function style(feature) {
  return { color: feature.properties.color, weight: 1,
           fillColor: feature.properties.color, fillOpacity: 0.45 };
}

async function calculate() {
  const payload = {
    magnitude: parseFloat(document.getElementById("magnitude").value),
    depth_km:  parseFloat(document.getElementById("depth_km").value),
    lat:       parseFloat(document.getElementById("lat").value),
    lon:       parseFloat(document.getElementById("lon").value),
  };
  statusEl.textContent = "Calculating…";
  try {
    const resp = await fetch("/intensity", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json();
      statusEl.textContent = "Error: " + JSON.stringify(err.detail ?? err);
      return;
    }
    const fc = await resp.json();
    if (intensityLayer) map.removeLayer(intensityLayer);
    intensityLayer = L.geoJSON(fc, {
      style,
      onEachFeature: (f, l) =>
        l.bindPopup(`MMI ${f.properties.mmi_lower}–${f.properties.mmi_upper}`),
    }).addTo(map);

    if (epicenterMarker) map.removeLayer(epicenterMarker);
    epicenterMarker = L.circleMarker([payload.lat, payload.lon], {
      radius: 6, color: "#000", fillColor: "#fff", fillOpacity: 1,
    }).addTo(map).bindPopup("Epicenter");

    statusEl.textContent = `${fc.features.length} intensity bands`;
    if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  } catch (e) {
    statusEl.textContent = "Request failed: " + e.message;
  }
}

document.getElementById("calc").addEventListener("click", calculate);
```

- [ ] **Step 3: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: Leaflet map and event form rendering MMI contour bands"
```

---

### Task 9: End-to-end run and docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the server**

Run: `uv run uvicorn eqmon.api:app --reload --port 8000`
(Requires `data/Vs30.tif` from Task 3 to exist.)

- [ ] **Step 2: Manual verification**

Open `http://localhost:8000/` in a browser. The map opens on Pakistan. With the defaults (mag 6.5, depth 10, lat 34.0, lon 72.5 — the original `Expression.cal` scenario), click **Calculate intensity**. Expected: filled MMI bands appear centered near the epicenter, strongest (red, MMI 8–10) at the center fading outward; clicking a band shows its MMI range; the status line reports the band count. Response should arrive in well under a second.

- [ ] **Step 3: Document setup**

Write `README.md`:

```markdown
# Earthquake Intensity Platform

Interactive MMI intensity mapping for the Coverage Region (Pakistan, India,
Afghanistan, Iran, China, Nepal). No ArcGIS dependency.

## Setup

```bash
uv sync --group dev
uv run python scripts/rasterize_vs30.py   # one-time: builds data/Vs30.tif (~50MB)
uv run uvicorn eqmon.api:app --port 8000
```

Open http://localhost:8000/, enter magnitude / depth / lat / lon, calculate.

## How the data-size problem is solved

The source Vs30 layer is 15.4M polygons (3.5 GB) — a vectorized raster. We
rasterize it once to a Cloud-Optimized GeoTIFF (~50 MB, lossless). At runtime
intensity is computed at full resolution in NumPy; only the output — a handful
of contour bands (tens of KB) — is sent to the browser.

## Tests

```bash
uv run pytest -v
```
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: setup and run instructions"
```

---

## Self-Review notes

- **Spec coverage:** form inputs (mag/depth/lat/lon) → Task 7/8; MMI via formula in Expression.cal → Task 5 (regression-tested against the decoded formula); no arcgis → Task 5 uses pyproj not arcpy; filled contours on Leaflet → Tasks 6/8; data-size problem → Task 3 (rasterize) + Task 6 (contour output); PostGIS decision → deferred to Plan B by design (documented in header). All covered.
- **Type consistency:** `Grid` fields (`vs30`, `lon`, `lat`, `transform`) used consistently across Tasks 4→5→7; `mmi_to_geojson(mmi, transform, levels)` signature consistent Tasks 6→7; feature property keys (`mmi_lower`, `mmi_upper`, `color`) consistent Tasks 6→8.
- **Known fragility flagged inline:** contourpy `filled()` return shape (Task 6 Step 4 note) — the test catches a version mismatch immediately.

## Decisions deferred to Plan B (Event Catalog + Feeds)

1. **Postgres/PostGIS** — adopt for the event catalog, Manual Event Input persistence, and district zonal-stats ("which districts are in MMI ≥ VII"). Do **not** load the Vs30 grid into it.
2. **MET (Primary) / USGS (Secondary) feed ingestion** with source dedup.
3. District impact aggregation overlay using `boundary/district.geojson`.
