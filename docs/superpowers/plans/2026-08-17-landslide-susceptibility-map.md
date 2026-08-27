# Landslide Susceptibility Map Integration Plan

**Status:** Phase 0 and implementation complete; artifact build/validation in progress. Production release still requires provenance, license, and coverage-mask confirmation  
**Date:** 2026-08-17  
**Scope:** Map visualization first; analytical use is a separate gated phase

## 1. Objective

Add landslide susceptibility to the map as a fast, scientifically traceable,
offline-capable hazard layer that:

- does not slow initial map load;
- remains visually subordinate to an active earthquake MMI footprint;
- works on desktop, touch devices, and controlled/offline deployments;
- preserves categorical values without interpolation;
- carries explicit coverage, provenance, version, and no-data semantics; and
- can later support point sampling and event/admin analysis without loading
  millions of raster-derived polygons into PostGIS.

The current shapefiles are the accepted filtered Very High mask. They still need
streaming geometry repair, categorical rasterization, reprojection, validation,
and reproducible packaging before they are production-ready.

## 2. Current Data Assessment

The source directory is currently:

```text
data/LS Susceptability Maps/
  AJK.*
  GB.*
  KP.*
  Baloch.*
```

Use the correctly spelled durable identifier `landslide_susceptibility` in code,
URLs, manifests, and UI. Keep the misspelled directory name only as a temporary
input path until the source drop is reorganized.

### 2.1 Measured inventory

| Region | Source CRS | Features | Approx. package size | WGS84 extent |
|---|---:|---:|---:|---|
| AJK | EPSG:32643 | 732,111 | 148 MB | 73.39-74.60 E, 32.94-35.13 N |
| GB | EPSG:32643 | 756,777 | 216 MB | 72.48-77.82 E, 34.48-37.07 N |
| KP | EPSG:32642 | 3,658,473 | 890 MB | 69.26-74.23 E, 31.07-36.98 N |
| Balochistan | EPSG:32642 | 2,173,496 | 446 MB | 60.71-70.28 E, 24.79-32.06 N |

Total: approximately 7.32 million polygons and 1.70 GB.

Every scanned feature has only:

```text
Id: integer
gridcode: 5
```

The ArcGIS metadata says the polygons were generated with `RasterToPolygon`
from four TIFFs that are not present. Sampled geometry contains roughly 2.2-2.9%
invalid polygons. The data therefore represents a raster class mask, not seven
million meaningful vector entities.

### 2.2 Confirmed semantics

Confirmed by the data owner on 2026-08-17:

1. `gridcode = 5` means **Very High landslide hazard/susceptibility**.
2. Classes 1-4 were intentionally filtered out before this data was supplied.
3. The product is a binary display mask: present polygons are Very High. Within
   an approved assessed-region mask, absence means not selected as Very High.
   Outside supplied regional coverage, absence remains unassessed.

The UI may therefore use the label `Very High landslide susceptibility`. It must
not call the layer a probability, forecast, event-triggered landslide map, or
risk map.

### 2.3 Remaining source-governance questions

Production release still requires:

1. Are AJK, GB, KP, and Balochistan the complete intended assessed coverage?
2. Which reviewed regional boundary defines where transparent pixels mean
   `not Very High` rather than `unassessed`?
3. Authoritative color confirmed on 2026-08-17: hazard red `#D73027`.
4. What methodology, source organization, version date, and license apply?
5. What refresh cadence and replacement policy are expected?
6. Are the original TIFFs available for independent reconstruction QA? They are
   useful but no longer a blocker for building from the accepted filtered masks.

## 3. Architecture Decision

### 3.1 Recommended representation

Use two distinct data planes:

1. **Analytical source:** one categorical Cloud Optimized GeoTIFF per region,
   reconstructed from the accepted Very High vector mask.
2. **Display derivative:** sparse raster PMTiles generated from those COGs.

Expose all regional files as one logical frontend layer through a manifest.
Regional separation is retained because source resolution and UTM zone differ.

```text
Authoritative TIFFs
        |
        v
prepare_landslide_data.py
  - validate source contract
  - normalize categorical values
  - reproject with nearest-neighbor
  - build COG overviews
  - write checksums + provenance manifest
        |
        +----------------------+
        |                      |
        v                      v
data/landslides/*.tif     build_landslide_tiles.py
 analytical COGs                |
                                v
                      web/landslides/*.pmtiles
                      web/landslides/manifest.json
                                |
                                v
                         landslides.js
```

