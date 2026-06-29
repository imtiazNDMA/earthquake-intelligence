# MMI Legend Enlargement & Shapefile Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enlarge the MMI map legend and let users export user-selected MMI intensity bands as a zipped Esri Shapefile.

**Architecture:** A new stateless backend helper converts a GeoJSON FeatureCollection of MMI band polygons into an in-memory zipped shapefile via `fiona`/`shapely`; a thin `POST /intensity/export/shapefile` FastAPI endpoint wraps it. The frontend retains the last `/intensity` FeatureCollection, turns the (enlarged) legend into the band-selection surface with per-band checkboxes and an export button, and downloads the zip via a blob anchor.

**Tech Stack:** FastAPI, Pydantic, `fiona`, `shapely`, `zipfile`/`tempfile` (Python); vanilla JS + Leaflet + CSS (frontend); `pytest` + `fastapi.testclient` (tests).

## Global Constraints

- No new dependencies — `fiona`, `shapely`, `pyproj` are already in `pyproject.toml`.
- Shapefile CRS is **EPSG:4326** (WGS84); the `.prj` must be written.
- Backend changes are TDD (write failing test first). Frontend (JS/CSS) has no JS
  test harness in this repo — verify in the browser with the running app.
- MMI band feature properties are `mmi_lower` (int), `mmi_upper` (int),
  `color` (hex string). Band geometries are `Polygon` or `MultiPolygon`.
- Mirror the existing export pattern in `src/eqmon/api.py:250` (`Response` +
  `Content-Disposition` attachment header).
- Tests instantiate the app with `TestClient(api.app)` **without** a `with`
  block, so lifespan/DB/grid startup does not run.

## File Structure

- Create `src/eqmon/export.py` — `featurecollection_to_shapefile_zip(fc) -> bytes`.
- Modify `src/eqmon/api.py` — new request model + `POST /intensity/export/shapefile`.
- Create `tests/test_shapefile_export.py` — helper unit tests + endpoint tests.
- Modify `web/styles.css` — enlarge legend; style checkboxes + export button.
- Modify `web/app.js` — retain `_lastFc`, data-driven `renderLegend`, checkboxes,
  export button, `exportShapefile()`.

---

### Task 1: Backend shapefile helper (`src/eqmon/export.py`)

**Files:**
- Create: `src/eqmon/export.py`
- Test: `tests/test_shapefile_export.py`

**Interfaces:**
- Consumes: nothing (pure function over a GeoJSON dict).
- Produces: `featurecollection_to_shapefile_zip(fc: dict) -> bytes` — returns the
  bytes of a zip archive containing `mmi_bands.shp/.shx/.dbf/.prj` (+ `.cpg`).
  Raises `ValueError` if no polygonal features are present.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_shapefile_export.py`:

```python
import io
import zipfile

import fiona
import pytest

from eqmon.export import featurecollection_to_shapefile_zip


