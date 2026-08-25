# eqMonitoring2 — Roadmap

## Active Plan — True 2D / 3D Analysis Map

### Outcome

Add a persistent map-mode control that lets an operator move between the existing
Leaflet 2D map and a true MapLibre GL 3D map without losing the current event,
camera position, analysis layers, filters, opacity settings, or sidebar state.

The 2D map remains the stable default. The 3D map adds pitched terrain and
height-extruded buildings while preserving the same operational data semantics.

### Delivery Estimate

| Milestone | Estimate | Result |
|-----------|----------|--------|
| Foundation and 3D shell | 1-2 days | Toggle, MapLibre map, synchronized camera, fallback |
| Core analysis parity | 2-3 days | Event, MMI, boundaries, layer state |
| Terrain and buildings | 2-3 days | DEM terrain and height extrusions |
| Hazard layers and interaction parity | 2-4 days | Landslides, PGA, hover/click, legends |
| Hardening and rollout | 2-3 days | Performance, accessibility, browser tests, documentation |
| **Total** | **9-15 engineering days** | Production-ready dual renderer |

### Architecture Decision

Use two renderer adapters behind one small mode-coordinator interface:

- **Leaflet adapter:** the existing 2D renderer and default/fallback.
- **MapLibre adapter:** a new 3D renderer, initialized lazily on first use.
- **Mode coordinator:** owns shared camera and analysis state, activates one
  renderer, and synchronizes state when the mode changes.

Do not replace Leaflet and do not add `if (mode === "3d")` branches throughout
feature modules. Rendering differences belong inside the two adapters.

Proposed interface at the seam:

```javascript
mapModes.setMode("2d" | "3d")
mapModes.getMode()
mapModes.setCamera({ center, zoom, bearing, pitch })
mapModes.publish({ event, mmi, layers, theme })
mapModes.resize()
```

The interface includes these invariants:

- Only one primary renderer is visible and interactive at a time.
- Switching modes does not issue analysis API requests again.
- Latitude, longitude, and practical ground scale are preserved across modes.
- Bearing and pitch are retained for 3D but ignored safely by Leaflet.
- If MapLibre, terrain, or WebGL initialization fails, mode returns to 2D and
  announces the failure without losing analysis state.

### Scope

**Included in the first production release**

- 2D / 3D segmented toggle with keyboard and screen-reader support.
- Camera synchronization in both directions.
- Current event and catalog event markers.
- MMI filled bands and epicenter.
- Administrative and tectonic reference overlays.
- Landslide susceptibility raster PMTiles.
- PGA hazard layers.
- Height-extruded building footprints.
- Terrain, hillshade, theme synchronization, legends, opacity, and visibility.
- Responsive behavior, reduced motion, WebGL fallback, and performance limits.

**Not included**

- 3D subsurface fault geometry.
- Physically simulated wave propagation.
- Photorealistic meshes or satellite-derived building models.
- Replacing the analytical hotspot mini-map in Insights.
- Moving Vs30 into the database or browser.
- Recalculating hazard or vulnerability values for 3D presentation.

### Decision Gates

- [x] **DG-1 Terrain source:** use public Terrarium DEM for the first release,
  or require a locally hosted DEM tile archive before implementation.
  - Recommended first release: AWS Open Data Terrarium raster DEM with MapLibre
    `encoding: "terrarium"`, explicit attribution, timeout, and no-terrain fallback.
  - Follow-up for self-contained deployment: build a local terrain PMTiles archive.
- [x] **DG-2 Browser floor:** use WebGL2-capable Edge/Chrome as the operational
  target; keep 2D available for unsupported hardware.
- [x] **DG-3 3D camera defaults:** use pitch `55`, bearing `0`, maximum pitch
  `70`, and a short camera transition disabled by reduced-motion preference.
- [x] **DG-4 layer parity:** block release if any core layer
  in the Included list cannot render correctly in 3D.

These are the approved working defaults for phased implementation. DG-1 keeps a
local terrain archive as a later hardening task, not a blocker for the tracer bullet.

---

### Phase 0 — Baseline and Technical Spike

**Goal:** prove the external dependencies and identify current map behavior before
changing production paths.

- [x] Record the current 2D camera, layer defaults, pane order, and active-event
  behavior in a short fixture reserved for browser tests and locked by pytest.
- [x] Inventory every direct `map.*` call in:
  - `web/app.js`
  - `web/buildings.js`
  - `web/landslides.js`
  - `web/pga.js` or the PGA section of `web/app.js`
