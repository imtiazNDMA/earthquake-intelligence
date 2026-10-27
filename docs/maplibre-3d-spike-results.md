# MapLibre 3D Phase 0 Spike Results

Date: 2026-08-25

Environment: project development machine, Windows, headless Microsoft Edge,
1440x900 viewport, FastAPI serving real project assets and building proxy routes.

## Versions

- MapLibre GL JS 5.7.1
- PMTiles JavaScript 4.3.0
- AWS Open Data Terrarium elevation tiles

## Sources Exercised

- Token-free OpenStreetMap raster basemap:
  `https://tile.openstreetmap.org/{z}/{x}/{y}.png`, tile size 256.
- Terrarium raster DEM:
  `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`,
  tile size 256, max zoom 15, encoding `terrarium`, pitch 55, bearing 0,
  terrain exaggeration 1.0, and hillshade exaggeration 0.28.
- Camera: center `[73.55, 34.2]` in `[lon, lat]` order, zoom 12.5.
- District vector source: `pmtiles://<origin>/tiles/districts.pmtiles`, source
  layer `districts`, rendered with fill and line layers.
- Landslide raster source: `pmtiles://<origin>/landslides/ajk.pmtiles`, tile size
  256, opacity 0.62, nearest resampling.
- Building vector source:
  `<origin>/buildings/tiles/Muzaffarabad_buildings/{z}/{x}/{y}.pbf`, source layer
  `buildings`, min zoom 12, max zoom 17.
- Building extrusion expression: positive numeric `height` is used directly;
  other values render at a flat height of 1. Height-band thresholds are 1, 3,
  8, and 15 metres with the existing Unknown/low/storey/mid/high colors.

## Result

```json
{
  "webgl": true,
  "style": true,
  "terrain": true,
  "boundaryFeatures": 21,
  "landslide": true,
  "buildingFeatures": 22678,
  "buildingHeight": 12.547640800476074,
  "styleMs": 22,
  "readyMs": 2748,
  "fps": 62,
  "heapMb": 54,
  "errors": [],
  "complete": true
}
```

`styleMs` measures MapLibre construction to style load. `readyMs` measures cold
3D construction to first fully idle view with all sampled sources loaded. It is
the Phase 0 proxy for first 3D activation; warm mode switching does not exist yet
and must be measured after Phase 1.

The FPS value is a one-second headless animation-frame sample, not a GPU profile.
The metrics establish compatibility only; Phase 9 owns production budgets.

The existing 2D application was measured separately on the same development
machine and browser: DOM content loaded at 1,123 ms, window load completed at
1,329 ms, and the first Leaflet tile was visible at 1,367 ms. Final measurements
on the intended operations-room hardware remain a Phase 9 release gate.

## Building Height Semantics

The source `height` property is interpreted in metres. Positive finite values
drive extrusion height directly. The existing 2D rule in `web/buildings.js`
treats the upstream `-1` sentinel, zero, negative, non-numeric, and non-finite
values as Unknown height. The 3D adapter must give those features a small flat
height and the existing Unknown color, never a fabricated measured height.

## Conclusion

All five Phase 0 compatibility checks passed. No token or backend change is
required for the tracer bullet. The temporary HTML spike was deleted after this
result was captured.