### 3.2 Why not raw vector PMTiles

The current vector builder materializes an entire shapefile as an in-memory
GeoJSON feature list. It is unsuitable for 7.32 million polygons. Tippecanoe's
generic drop/simplification options can also remove or alter hazard coverage.

A vector display derivative may be reconsidered only if authoritative rasters
are unavailable and a measured dissolve/generalization spike reduces complexity
by orders of magnitude while preserving area within an approved tolerance.

### 3.3 Why not raw-vector PostGIS

The polygon IDs are conversion artifacts, not domain entities. Loading 7.32
million invalid/tiny polygons into PostGIS would create high ingestion, index,
storage, and query costs without improving the initial display requirement.

PostGIS is not needed for Phase 1. Future analytical requirements should first
use COG window reads, point sampling, or precomputed admin summaries. PostGIS
raster or dissolved/subdivided polygons require a separate benchmark and ADR.

### 3.4 Why not one large PNG overlay

The PGA image-overlay pattern is excellent for its 347x250 grids but does not
scale to 10-30 m regional landslide data. A single image either becomes too large
or discards the detail users expect when zooming. A downsampled PNG remains a
valid fallback only if stakeholders explicitly choose strategic overview at
zoom 8 or lower.

## 4. Immediate Safety Work

Complete these before any data processing:

1. Add `data/LS Susceptability Maps/` and the normalized future raw-source
   directory to `.gitignore`.
2. Add raw landslide directories to `.dockerignore`; the current Docker context
   would otherwise absorb approximately 1.70 GB.
3. Remove/ignore the zero-byte ArcGIS `.sr.lock` file.
4. Do not add the landslide sources to the existing `build_tiles.py` layer list.
5. Record source files and SHA-256 checksums in a local intake manifest.
6. Obtain the methodology, source organization, license, release date, approved
   Very High color, and assessed-region coverage masks.
7. Obtain the original TIFFs when available for independent QA; do not block the
   AJK/GB technical spike on them.

These are repository-safety changes, not acceptance of the data product.

## 5. Source Acceptance Contract

Create `data/landslides/source_manifest.json` from reviewed source material. It
must contain:

```json
{
  "dataset_id": "landslide_susceptibility",
  "dataset_version": "owner-supplied-version",
  "title": "authoritative title",
  "source_organization": "...",
  "license": "...",
  "methodology_url": "...",
  "regions": [
    {
      "id": "kp",
      "source_file": "data/LS Susceptability Maps/KP.shp",
      "sha256": "...",
      "crs": "EPSG:32642",
      "resolution_m": [10, 10],
      "nodata": 255,
      "classes": [5]
    }
  ],
  "classes": [
    {"value": 5, "label": "Very High", "color": "owner-approved-color"}
  ],
  "absence_semantics": "filtered_to_very_high_within_assessed_region",
  "outside_coverage_semantics": "unassessed"
}
```

The build must fail closed when any required provenance, class, CRS, checksum,
or no-data field is missing.

## 6. Data Preparation Pipeline

Add a dedicated `scripts/prepare_landslide_data.py`. Do not extend the generic
vector builder.

### 6.1 Inputs

Input: the four accepted filtered shapefiles in
`data/LS Susceptability Maps/`. They are authoritative for the supplied Very High
mask. The generated manifest must record
`reconstructed_from_raster_derived_polygons: true` because the geometry has
already passed through ArcGIS `RasterToPolygon` simplification.

The build must stream features. It must not materialize millions of features as
one Python list or GeoJSON document.

### 6.2 Processing rules

For each region:

1. Verify file SHA-256 against the intake manifest.
2. Verify CRS equals EPSG:32642 or EPSG:32643 as declared.
3. Stream all records and fail if any `gridcode` is not 5.
4. Repair invalid geometry deterministically and report repaired/skipped counts
   and area deltas. No invalid feature is silently dropped.
5. Derive and record the native target resolution per region from source
   metadata/geometry, then validate it against sampled raster-cell fragments.
6. Rasterize the repaired mask in its native CRS using burn value 5.
7. Apply the approved assessed-region boundary so values have three states:
   `5 = Very High`, `0 = assessed but not Very High`, `255 = unassessed/nodata`.