- [x] Classify each call as camera, layer lifecycle, interaction, layout, or
  Leaflet-only implementation detail.
- [x] Build a throwaway MapLibre page that verifies:
  - Pakistan raster basemap loads without a token.
  - Terrarium DEM pitches correctly.
  - PMTiles protocol can read one existing vector archive.
  - A sample building tile supports `fill-extrusion-height` from `height`.
  - One landslide raster PMTiles archive renders with transparency.
- [x] Measure current 2D load plus cold 3D activation, frame rate, and memory on
  the development machine; repeat final budgets on operations-room hardware in
  Phase 9.
- [x] Delete the spike after recording findings; production work starts only if
  all five rendering checks pass.

**Acceptance criteria**

- [x] No production behavior changed.
- [x] Terrain and PMTiles sources work in the target browser.
- [x] Building `height` values are confirmed in metres and missing values are
  identified consistently with `web/buildings.js`.

**Phase 0 findings — 2026-08-25**

- Literal global `map.*` coupling: 85 call sites across the three primary map
  modules: 68 in `web/app.js`, 12 in `web/buildings.js`, and 5 in
  `web/landslides.js`. The broader renderer-coupled inventory is 98 sites when
  `.addTo(map)`, map construction, controls, panes, and projections are included.
  Counts and classifications are retained in `docs/map-renderer-inventory.md`.
- Only four publication seams are required for the tracer bullet: settled camera,
  `updateCurrentEventCard()`, `renderCurrentMmiLayer()` plus its visibility setter,
  and building district reconciliation.
- MapLibre GL `5.7.1` and PMTiles `4.3.0` loaded successfully in headless Edge on
  the target development machine.
- AWS Terrarium DEM loaded with `encoding: "terrarium"`; terrain and hillshade
  rendered at pitch `55` without a token.
- `web/tiles/districts.pmtiles` loaded through the PMTiles protocol and returned
  21 source features in the sampled Muzaffarabad view.
- `web/landslides/ajk.pmtiles` loaded as a transparent raster source with nearest
  resampling.
- The real `Muzaffarabad_buildings` proxy source returned 22,678 visible features;
  positive `height` values drove `fill-extrusion-height`, with a sampled maximum
  of 12.55 m.
- Provisional headless baseline at 1440x900: style ready 22 ms, fully idle 2.75 s,
  62 sampled FPS, and 54 MB reported JavaScript heap. These are compatibility
  numbers, not final production budgets.
- Existing 2D baseline on the same machine: DOM content loaded 1.12 s, window
  load 1.33 s, and first Leaflet tile visible 1.37 s.
- The tested source configuration, camera, measurement definitions, result JSON, and
  missing-height rule are retained in `docs/maplibre-3d-spike-results.md`.
- The temporary spike was deleted after the successful run. The normalized 2D
  baseline is retained in `tests/fixtures/map_mode_baseline.json`.

---

### Phase 1 — Dependencies, Containers, and Mode Control

**Goal:** provide an accessible toggle and a lazily initialized empty 3D renderer.

**Files**

- `web/index.html`
- `web/styles.css`
- New: `web/map-modes.js`
- New: `web/maplibre-3d.js`
- `tests/test_web_assets.py`

**Tasks**

- [ ] Pin MapLibre GL JS and CSS to an exact version with integrity hashes, or
  self-host the pinned assets if SRI is unavailable.
- [ ] Register the existing PMTiles v4 protocol with MapLibre once.
- [ ] Add `<div id="map-3d">` beside the existing `<div id="map">`.
- [ ] Add a compact `2D / 3D` segmented control over the map, clear of the
  sidebar, time control, MMI ladder, legends, and exposure strip.
- [ ] Use native buttons with `aria-pressed`, a group label, visible focus, and
  minimum 44px targets.
- [ ] Keep 2D selected by default; persist a successful user selection in
  `localStorage` but ignore stored 3D mode when WebGL is unavailable.
- [ ] Initialize MapLibre only on the first 3D request.
- [ ] Show a short loading state while the renderer and style initialize.
- [ ] On failure, restore Leaflet, reset the toggle, and show a non-blocking toast.
- [ ] Respect `prefers-reduced-motion` when changing renderer visibility.
- [ ] Revision all mutable frontend assets in `web/index.html`.

**Acceptance criteria**

