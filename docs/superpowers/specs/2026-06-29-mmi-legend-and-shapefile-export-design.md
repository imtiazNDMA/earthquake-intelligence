# MMI Legend Enlargement & Shapefile Export — Design

**Date:** 2026-06-29
**Status:** Approved for planning
**Scope:** Frontend (`web/`) + Backend (`src/eqmon/api.py`) + tests

## Problem

Two user-facing gaps on the intensity map:

1. The MMI legend (lower-right) is small and hard to read against a busy satellite basemap.
2. There is no way to export the rendered MMI intensity polygons. The existing
   `/events/export` endpoint only exports the event *catalog* (points), not the
   intensity *bands*. Users need the selected MMI band polygons as a GIS-ready
   shapefile.

## Goals

- Make the MMI legend visibly larger and more legible without changing its
  hover-highlight behavior.
- Let the user pick which MMI bands to export, then download them as a single
  zipped Esri Shapefile (`.shp/.shx/.dbf/.prj/.cpg`) in WGS84.

## Non-Goals

- No change to how MMI bands are computed or rendered.
- No export of other layers (boundaries, faults) — MMI bands only.
- No server-side persistence of exports; generation is on-demand and stateless.
- No new geo dependency — `fiona`, `shapely`, `pyproj` are already in `pyproject.toml`.

## Current State (verified)

- **Legend** is a JS-generated Leaflet control: `web/app.js:388–403`. Styled by
  `.legend`, `.legend-title`, `.legend-item`, `.legend-swatch`, `.legend-label`
  in `web/styles.css:301–320`. Items carry `data-level` and drive
  `highlightByLevel()` / `unhighlightAll()` on hover.
- **MMI bands** come from `POST /intensity`, returning a GeoJSON
  `FeatureCollection`. Each feature has properties `mmi_lower` (int),
  `mmi_upper` (int), `color` (hex) and a `Polygon` geometry
  (`src/eqmon/contours.py:36–109`).
- In `calculate()` (`web/app.js:429–467`) the `fc` is a **local** variable; it is
  rendered then discarded. Layers are grouped by level into `_mmiLayers`.
- **Export pattern** to mirror: `GET /events/export` (`src/eqmon/api.py:250–302`)
  builds bytes and returns a `Response` with a `Content-Disposition` attachment
  header.

## Feature 1 — Larger MMI Legend

CSS-only change in `web/styles.css`. No JS edits.

| Selector | Current | New |
| :-- | :-- | :-- |
| `.legend-swatch` | `24×18` | `34×24` |
| `.legend-label` | `13px` | `15px` |
| `.legend-title` | base | one step larger, more bottom margin |
| `.legend` padding | `10px 12px` | `12px 14px` |
| `.legend-item` gap/padding | `6px` / `2px 4px` | `8px` / `3px 6px` |

Hover-highlight is keyed off `data-level`, not sizes, so it is unaffected. The
`.legend-item.active` scale transform stays as-is.

## Feature 2 — Export Selected MMI Bands as a Zipped Shapefile

### UX

The enlarged legend doubles as the selection surface (decided: in-legend, not a
separate menu):

- Each band row gains a checkbox. When a new `/intensity` result loads, **all
  present bands start checked** (decided default).
- A footer row in the legend holds an **"⬇ Export shapefile"** button.
- The button is **disabled until a calc has run** (i.e. `_lastFc` exists). If the
  user unchecks every band, the button disables again.
- Only MMI levels actually present in the current result render rows; absent
  levels are omitted (legend becomes data-driven instead of always showing 2–10).

### Frontend changes (`web/app.js`)

1. Promote the rendered FeatureCollection to a module-level `_lastFc` inside
   `calculate()`.
2. Rebuild the legend from the levels present in `_lastFc` after each calc (a
   `renderLegend(fc)` function), instead of the current static build from
   `MMI_PALETTE`. `MMI_PALETTE` stays as the color/order source of truth; only
   levels present in `fc` are shown, each with a checkbox (checked) + swatch +
   label. Empty state (no calc yet) shows the full static palette with the export
   button disabled, preserving today's at-a-glance look.