def _polygon_feature(mmi_low, mmi_high, color, x0=70.0, y0=30.0):
    ring = [[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]
    return {
        "type": "Feature",
        "properties": {"mmi_lower": mmi_low, "mmi_upper": mmi_high, "color": color},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def test_zip_contains_all_shapefile_sidecars():
    data = featurecollection_to_shapefile_zip(
        _fc([_polygon_feature(6, 7, "#ffff00"), _polygon_feature(7, 8, "#ffc800", 71.0, 31.0)])
    )
    assert isinstance(data, bytes) and len(data) > 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        assert any(n.endswith(ext) for n in names), f"missing {ext} in {names}"


def test_roundtrip_preserves_attributes_geometry_and_crs(tmp_path):
    data = featurecollection_to_shapefile_zip(
        _fc([_polygon_feature(6, 7, "#ffff00"), _polygon_feature(7, 8, "#ffc800", 71.0, 31.0)])
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(tmp_path)
    shp = next(tmp_path.glob("*.shp"))
    with fiona.open(str(shp)) as src:
        assert src.crs.to_epsg() == 4326
        recs = list(src)
    assert len(recs) == 2
    props = {r["properties"]["mmi_low"]: r["properties"] for r in recs}
    assert props[6]["mmi_high"] == 7 and props[6]["color"] == "#ffff00"
    for r in recs:
        assert r["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_empty_featurecollection_raises():
    with pytest.raises(ValueError):
        featurecollection_to_shapefile_zip(_fc([]))


def test_non_polygon_features_are_skipped():
    point = {
        "type": "Feature",
        "properties": {"mmi_lower": 5, "mmi_upper": 6, "color": "#7aff93"},
        "geometry": {"type": "Point", "coordinates": [70.0, 30.0]},
    }
    data = featurecollection_to_shapefile_zip(_fc([point, _polygon_feature(6, 7, "#ffff00")]))
    with zipfile.ZipFile(io.BytesIO(data)) as zf, \
         zf.open(next(n for n in zf.namelist() if n.endswith(".shp"))):
        pass  # zip is valid
    # exactly one polygon survived
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(td)
        shp = next(p for p in os.listdir(td) if p.endswith(".shp"))
        with fiona.open(os.path.join(td, shp)) as src:
            assert len(list(src)) == 1


def test_all_points_raises():
    point = {
        "type": "Feature",
        "properties": {"mmi_lower": 5, "mmi_upper": 6, "color": "#7aff93"},
        "geometry": {"type": "Point", "coordinates": [70.0, 30.0]},
    }
    with pytest.raises(ValueError):
        featurecollection_to_shapefile_zip(_fc([point]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_shapefile_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eqmon.export'`.

- [ ] **Step 3: Write the helper**

Create `src/eqmon/export.py`:

```python
"""Convert a GeoJSON FeatureCollection of MMI band polygons into a zipped
Esri Shapefile (WGS84). Stateless and HTTP-agnostic so it can be unit-tested
without the API layer."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import fiona
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

_SCHEMA = {
    "geometry": "MultiPolygon",
    "properties": {"mmi_low": "int", "mmi_high": "int", "color": "str"},
}
_LAYER = "mmi_bands"


def featurecollection_to_shapefile_zip(fc: dict) -> bytes:
    """Return zip bytes containing mmi_bands.{shp,shx,dbf,prj,cpg}.

    Non-polygon features are skipped. Raises ValueError if nothing writable
    remains.
    """
    records = []
    for feat in (fc or {}).get("features", []) or []:
        geom_obj = (feat or {}).get("geometry")
        if not geom_obj or geom_obj.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = shape(geom_obj)
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        elif not isinstance(geom, MultiPolygon):
            continue
        props = (feat.get("properties") or {})
        records.append({
            "geometry": mapping(geom),
            "properties": {
                "mmi_low": props.get("mmi_lower"),
                "mmi_high": props.get("mmi_upper"),
                "color": props.get("color"),
            },
        })

    if not records:
        raise ValueError("no polygonal features to export")

    with TemporaryDirectory() as td:
        shp_path = Path(td) / f"{_LAYER}.shp"
        with fiona.open(
            str(shp_path), "w", driver="ESRI Shapefile",
            schema=_SCHEMA, crs="EPSG:4326", encoding="utf-8",
        ) as dst:
            dst.writerecords(records)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for part in sorted(Path(td).glob(f"{_LAYER}.*")):
                zf.write(part, arcname=part.name)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_shapefile_export.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/eqmon/export.py tests/test_shapefile_export.py
git commit -m "feat(export): FeatureCollection -> zipped shapefile helper"
```

---

### Task 2: Backend endpoint (`POST /intensity/export/shapefile`)

**Files:**
- Modify: `src/eqmon/api.py` (add import near line 20; add model + route after the
  `/intensity` route, around line 157)
- Test: `tests/test_shapefile_export.py` (append endpoint tests)

**Interfaces:**
- Consumes: `featurecollection_to_shapefile_zip` from Task 1.
- Produces: `POST /intensity/export/shapefile` — JSON body `{type, features}`;
  returns `application/zip` with `Content-Disposition: attachment;
  filename=mmi_bands.shp.zip`. Returns 400 for empty/invalid input.

- [ ] **Step 1: Write the failing endpoint tests**

Append to `tests/test_shapefile_export.py`:

```python
from fastapi.testclient import TestClient


def test_endpoint_returns_zip():
    from eqmon import api
    client = TestClient(api.app)
    resp = client.post("/intensity/export/shapefile", json=_fc([
        _polygon_feature(6, 7, "#ffff00"), _polygon_feature(7, 8, "#ffc800", 71.0, 31.0),
    ]))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "mmi_bands.shp.zip" in resp.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert any(n.endswith(".shp") for n in zf.namelist())


def test_endpoint_rejects_empty():
    from eqmon import api
    client = TestClient(api.app)
    resp = client.post("/intensity/export/shapefile", json=_fc([]))
    assert resp.status_code == 400


def test_endpoint_rejects_wrong_type():
    from eqmon import api
    client = TestClient(api.app)
    resp = client.post("/intensity/export/shapefile",
                       json={"type": "Nonsense", "features": [_polygon_feature(6, 7, "#ffff00")]})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_shapefile_export.py -k endpoint -v`
Expected: FAIL — 404 Not Found (route does not exist yet).

- [ ] **Step 3: Add the import**

In `src/eqmon/api.py`, modify the contours import line (currently line 20
`from .contours import mmi_to_geojson`) to also import the new helper. Add a new
line directly after it:

```python
from .contours import mmi_to_geojson
from .export import featurecollection_to_shapefile_zip
```

- [ ] **Step 4: Add the request model and route**

In `src/eqmon/api.py`, immediately after the `/intensity` endpoint (ends around
line 157, before the next route), add:

```python
class FeatureCollectionIn(BaseModel):
    type: str
    features: list[dict]


@app.post("/intensity/export/shapefile")
def export_intensity_shapefile(fc: FeatureCollectionIn):
    if fc.type != "FeatureCollection" or not fc.features:
        raise HTTPException(status_code=400, detail="expected a non-empty FeatureCollection")
    try:
        data = featurecollection_to_shapefile_zip(fc.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=mmi_bands.shp.zip"},
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_shapefile_export.py -v`
Expected: PASS (8 passed).

- [ ] **Step 6: Run the full backend suite (no regressions)**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/eqmon/api.py tests/test_shapefile_export.py
git commit -m "feat(api): POST /intensity/export/shapefile endpoint"
```

---

### Task 3: Enlarge the MMI legend (CSS)

**Files:**
- Modify: `web/styles.css:301-320`

**Interfaces:**
- Consumes: existing `.legend*` markup produced by `web/app.js`.
- Produces: larger legend; no class names added or removed (Feature 4 reuses them).

- [ ] **Step 1: Enlarge the legend selectors**

In `web/styles.css`, replace the block at lines 301–320 with:

```css
.legend {
  background: var(--surface); padding: 12px 14px; border-radius: var(--r-lg);
  box-shadow: var(--shadow-md); min-width: 64px;
}
.legend-title { font-weight: 700; font-size: 16px; margin-bottom: 7px; color: var(--slate); }
.legend-item {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 6px; border-radius: var(--r-sm);
  cursor: default; transition: all .15s var(--ease);
}
.legend-item.active {
  transform: scale(1.18);
  box-shadow: var(--shadow-md);
  background: rgba(15,76,129,.06);
}
.legend-swatch {
  display: inline-block; width: 34px; height: 24px;
  border-radius: 3px; border: 1px solid rgba(0,0,0,.1); flex: none;
}
.legend-label { font-family: var(--font-mono); font-size: 15px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }
```

- [ ] **Step 2: Verify visually**

Start the app (`uvicorn eqmon.api:app --reload` or `start.bat`), open the map,
run a calculation, and confirm the lower-right MMI legend is visibly larger and
still readable. Hovering a legend row still highlights the matching band.

- [ ] **Step 3: Commit**

```bash
git add web/styles.css
git commit -m "feat(ui): enlarge MMI legend for readability"
```

---

### Task 4: Frontend band selection + shapefile export

**Files:**
- Modify: `web/app.js` (legend block lines 362-412; `calculate()` lines 429-467;
  state declarations near lines 368-369)
- Modify: `web/styles.css` (append checkbox + export-button styles)

**Interfaces:**
- Consumes: `POST /intensity/export/shapefile` (Task 2); `_lastFc` FeatureCollection
  retained from `/intensity`; `toast()` helper already in `app.js`.
- Produces: data-driven `renderLegend(fc)`, `exportShapefile()`, `_lastFc`,
  `_legendCheckboxes` — used only within `app.js`.

- [ ] **Step 1: Add export-button + checkbox CSS**

Append to `web/styles.css`:

```css
.legend-cb { width: 16px; height: 16px; margin: 0; flex: none; cursor: pointer; accent-color: var(--brand); }
.legend-export {
  margin-top: 8px; width: 100%; padding: 6px 8px;
  font-size: var(--fs-xs); font-weight: 600; font-family: inherit;
  border: 1px solid var(--brand); border-radius: var(--r-sm);
  background: var(--brand); color: #fff; cursor: pointer;
}
.legend-export:disabled { opacity: .5; cursor: not-allowed; }
.legend-export:hover:not(:disabled) { filter: brightness(1.08); }
```

- [ ] **Step 2: Add state declarations**

In `web/app.js`, replace lines 368-369:

```javascript
let _legendItems = {};
let _mmiLayers = {};
```

with:

```javascript
let _legendItems = {};
let _mmiLayers = {};
let _lastFc = null;
let _legendDiv = null;
const _legendCheckboxes = {};
```

- [ ] **Step 3: Replace the legend control + add renderLegend / export**

In `web/app.js`, replace the legend control block (lines 388-403, from
`const legend = L.control(...)` through `legend.addTo(map);`) with:

```javascript
function presentLevels(fc) {
  const set = new Set((fc && fc.features ? fc.features : []).map(f => f.properties.mmi_lower));
  return MMI_PALETTE.map(([m]) => m).filter(m => set.has(m));
}

function updateExportEnabled() {
  const btn = _legendDiv && _legendDiv.querySelector("#legend-export");
  if (!btn) return;
  const anyChecked = Object.values(_legendCheckboxes).some(cb => cb.checked);
  btn.disabled = !(_lastFc && anyChecked);
}

function renderLegend(fc) {
  if (!_legendDiv) return;
  _legendItems = {};
  Object.keys(_legendCheckboxes).forEach(k => delete _legendCheckboxes[k]);
  const colorOf = Object.fromEntries(MMI_PALETTE);
  const hasData = !!(fc && fc.features && fc.features.length);
  const levels = hasData ? presentLevels(fc) : MMI_PALETTE.map(([m]) => m);

  let html = "<div class='legend-title'>MMI</div>";
  levels.forEach(m => {
    const cb = hasData
      ? `<input type="checkbox" class="legend-cb" data-level="${m}" checked aria-label="Include MMI ${m} in export">`
      : "";
    html += `<div class="legend-item" data-level="${m}">${cb}` +
      `<span class="legend-swatch" style="background:${colorOf[m]}"></span>` +
      `<span class="legend-label">${m}</span></div>`;
  });
  html += `<button type="button" id="legend-export" class="legend-export"${hasData ? "" : " disabled"}>⬇ Export shapefile</button>`;
  _legendDiv.innerHTML = html;

  _legendDiv.querySelectorAll(".legend-item").forEach(el => {
    const level = parseInt(el.dataset.level);
    el.addEventListener("mouseenter", () => highlightByLevel(level));
    el.addEventListener("mouseleave", () => unhighlightAll());
    _legendItems[level] = el;
  });
  _legendDiv.querySelectorAll(".legend-cb").forEach(cb => {
    _legendCheckboxes[parseInt(cb.dataset.level)] = cb;
    cb.addEventListener("change", updateExportEnabled);
  });
  const btn = _legendDiv.querySelector("#legend-export");
  if (btn) btn.addEventListener("click", exportShapefile);
  updateExportEnabled();
}

async function exportShapefile() {
  if (!_lastFc) return;
  const levels = new Set(
    Object.values(_legendCheckboxes).filter(cb => cb.checked).map(cb => parseInt(cb.dataset.level))
  );
  const features = _lastFc.features.filter(f => levels.has(f.properties.mmi_lower));
  if (!features.length) { toast("Select at least one MMI band to export", "error"); return; }
  toast(`Exporting ${features.length} band(s) as shapefile…`, "info");
  try {
    const resp = await fetch("/intensity/export/shapefile", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "FeatureCollection", features }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      toast("Export failed: " + JSON.stringify(err.detail ?? err), "error");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "mmi_bands.shp.zip";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast("Export request failed: " + e.message, "error");
  }
}

const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  _legendDiv = div;
  L.DomEvent.disableClickPropagation(div);
  L.DomEvent.disableScrollPropagation(div);
  renderLegend(null);
  return div;
};
legend.addTo(map);
```

- [ ] **Step 4: Retain `_lastFc` and refresh the legend on calc**

In `web/app.js` `calculate()`, find (around line 448-454):

```javascript
    const fc = await resp.json();
    _mmiLayers = {};
    if (intensityLayer) map.removeLayer(intensityLayer);
    intensityLayer = L.geoJSON(fc, {
      style,
      onEachFeature: onMmiFeature,
    }).addTo(map);
```

and insert two lines so it reads:

```javascript
    const fc = await resp.json();
    _mmiLayers = {};
    _lastFc = fc;
    if (intensityLayer) map.removeLayer(intensityLayer);
    intensityLayer = L.geoJSON(fc, {
      style,
      onEachFeature: onMmiFeature,
    }).addTo(map);
    renderLegend(fc);
```

- [ ] **Step 5: Verify in the browser**

Start the app, open the map.
1. Before any calc: legend shows all MMI swatches; the "⬇ Export shapefile"
   button is present and **disabled**.
2. Run a calculation: legend now lists only the bands present, each with a
   **checked** checkbox; export button is **enabled**.
3. Untick all checkboxes → button disables again. Tick one → it re-enables.
4. Hovering a legend row still highlights the matching band on the map; clicking
   a checkbox does not pan/zoom the map.
5. With a subset ticked, click Export → a `mmi_bands.shp.zip` downloads. Unzip and
   confirm `.shp/.shx/.dbf/.prj` are present and it opens in GIS (QGIS) at the
   correct location with `mmi_low`/`mmi_high`/`color` attributes.

- [ ] **Step 6: Commit**

```bash
git add web/app.js web/styles.css
git commit -m "feat(ui): select MMI bands in legend and export as shapefile"
```

---

## Self-Review

**Spec coverage:**
- Feature 1 (larger legend) → Task 3. ✓
- Feature 2 backend helper → Task 1; endpoint → Task 2. ✓
- In-legend selection UI, all-present-bands-checked default → Task 4 Step 3. ✓
- `_lastFc` retention → Task 4 Step 4. ✓
- Blob-anchor download (POST body can't use `window.open`) → Task 4 Step 3. ✓
- EPSG:4326 + `.prj`, zipped sidecars → Task 1. ✓
- Error handling: empty/invalid → 400 (Task 2); non-polygon skip, all-points →
  `ValueError`/400 (Task 1). ✓
- Tests: round-trip, empty rejection, non-polygon skip, helper unit test → Task 1;
  endpoint zip + 400 → Task 2. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**Type consistency:** `featurecollection_to_shapefile_zip(fc: dict) -> bytes`,
`FeatureCollectionIn{type, features}`, `renderLegend(fc)`, `exportShapefile()`,
`_lastFc`, `_legendCheckboxes`, `updateExportEnabled()`, `presentLevels(fc)` are
named identically across the tasks that define and use them. Property mapping
`mmi_lower→mmi_low`, `mmi_upper→mmi_high` is consistent between helper, tests, and
round-trip assertions. ✓