- [ ] Initial page load creates no MapLibre map and performs no terrain request.
- [ ] Toggle works with mouse, Enter, and Space.
- [ ] Repeated mode changes create at most one Leaflet and one MapLibre instance.
- [ ] Dashboard and expanded forecast continue to hide/restore the active map.
- [ ] A WebGL initialization failure leaves the existing 2D map usable.

---

### Phase 2 — Shared Camera and Analysis State

**Goal:** create the deep mode-coordinator module and prevent renderer-specific
state from leaking into feature modules.

**Files**

- `web/map-modes.js`
- `web/maplibre-3d.js`
- `web/app.js`
- `web/buildings.js`
- `web/landslides.js`

**Tasks**

- [ ] Define one normalized camera shape:
  `{ center: [lon, lat], zoom, bearing, pitch }`.
- [ ] Convert Leaflet `[lat, lon]` values only inside the Leaflet adapter.
- [ ] Capture Leaflet camera on `moveend` and MapLibre camera on `moveend`.
- [ ] Add a re-entrancy guard so synchronization cannot produce move loops.
- [ ] Preserve center and practical scale when translating zoom levels; calibrate
  any Leaflet/MapLibre zoom offset in one named conversion function.
- [ ] Define normalized shared analysis state:
  - selected/current event
  - current MMI FeatureCollection
  - active map-event FeatureCollection and filters
  - selected basemap
  - overlay visibility/style settings
  - landslide region visibility and opacity
  - PGA return period and opacity
  - building enabled/district state
  - theme and alert level
- [ ] Publish state from existing successful render paths instead of refetching it.
- [ ] Keep renderer-specific objects out of shared state: no Leaflet layers,
  MapLibre source handles, DOM nodes, or class instances.
- [ ] Route map resizing through `mapModes.resize()` after sidebar collapse,
  dashboard close, expanded forecast close, and mobile viewport changes.

**Acceptance criteria**

- [ ] Twenty repeated mode switches do not drift the map center or zoom.
- [ ] Changing camera in either mode is reflected when returning to the other.
- [ ] Switching modes causes no `/intensity`, `/events`, `/impact`, or
  `/aftershock` refetch.
- [ ] Shared state is JSON-serializable and testable without either renderer.

---

### Phase 3 — 3D Basemap, Terrain, Theme, and Attribution

**Goal:** make the 3D map spatially useful before adding analysis overlays.

**Files**

- `web/maplibre-3d.js`
- New: `web/map-style-config.js`
- `web/app.js`
- `web/styles.css`

**Tasks**

- [ ] Extract basemap definitions into shared configuration containing Leaflet
  URL templates and equivalent MapLibre raster source definitions.
- [ ] Start with the same keyless basemap selected in 2D.
- [ ] Add raster DEM source, terrain exaggeration `1.0`, and subtle hillshade.
- [ ] Keep terrain source attribution visible and deduplicated with basemap text.
- [ ] Add sky/fog only if it improves depth without reducing hazard contrast.
- [ ] Reapply the selected light/dark basemap and application theme on mode change.
- [ ] Keep the MMI alert palette independent of basemap styling.
- [ ] Handle DEM timeout by retaining pitched 3D without terrain and announcing
  "Terrain unavailable" once.
- [ ] Restrict pitch/rotation gestures where they conflict with page scrolling on
  touch devices; retain compass/reset-bearing controls.

**Acceptance criteria**

- [ ] Pakistan opens at the same center and scale as 2D.
- [ ] Terrain is visible at regional and district scales without excessive relief.
- [ ] Light and dark themes preserve text and control contrast.
- [ ] Missing DEM tiles do not blank or crash the map.

---

### Phase 4 — Events and MMI Core Analysis

**Goal:** make the principal earthquake workflow available in 3D.

**Files**

- `web/maplibre-3d.js`
- `web/map-modes.js`
- `web/app.js`
- `tests/test_aftershock_ui.py`

**Tasks**

- [ ] Add GeoJSON sources for current epicenter, catalog/map events, and MMI bands.
- [ ] Reuse the existing MMI color lookup and selected-band semantics.
- [ ] Render MMI fills draped over terrain with borders readable in both themes.
- [ ] Preserve severity ordering so stronger MMI bands are not hidden by weaker ones.
- [ ] Render the active epicenter above terrain with a restrained pulse disabled
  under reduced motion.
- [ ] Port event bubble sizing and depth colors exactly from 2D.
- [ ] Port event click selection, popup content, and current-event synchronization.
- [ ] Port MMI band selection/highlighting from the existing right-side ladder.
- [ ] Keep export behavior data-driven and renderer-independent.

