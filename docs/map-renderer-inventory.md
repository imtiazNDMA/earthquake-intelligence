# Map Renderer Coupling Inventory

Recorded for Phase 0 of the dual Leaflet/MapLibre implementation on 2026-08-25.

## Counting Rules

Two counts are useful and must not be conflated:

- **Literal global `map.*` call sites:** 85 total: 68 in `web/app.js`, 12 in
  `web/buildings.js`, and 5 in `web/landslides.js`.
- **Renderer-coupled call sites:** 98 total. This broader count also includes
  `.addTo(map)`, the initial `L.map(...)`, controls, pane/projection work, and
  other Leaflet objects that a 3D adapter cannot reuse.

The renderer-coupled classification is:

| File | Camera | Layer lifecycle | Interaction | Layout/resize | Leaflet-only | Total |
|------|-------:|----------------:|------------:|--------------:|-------------:|------:|
| `web/app.js` | 8 | 36 | 5 | 4 | 27 | 80 |
| `web/buildings.js` | 5 | 2 | 1 | 0 | 4 | 12 |
| `web/landslides.js` | 0 | 2 | 0 | 0 | 4 | 6 |
| **Total** | **13** | **40** | **6** | **4** | **35** | **98** |

## Literal `map.*` Extraction Checklist

Line numbers identify each current direct-call site. A comma-separated range has
one classification and should move as one concern during adapter extraction.

### `web/app.js`

| Lines | Classification | Responsibility |
|-------|----------------|----------------|
| 110-114 | Leaflet-only | Reference/event pane creation and styling |
| 115 | Interaction | Clear selected MMI band on map click |
| 358, 366 | Leaflet-only | Wrapped hover-query coordinate projection |
| 374, 429 | Interaction | Overlay mousemove/mouseout listeners |
| 382 | Layer lifecycle | Ignore hidden overlay during hit testing |
| 461-462 | Layer lifecycle | Preserve visibility while rebuilding overlay |
| 475 | Leaflet-only | Leaflet zoom-control placement |
| 484-485 | Layer lifecycle | Remove selected raster basemap |
| 592 | Layer lifecycle | Disable reference overlay |
| 693-699 | Leaflet-only | PGA pane creation and styling |
| 707 | Layer lifecycle | Replace PGA raster layer |
| 1130, 1157, 1159, 1163 | Leaflet-only | MMI sweep SVG and layer-point projection |
| 1169, 1189 | Leaflet-only | MMI sweep move/zoom synchronization lifecycle |
| 1204 | Layer lifecycle | Remove current MMI layer |
| 1281-1286 | Leaflet-only | MMI loader pane creation and styling |
| 1350 | Layer lifecycle | Remove MMI loading marker |
| 1380 | Layer lifecycle | Replace manual-event epicenter marker |
| 1392-1393 | Camera | Frame manual MMI result or event |
| 1583, 1585 | Layer lifecycle | Clear comparison layers and legend control |
| 1611 | Camera | Center selected catalog event |
| 1615 | Layer lifecycle | Replace catalog-event epicenter marker |
| 1620, 1622 | Camera | Frame catalog MMI result or event |
| 1900 | Layout/resize | Resize after exposure-strip change |
| 2235, 2238 | Layer lifecycle | Enter comparison mode |
| 2255 | Camera | Frame comparison geometry |
| 2256, 2266, 2269 | Layer lifecycle | Replace/clear comparison legend and layers |
| 2474 | Layer lifecycle | Replace map-event layer |
| 2487 | Camera | Frame visible map events |
| 2530, 2535, 2541 | Layer lifecycle | Synchronize plate annotations |
| 2753 | Layout/resize | Restore map after Dashboard |
| 3489 | Layout/resize | Restore map after expanded Forecast |
| 3673, 3678-3679 | Layer lifecycle | Section-switch map-event cleanup |
| 3724 | Layout/resize | Restore map after Elements at Risk |

### `web/buildings.js`

| Lines | Classification | Responsibility |
|-------|----------------|----------------|
| 90-96 | Leaflet-only | Building pane creation and styling |
| 114 | Camera | Read viewport and zoom for district reconciliation |
| 121 | Layer lifecycle | Remove district layer outside desired set |
| 150 | Camera | Read zoom for availability state |
| 206-209 | Camera | Frame selected district at minimum usable zoom |
| 253 | Interaction | Reconcile districts after settled movement |

### `web/landslides.js`

| Lines | Classification | Responsibility |
|-------|----------------|----------------|
| 16-18 | Leaflet-only | Landslide pane creation and styling |
| 142 | Layer lifecycle | Remove disabled regional raster |

The associated `.addTo(map)` sites are included in the broader 98-site renderer
inventory and remain paired with their corresponding lifecycle rows above.

## Camera

The initial Leaflet camera is created at `web/app.js:109`. Later camera changes
come from manual intensity results, catalog events, comparisons, map-event
framing, and district selection.

The mode coordinator needs only one Leaflet `moveend` publisher. Instrumenting
every `setView()` and `fitBounds()` caller would create a shallow interface and
duplicate synchronization logic.

Building reconciliation consumes camera state in `web/buildings.js` through
`getBounds()`, `getZoom()`, `getBoundsZoom()`, `setView()`, and `fitBounds()`.

## Layer Lifecycle

`web/app.js` directly manages:

- raster basemap replacement
- reference overlay creation/rebuilding
- PGA raster lifecycle
- current MMI and epicenter lifecycle
- comparison footprints
- map-event bubbles and plate annotations
- temporary loaders and Leaflet controls

`web/buildings.js` adds and removes viewport-intersecting district layers.

`web/landslides.js` adds and removes one raster PMTiles layer per enabled region.

Shared state must contain visibility and data, never Leaflet layer instances.

## Interaction

Leaflet-specific interaction includes map-click MMI deselection, vector-tile
hover hit-testing, tooltip projection, event selection, and move-settle building
reconciliation. Equivalent MapLibre handlers belong inside the 3D adapter.

## Layout and Resize

Leaflet `invalidateSize()` is called after the exposure strip changes and after
Dashboard, expanded Forecast, and Elements at Risk close. These callers should
move to `mapModes.resize()` so each adapter performs its own resize operation.

## Leaflet-only Implementation

Pane construction, SVG MMI sweep projection, Protomaps symbolizers, Leaflet
controls, `latLngToLayerPoint()`, and pane DOM access remain private to the 2D
adapter. They are not part of normalized shared state.

## Tracer-Bullet Publication Seams

1. **Camera:** one initial state plus one settled-camera publisher near primary
   map initialization.
2. **Current event:** `updateCurrentEventCard()` already emits
   `eqmon:current-event` for event and clear states.
3. **Current MMI:** `renderCurrentMmiLayer()` plus
   `setCurrentMmiVisible()`; selected-band state is a later extension.
4. **Buildings:** district selection and the completed active-district set after
   `reconcile()`.

## Risks Carried Into Phase 1

- Camera updates need origin/suppression metadata to prevent feedback loops.
- Event and MMI updates are sequential rather than atomic.
- Comparison mode bypasses the normal current-MMI render path.
- Manual and catalog event payloads are heterogeneous.
- Building selection and active viewport districts are different concepts.
- Hidden renderer lifecycle must not retain duplicate listeners or controls.