8. Reproject to EPSG:4326 using nearest neighbor only.
9. Store values as `uint8`.
10. Reject unknown classes rather than assigning a fallback color.
11. Build tiled, compressed COGs with categorical overviews using nearest or an
   explicitly approved dominant-class policy. Never average class codes.
12. Emit COG SHA-256, dimensions, bounds, class counts, assessed area, and build
    tool versions into `data/landslides/manifest.json`.

### 6.3 Validation gates

- transformed bounds match expected regional bounds;
- all pixels are declared classes or nodata;
- no bilinear/cubic/average resampling appears in command configuration;
- class area before and after reprojection remains within an approved tolerance;
- COG internal tiling and overview structure validate;
- known control points return owner-confirmed class/nodata values; and
- adjacent regional edges are checked for gaps/overlap and documented.

## 7. Display Tile Pipeline

Add `scripts/build_landslide_tiles.py`.

### 7.1 Outputs

```text
web/landslides/manifest.json
web/landslides/ajk.pmtiles
web/landslides/gb.pmtiles
web/landslides/kp.pmtiles
web/landslides/balochistan.pmtiles
```

The display manifest should include:

- dataset/version/provenance summary;
- regional archive URL and WGS84 bounds;
- min/max zoom;
- tile format;
- authoritative class palette;
- opacity default;
- absence/no-data statement;
- source and output checksums; and
- build timestamp and tool versions.

### 7.2 Tile generation rules

- Generate transparent PNG or lossless WebP raster tiles.
- Use nearest-neighbor categorical sampling.
- Omit fully transparent tiles so archives stay sparse.
- Retain one archive per region for independent rebuild/replacement.
- Do not interpolate colors between classes.
- Do not bake UI opacity into tile alpha; the frontend controls opacity.
- Select zoom range from measured source resolution and product need, not from a
  generic default. Initial candidate: zoom 5-12, validated with stakeholders.
- Produce a build report with archive size, tile count, p50/p95/max tile bytes,
  class pixel counts by zoom, and omitted-area estimates.

### 7.3 Required delivery spike

Before committing to raster PMTiles, build AJK and GB as a spike and verify:

1. the chosen Leaflet PMTiles client supports raster archives and HTTP range
   requests in the current no-bundler frontend;
2. FastAPI `FileResponse` returns `206`, `Content-Range`, and `Accept-Ranges`;
3. pan/zoom requests only required byte ranges;
4. transparent sparse tiles render without seams; and
5. memory/network budgets below are met.

If the raster PMTiles client is not reliable, fallback order is:

1. prebuilt XYZ tiles for a deployment that can tolerate many files;
2. a bounded Rasterio tile endpoint with HTTP caching;
3. a deliberately downsampled regional PNG overview if detailed zoom is not a
   requirement.

## 8. Frontend Integration

Implement landslide runtime behavior in `web/landslides.js`, loaded after
`app.js`, following the isolation pattern used by `buildings.js`.

Do not add another large subsystem directly to `app.js`.

### 8.1 One logical layer

The UI exposes one toggle: `Landslide susceptibility`.

The manager reads the manifest and mounts only regional sources whose bounds
intersect the viewport. Four source archives remain an implementation detail.

### 8.2 Pane order

Create a dedicated `landslidePane` around z-index 320:

```text
200 basemap
320 landslide susceptibility
330 PGA raster
350 buildings
400 earthquake MMI footprint
410 faults/boundaries/reference vectors
600 markers
```

This prevents susceptibility fills from hiding the active earthquake footprint,
fault lines, boundaries, markers, or tooltips.

Define and test the policy for simultaneous PGA and landslide fills. Recommended
default: enabling one static hazard fill disables the other, with an explicit
operator option to compare using reduced opacity only if product owners require
it.

### 8.3 Layer controls

Add a dedicated hazard block to the existing Layers panel:

- master checkbox;
- opacity slider, default 45-55%;
- compact authoritative class legend;
- assessed/not-assessed coverage note;
- dataset version/source link or details disclosure;
- loading/error state per region; and
- `Zoom to coverage` action.

Do not expose stroke width or arbitrary color controls for a published
categorical hazard product. Operators may change opacity; authoritative colors
remain locked.

### 8.4 Inspection behavior