**Acceptance criteria**

- [ ] The same event has the same coordinates, magnitude, depth color, and popup
  values in both modes.
- [ ] MMI band colors and selection match 2D.
- [ ] Drawing a new footprint while 3D is active updates both renderers.
- [ ] No analysis formula or GeoJSON geometry changes are introduced.

---

### Phase 5 — Reference Overlays and Hover Interaction

**Goal:** port the operational boundary/fault context with equivalent controls.

**Files**

- `web/maplibre-3d.js`
- `web/map-style-config.js`
- `web/app.js`

**Tasks**

- [ ] Register each boundary/fault PMTiles archive as a MapLibre vector source.
- [ ] Map the existing `OVERLAY_CONFIG` values to line/fill/opacity expressions.
- [ ] Preserve published categorical colors for PGA Zones.
- [ ] Preserve default visibility for National, Provinces, and National Faults.
- [ ] Port hover hit-testing and tooltip field/label/unit formatting.
- [ ] Increase line widths under pitch where needed for equivalent visual weight.
- [ ] Synchronize visibility, color, width, and opacity edits immediately.
- [ ] Ensure sources are registered once and layers are toggled, not repeatedly
  destroyed and reconstructed.

**Acceptance criteria**

- [ ] Every reference overlay available in Layers renders in 3D.
- [ ] Hover fields and values match 2D fixtures.
- [ ] Published PGA Zone colors remain unchanged.
- [ ] Layer toggles do not accumulate duplicate MapLibre layers or event handlers.

---

### Phase 6 — Building Extrusions

**Goal:** use the existing building-height data as the primary true-3D layer.

**Files**

- `web/maplibre-3d.js`
- `web/buildings.js`
- `web/styles.css`
- `tests/test_buildings_api.py`

**Tasks**

- [ ] Reuse `GET /buildings/districts` for bounds and minimum zoom.
- [ ] Reuse `/buildings/tiles/{district}/{z}/{x}/{y}.pbf` sources.
- [ ] Add/remove district vector sources according to viewport intersection,
  preserving the current rule that only a small set is live at once.
- [ ] Use `fill-extrusion-height` from positive finite `height` values in metres.
- [ ] Give unknown/non-positive heights a small flat height rather than implying a
  measured building height.
- [ ] Reuse the five height-band colors and shared opacity.
- [ ] Keep buildings below MMI and event emphasis in the visual hierarchy.
- [ ] Disable extrusion below the configured minimum zoom.
- [ ] Update district selection and map framing through the mode coordinator.
- [ ] Add a configurable source cap and eviction policy for long pan sessions.

**Acceptance criteria**

- [ ] Building heights and colors match the existing legend.
- [ ] Selecting a district frames it and renders at a usable zoom in both modes.
- [ ] Unknown heights are visually distinct and never interpreted as high-rise.
- [ ] Panning across districts does not leave stale sources or unbounded memory.

---

### Phase 7 — Landslide and PGA Raster Hazard Layers

**Goal:** reach hazard-layer parity without changing analytical meaning.

**Files**

- `web/maplibre-3d.js`
- `web/landslides.js`
- PGA implementation in `web/app.js`
- `scripts/build_landslide_tiles.py`

**Tasks**

- [ ] Add each enabled landslide raster PMTiles archive as an independent source.
- [ ] Preserve AJK, GB, KP, and Balochistan toggles and shared opacity.
- [ ] Preserve transparent/unassessed areas and the Very High-only classification.
- [ ] Port PGA return-period raster sources, class breaks, opacity, and attribution.
- [ ] Drape raster hazards over terrain without smoothing categorical classes.
- [ ] Use nearest-neighbor raster resampling where MapLibre supports it.
- [ ] Keep landslide and PGA legends mode-independent so switching renderers does
  not duplicate or reposition them.
- [ ] Report archive/source errors per layer without disabling unrelated regions.

**Acceptance criteria**

- [ ] All four landslide regions can be toggled independently in 3D.
- [ ] Landslide and PGA colors, opacity, and legends match 2D.
- [ ] Raster edges align with administrative reference geometry.
- [ ] One failed archive does not remove other active hazard layers.

---

### Phase 8 — Interaction, Layout, and Accessibility Parity

**Goal:** make mode switching safe during active analysis rather than a demo view.

**Files**

- `web/map-modes.js`
- `web/maplibre-3d.js`
- `web/index.html`
- `web/styles.css`

