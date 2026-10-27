/* Building height bands and viewport decisions, shared by the 2D canvas
 * renderer (buildings.js) and the 3D extrusions (maplibre-3d.js) so the legend,
 * the colours, and the live-source budget can never diverge between modes.
 */
(function () {
  "use strict";

  const BANDS = [
    { max: 3,        label: "Low-rise (≤3 m)",    color: "#C8C1B2" },
    { max: 8,        label: "2–3 storey (3–8 m)", color: "#D8B22C" },
    { max: 15,       label: "Mid-rise (8–15 m)",  color: "#E08A34" },
    { max: Infinity, label: "High-rise (>15 m)",  color: "#DD5730" },
  ];
  const UNKNOWN = { label: "Unknown height", color: "#5A6570" };

  // Upstream uses -1 for "no height data"; treat 0/negative/non-finite alike.
  const UNKNOWN_HEIGHT_M = 2;
  const OPACITY = 0.75;
  const DATA_MAXZOOM = 17;
  const MAX_LIVE_SOURCES = 6;
  const HEIGHT_PROP = "height";

  const tileUrl = id => `/buildings/tiles/${id}/{z}/{x}/{y}.pbf`;

  function heightBand(height) {
    if (typeof height !== "number" || !isFinite(height) || height <= 0) return UNKNOWN;
    return BANDS.find(band => height <= band.max);
  }

  // bounds = [minLon, minLat, maxLon, maxLat]; view is any Leaflet/MapLibre bounds.
  function intersects(bounds, view) {
    return !(bounds[0] > view.getEast() || bounds[2] < view.getWest() ||
             bounds[1] > view.getNorth() || bounds[3] < view.getSouth());
  }

  function centerOf(bounds) {
    return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
  }

  function distanceFrom(center, bounds) {
    const [lon, lat] = centerOf(bounds);
    return Math.hypot(lon - center[0], lat - center[1]);
  }

  // Never more than `cap` districts live at once: past that the nearest to the
  // viewport centre win, so a long pan evicts what it left behind.
  function visibleDistricts(catalog, view, zoom, minZoom, selectedId, cap = MAX_LIVE_SOURCES) {
    if (!Array.isArray(catalog) || zoom < minZoom) return [];
    const pool = selectedId ? catalog.filter(d => d.id === selectedId) : catalog;
    const inView = pool.filter(d => Array.isArray(d.bounds) && intersects(d.bounds, view));
    if (inView.length <= cap) return inView.map(d => d.id);
    const center = [(view.getWest() + view.getEast()) / 2, (view.getSouth() + view.getNorth()) / 2];
    return inView
      .sort((a, b) => distanceFrom(center, a.bounds) - distanceFrom(center, b.bounds))
      .slice(0, cap)
      .map(d => d.id);
  }

  const heightExpression = () => [
    "let", "h", ["to-number", ["get", HEIGHT_PROP], -1],
    // A missing height gets a stub, not a guess: it must never read as a tower.
    ["case", [">", ["var", "h"], 0], ["var", "h"], UNKNOWN_HEIGHT_M],
  ];

  const colorExpression = () => [
    "let", "h", ["to-number", ["get", HEIGHT_PROP], -1],
    ["case",
      ["<=", ["var", "h"], 0], UNKNOWN.color,
      ...BANDS.slice(0, -1).flatMap(band => [["<=", ["var", "h"], band.max], band.color]),
      BANDS[BANDS.length - 1].color],
  ];

  window.eqmonBuildingsConfig = {
    BANDS,
    UNKNOWN,
    UNKNOWN_HEIGHT_M,
    OPACITY,
    DATA_MAXZOOM,
    MAX_LIVE_SOURCES,
    HEIGHT_PROP,
    tileUrl,
    heightBand,
    intersects,
    visibleDistricts,
    heightExpression,
    colorExpression,
  };
})();