Do not rely on mouse hover. Touch and keyboard users need equivalent behavior.

Recommended Phase 1 behavior:

- click/tap map to show class, class label, region, dataset version, and whether
  the location is outside assessed coverage;
- use a small FastAPI point-sampling endpoint over the analytical COGs if the
  raster tile client cannot expose pixel values reliably; and
- clearly distinguish `not assessed` from a lower susceptibility class.

If point inspection is out of initial scope, omit it entirely rather than
inferring values from rendered colors.

### 8.5 Mobile behavior

- legend collapses to a single-row summary and expands on tap;
- controls remain reachable without covering most of the map;
- no hover-only descriptions;
- touch targets are at least 44x44 CSS pixels;
- the layer manager loads only visible regions; and
- legend/controls avoid the MMI ladder, exposure strip, and AI robot positions.

## 9. Optional Backend Point Sampling

If inspection or later analytics is required, add a model-independent module:

```text
src/eqmon/landslides.py
```

Suggested deep interface:

```python
sample_susceptibility(lon: float, lat: float) -> SusceptibilitySample
```

The implementation owns:

- regional bounds lookup;
- WGS84-to-raster coordinate transforms;
- COG window reads;
- nodata and coverage semantics;
- dataset/version provenance; and
- process-wide dataset handles/caching.

Optional route:

```text
GET /landslides/sample?lon=...&lat=...
```

Return a typed distinction between:

```text
classified | nodata | outside_assessed_coverage
```

Do not return a low-risk class for an uncovered point.

## 10. Analytical Expansion - Deferred

Only begin this phase after visualization and source semantics are accepted.

Candidate capabilities:

- susceptibility class at an event or asset point;
- high-susceptibility area intersecting MMI bands;
- precomputed class area by district/tehsil;
- settlements/infrastructure inside susceptible terrain; and
- event-impact artifact provenance including landslide dataset checksum.

Preferred order:

1. point sampling from COG;
2. offline precomputed admin summaries;
3. bounded COG window analysis for an event footprint;
4. PostGIS raster/dissolved geometry only after benchmarks prove it necessary.

Do not load the current raw polygons into `admin_boundary` or reuse its loader.

## 11. Testing Strategy

### 11.1 Source/build tests

Add `tests/test_landslide_build.py` covering:

- declared files and checksums;
- source CRS and transformed expected bounds;
- dtype, nodata, classes, and histogram;
- categorical resampling configuration;
- manifest schema;
- class/legend parity;
- COG tiling/overview validation;
- PMTiles archive metadata and regional bounds;
- output ID/filename consistency; and
- deterministic rebuild from unchanged inputs.

### 11.2 Backend tests

If point sampling is added:

- known classified control points;
- nodata point;
- outside-coverage point;
- exact boundary/edge behavior;
- EPSG:32642 and EPSG:32643 transform smoke tests;
- invalid longitude/latitude;
- missing/corrupt COG typed failure; and
- no network or PostGIS dependency for pure sampling tests.

### 11.3 Static serving tests

- manifest and archive exist;
- byte-range request returns `206` and correct headers;
- missing archive returns `404`, never SPA HTML;
- traversal remains rejected; and
- content type does not prevent PMTiles client range reads.

### 11.4 Browser tests

Use Playwright to verify:

- no landslide requests before toggle-on;
- toggle loads only visible regional archives;
- pan reconciles active sources;
- opacity and locked legend colors;
- pane order leaves MMI/faults/markers visible;
- click/touch inspection semantics;
- loading/error/retry states;
- desktop and mobile legend placement;
- light/dark theme readability; and
- layer survives rapid toggle/pan without stale overlays.

### 11.5 Visual QA

Maintain owner-approved screenshots/control points for each region at low,
medium, and high zoom. Compare against the authoritative GIS product, not only
against the application's previous output.

## 12. Performance Budgets

Initial budgets to validate during the spike:

- zero landslide network requests while disabled;
- manifest under 50 KB;
- first visible viewport under 1 MB transferred at zoom 6-8;
- p95 raster tile under 200 KB and hard maximum under 500 KB;
- warm toggle visible within 250 ms;
- cold toggle useful content within 1 second on the target LAN;
- no long task over 100 ms from client-side raster processing;
- only viewport-intersecting regional archives mounted;
- no raw-source files in runtime Docker image; and
- no increase to non-landslide API response latency.