**Tasks**

- [ ] Preserve selected event, selected MMI band, filters, and open sidebar section.
- [ ] Ensure time-window controls update 3D event visibility.
- [ ] Keep map legends clear of the sidebar, MMI ladder, status bar, exposure strip,
  chat trigger, and MapLibre attribution/controls.
- [ ] Keep toggle reachable and unobscured at 200% browser zoom.
- [ ] Add visible focus, `aria-pressed`, descriptive group label, and live status
  text for loading/failure.
- [ ] Do not announce routine camera changes to screen readers.
- [ ] Respect reduced motion for camera transitions, epicenter pulse, and fades.
- [ ] On mobile, default 3D bearing to north and provide a one-tap reset.
- [ ] Disable browser context-menu conflicts only where MapLibre requires them.
- [ ] Confirm expanded Forecast, Elements at Risk, and Insights restore the correct
  renderer and call its resize method when closed.

**Acceptance criteria**

- [ ] Complete mode toggle is keyboard-operable and screen-reader named.
- [ ] Layout works at 1440x900, 1024x768, 430x800, and 200% zoom.
- [ ] Opening/closing every full-screen view leaves the active map correctly sized.
- [ ] Reduced-motion users receive no animated fly or spin transition.

---

### Phase 9 — Performance, Reliability, and Tests

**Goal:** prevent the second renderer from degrading the existing operational map.

**Files**

- `tests/test_web_assets.py`
- New: `tests/test_map_modes.py`
- New: `tests/browser/test_map_modes.py`
- `pyproject.toml`
- `web/map-modes.js`
- `web/maplibre-3d.js`

**Tasks**

- [ ] Add Python Playwright to the dev dependency group through `uv` if browser
  tests are made part of the repeatable suite.
- [ ] Test pure camera conversion and shared-state normalization functions.
- [ ] Test lazy initialization, one-instance invariant, fallback, and mode state.
- [ ] Browser-test 2D -> 3D -> 2D camera and layer preservation.
- [ ] Browser-test WebGL failure and DEM failure separately.
- [ ] Browser-test events, MMI, one vector overlay, one landslide region, PGA, and
  one building district with fixture data/mocked tile responses.
- [ ] Run interaction tests in dark and light themes.
- [ ] Capture console errors and fail tests on unhandled exceptions.
- [ ] Establish budgets on the target machine:
  - first 3D activation <= 3 seconds on warm network
  - mode switch after initialization <= 500 ms
  - interactive frame rate >= 30 FPS in a representative district
  - no source/layer growth after 20 mode switches and a district pan loop
- [ ] Pause hidden renderer animation/render loops where supported.
- [ ] On low-memory/WebGL context loss, return to 2D and release recoverable 3D
  resources without reloading the page.

**Verification commands**

```bash
node --check web/app.js
node --check web/map-modes.js
node --check web/maplibre-3d.js
uv run pytest tests/test_map_modes.py -q
uv run pytest -q
```

**Acceptance criteria**

- [ ] Existing pure, API, DB-skip, and frontend regression tests remain green.
- [ ] Browser matrix passes in current Edge and Chrome.
- [ ] No repeated listeners, duplicate sources, duplicate layers, or WebGL leaks.
- [ ] 2D startup performance remains within 5% of its pre-3D baseline.

---

### Phase 10 — Documentation and Rollout

**Goal:** release incrementally with an immediate fallback path.

- [ ] Add a disabled-by-default `ENABLE_3D_MAP` feature flag for initial integration.
- [ ] Enable the flag in development after Phases 1-4.
- [ ] Enable it for internal operations testing after Phases 5-8.
- [ ] Record terrain source, attribution, browser requirements, and offline behavior
  in `README.md` or `CLAUDE.md`.
- [ ] Document local terrain build steps if DG-1 selects self-hosting.
- [ ] Update `AGENTS.md` quick reference if a new terrain build command is added.
- [ ] Add operator help text limited to: drag to rotate, Shift+drag to pitch, and
  reset north; do not add a persistent tutorial overlay.
- [ ] Test with a live representative event and obtain operator sign-off.
- [ ] Remove the feature flag only after one stable operational release.

**Release definition of done**

- [ ] 3D is true MapLibre rendering with terrain and building extrusion.
- [ ] 2D remains the default, complete, and independently usable.
- [ ] Core analysis state survives mode changes with no refetch or recalculation.
- [ ] Every included layer has verified 2D/3D semantic and visual parity.
- [ ] Unsupported hardware falls back automatically and accessibly.
- [ ] Performance budgets and full test suite pass.