3. `exportShapefile()`:
   - Read checked `mmi_lower` levels from the legend.
   - Filter `_lastFc.features` to those levels into a new FeatureCollection.
   - `POST` it as JSON to `/intensity/export/shapefile`.
   - Read the response as a `Blob`, create an object URL, and trigger a download
     via a temporary `<a download>` element (a POST body cannot be downloaded via
     `window.open`, so the blob-anchor pattern is required here rather than the
     catalog's `window.open` approach).
   - Toast on start and on failure; revoke the object URL after click.

### Backend changes (`src/eqmon/api.py`)

New endpoint `POST /intensity/export/shapefile`:

- **Request model** (Pydantic): a GeoJSON FeatureCollection. Validate
  `type == "FeatureCollection"` and a non-empty `features` list; reject empty with
  HTTP 400.
- **Write** to a `tempfile.TemporaryDirectory()` using `fiona`:
  - Schema: `{"geometry": "Polygon", "properties": {"mmi_low": "int",
    "mmi_high": "int", "color": "str"}}`.
  - Map each feature's `mmi_lower`→`mmi_low`, `mmi_upper`→`mmi_high`,
    `color`→`color`.
  - CRS: `EPSG:4326` (writes the `.prj`); driver `ESRI Shapefile`.
- **Zip** all sidecar files (`.shp/.shx/.dbf/.prj/.cpg`) into an in-memory
  `io.BytesIO` via `zipfile`.
- **Return** `Response(zip_bytes, media_type="application/zip",
  headers={"Content-Disposition": "attachment; filename=mmi_bands.shp.zip"})`.

Helper extraction: a small `featurecollection_to_shapefile_zip(fc) -> bytes`
function (in `api.py` or a new `src/eqmon/export.py`) keeps the endpoint thin and
makes the logic unit-testable without HTTP. Decision deferred to the
implementation plan; default is a new `src/eqmon/export.py` module so `api.py`
does not grow further.

### Error handling

- Empty/invalid FeatureCollection → HTTP 400 with a clear `detail`.
- A feature whose geometry is not a Polygon/MultiPolygon → skip it and continue;
  if that leaves zero writable features → HTTP 400.
- Any `fiona` write error → HTTP 500 with a logged exception (mirrors existing
  endpoints using `logger`).

## Testing (TDD)

New `tests/test_shapefile_export.py`:

1. **Round-trip:** POST a small 2-feature FeatureCollection; assert 200,
   `application/zip`, and `Content-Disposition` filename. Unzip in-memory; assert
   `.shp/.shx/.dbf/.prj` all present. Re-open with `fiona`; assert feature count,
   that `mmi_low`/`mmi_high`/`color` attributes survived, CRS is EPSG:4326, and
   geometry type is Polygon.
2. **Empty rejection:** POST a FeatureCollection with `features: []` → 400.
3. **Non-polygon skip:** POST a mix of one Polygon + one Point; assert the Point
   is dropped and the Polygon survives.
4. **Helper unit test:** call `featurecollection_to_shapefile_zip` directly and
   assert it returns non-empty `bytes` forming a valid zip (no HTTP layer).

Run with `pytest tests/test_shapefile_export.py`.

## Files Touched

- `web/styles.css` — enlarge legend (Feature 1).
- `web/app.js` — `_lastFc`, data-driven `renderLegend`, checkboxes, export button,
  `exportShapefile()` (Feature 2).
- `web/index.html` — only if the export button/footer needs static markup
  (likely none; legend is JS-built).
- `src/eqmon/api.py` — new `POST /intensity/export/shapefile` endpoint + request
  model.
- `src/eqmon/export.py` *(new)* — `featurecollection_to_shapefile_zip()`.
- `tests/test_shapefile_export.py` *(new)* — tests above.

## Open Questions

None blocking. Helper module location (`export.py` vs inline) is a minor
implementation detail resolved in the plan.