Budgets are release gates, not aspirations. Adjust only from measured target
network/device evidence.

## 13. Observability and Failure Handling

Track or log:

- manifest version and load failure;
- archive request failures by region;
- range-response status and bytes transferred;
- point-sample latency and outcome;
- COG open/cache failures; and
- dataset checksum at application startup when sampling is enabled.

Failure behavior:

- a missing region does not disable other regions;
- a missing manifest disables the control with a clear build instruction;
- corrupt/unrecognized classes fail visibly rather than using fallback colors;
- outside coverage is never rendered or reported as low susceptibility; and
- the earthquake map remains fully usable when landslide data is unavailable.

## 14. Deployment and Reproducibility

Update:

- `.gitignore` for raw and generated landslide products;
- `.dockerignore` to exclude raw source and analytical COGs unless the backend
  sampling feature is enabled;
- Docker packaging to include only `web/landslides/` display artifacts and,
  conditionally, `data/landslides/` analytical COGs;
- `README.md` and `AGENTS.md` with exact build order;
- a release manifest mapping source checksums to COG and PMTiles checksums; and
- backup/restore instructions for generated artifacts or their reproducible
  source package.

Proposed build order:

```text
uv run python scripts/prepare_landslide_data.py
uv run python scripts/build_landslide_tiles.py
uv run pytest -q tests/test_landslide_build.py
```

## 15. Delivery Phases

### Phase 0 - Source and safety gate

- [ ] Ignore raw files in Git and Docker contexts.
- [ ] Remove lock/transient files.
- [x] Confirm class 5 means Very High and classes 1-4 were intentionally
  filtered out.
- [ ] Confirm assessed-region masks and outside-coverage semantics.
- [ ] Obtain authoritative color, methodology, source organization, license,
  and version.
- [ ] Obtain original TIFFs for independent QA when available (non-blocking for
  the technical spike).
- [ ] Approve source manifest and control points.

**Exit:** data owner signs off that the application can label the product
accurately.

### Phase 1 - AJK/GB technical spike

- [ ] Build normalized COGs.
- [ ] Build raster PMTiles.
- [ ] Verify range delivery and Leaflet client compatibility.
- [ ] Measure tile/network/memory budgets.
- [ ] Compare visual output and area to source GIS.

**Exit:** chosen display transport is measured, faithful, and supportable.

### Phase 2 - Production map layer

- [ ] Build all four regions.
- [ ] Add `landslides.js` manager and dedicated pane.
- [ ] Add controls, legend, coverage note, loading/error states.
- [ ] Add touch/mobile behavior and browser tests.
- [ ] Package generated display artifacts reproducibly.

**Exit:** one logical layer works across regions without obscuring operational
earthquake layers or slowing default map load.

### Phase 3 - Optional sampling

- [ ] Add COG-backed sampling module and typed endpoint.
- [ ] Add class/nodata/outside-coverage semantics.
- [ ] Add transform, cache, and control-point tests.

**Exit:** map inspection reports traceable values from the analytical source.

### Phase 4 - Optional event/admin analytics

- [ ] Define approved questions and latency targets.
- [ ] Benchmark COG windows and precomputed summaries.
- [ ] Version landslide-derived artifacts and provenance.
- [ ] Consider PostGIS only if measured workloads require it.

## 16. Acceptance Criteria

The visualization is done only when:

- class labels/colors come from an authoritative legend;
- absence/no-data semantics are visible and correct;
- source, version, license, and checksum are recorded;
- categorical values are never averaged/interpolated;
- the layer is lazy-loaded and meets performance budgets;
- MMI, PGA, faults, markers, colorbar, exposure strip, and AI control remain
  legible and interactive;
- desktop, touch, and mobile flows pass browser tests;
- generated artifacts are reproducible and raw files stay out of Git/runtime
  images; and
- the map remains functional when every landslide artifact is unavailable.

## 17. Recommended Next Action

Start with repository safety changes and the source-manifest validator, then
implement the streaming AJK/GB shapefile-to-COG spike using burn value 5. Use the
spike to measure geometry repair, raster resolution, area preservation, COG size,
and raster-PMTiles delivery. Frontend production work still waits for the
approved Very High color, coverage masks, methodology, license, and version.