---

### Implementation Order and Blocking Edges

1. DG-1 through DG-4 block Phase 1 production implementation.
2. Phase 0 blocks dependency commitment.
3. Phase 1 blocks every renderer feature.
4. Phase 2 blocks Phases 4-8 because features need shared state first.
5. Phase 3 can proceed in parallel with late Phase 2 work.
6. Phases 4, 5, 6, and 7 can proceed independently after Phase 2.
7. Phase 8 requires Phases 4-7 to verify real layout and interactions.
8. Phase 9 blocks production enablement.
9. Phase 10 controls rollout and final sign-off.

### Recommended First Tracer Bullet

Implement only this vertical slice before broad layer porting:

- [ ] Accessible toggle and lazy MapLibre initialization.
- [ ] Camera synchronization.
- [ ] Raster basemap and terrain.
- [ ] One current-event marker.
- [ ] One MMI FeatureCollection.
- [ ] One district building extrusion.
- [ ] Browser test covering 2D -> 3D -> 2D state preservation.

This tracer bullet proves the mode coordinator, terrain, analytical GeoJSON, and
the hardest 3D tile source without prematurely porting every overlay.

---

## ✅ Complete — USGS FDSN Integration (Phases 1-4)

Full pipeline: fetch → ingest → dedup → incremental sync → detail cache → catalog UI with impact rollups and USGS metadata card.

See git log for details: `git log --oneline --author-date-order HEAD~4..HEAD`

---

## 🔲 Phase 5 — METSource (Primary)

**Value:** Pakistan MET Department feed becomes the primary source, winning dedup priority over USGS.

| File | What |
|------|------|
| `sources.py` | Implement `METSource.fetch()` once feed format is known |
| `config.py` | Add MET feed URL, polling interval, etc. |
| `sources.py` | Add source priority constant (MET=1, USGS=2) |
| `ingest.py` | _recluster already prefers MET over USGS |

**Blocked by:** MET feed format unknown.

---

## 🔲 Phase 6 — Boundary data pipeline

**Value:** Fresh developer can run `uv run python scripts/load_boundaries.py && uv run python scripts/build_tiles.py` and get admin overlays working.

| File | What |
|------|------|
| `scripts/load_boundaries.py` | Review/update; add idempotency |
| `scripts/build_tiles.py` | Review/update; add `--force` or check for existing tiles |
| `scripts/` | Add README or docstring with prerequisites (Docker, PostGIS) |
| `AGENTS.md` | Add build pipeline section |

---

## 🔲 Phase 7 — Edit/delete events

**Value:** Clean up test data, delete/update imported events without raw DB access.

| File | What |
|------|------|
| `repo.py` | `delete_event(conn, event_id)`, `update_event(...)` |
| `api.py` | `DELETE /events/{id}`, `PUT /events/{id}` |
| `app.js` | Delete button on event cards or detail panel, confirmation dialog |

---

## 🔲 Phase 8 — Automated ingest scheduler

**Value:** Catalog stays current without manual "Pull USGS feed" button clicks.

| File | What |
|------|------|
| `api.py` | Add `@app.on_event("startup")` or background task with apscheduler |
| `config.py` | Add `INGEST_INTERVAL_MINUTES = 15` |
| `api.py` | One-shot ingest on startup + periodic timer |

---

## 🔲 Phase 9 — Auto schema on startup

**Value:** No manual `init_schema()` invocation — migrations run automatically when the server starts.

| File | What |
|------|------|
| `api.py` | Call `db.init_schema()` in a startup event |
| `db.py` | Ensure `init_schema()` is safe to call multiple times (it already is) |

---

## 🔲 Phase 10 — Event filtering & search

**Value:** Filter catalog by magnitude range, date range, source; search by place name.

| File | What |
|------|------|
| `repo.py` | Add `search_events()`, `count_events()` |
| `api.py` | Add query params to `GET /events` |
| `app.js` | Filter inputs in catalog section |

---

## Quick reference

| Command | Description |
|---------|-------------|
| `uv sync --group dev` | Install all deps (dev included) |
| `uv run pytest -q` | Run full test suite |
| `uv run python -c "from eqmon.db import init_schema; init_schema()"` | Apply pending migrations |
| `uv run uvicorn eqmon.api:app --port 8000` | Start dev server |
