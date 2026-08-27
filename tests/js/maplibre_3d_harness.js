/* Exercises web/maplibre-3d.js against a stub MapLibre: style construction,
   basemap swapping, terrain fallback, and the Phase 4 analysis layers.

   The stub records what the adapter asked MapLibre to do, so the assertions are
   about behaviour (which paint value, which geometry) rather than source text. */
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const intents = [];
const sandbox = {
  console: { warn() {}, error() {} },
  setTimeout, clearTimeout,
  devicePixelRatio: 1,
  location: { href: "http://localhost:8000/", origin: "http://localhost:8000" },
  URL,
  Date,
  Set,
};
sandbox.window = sandbox;

// --- stub DOM -------------------------------------------------------------
function stubElement(tag) {
  return {
    tag, dataset: {}, style: {}, className: "", innerHTML: "",
    listeners: {}, setAttribute() {}, appendChild() {}, remove() {},
    addEventListener(event, fn) { (this.listeners[event] ||= []).push(fn); }, querySelectorAll: () => [],
  };
}
const head = { children: [], appendChild(node) { this.children.push(node); } };
// The stylesheet is reported as already loaded, so no network wait is possible.
const loadedCss = stubElement("link");
loadedCss.dataset.loaded = "true";
sandbox.document = {
  head,
  documentElement: { dataset: { theme: "light" } },
  createElement: stubElement,
  getElementById: id => (id === "maplibre-gl-css" ? loadedCss : null),
};

// --- stub MapLibre --------------------------------------------------------
let lastMap = null;

function makeMap(options) {
  const geojson = {};
  Object.entries(options.style.sources).forEach(([id, spec]) => {
    if (spec.type === "geojson") geojson[id] = { data: spec.data, setData(next) { this.data = next; } };
  });
  const canvas = stubElement("canvas");
  return {
    options,
    layerDefs: options.style.layers.map(layer => ({ ...layer })),
    paint: {},
    layout: {},
    sourceFeatures: {},
    renderedByLayer: {},
    queries: [],
    sources: geojson,
    rasterSpecs: { ...options.style.sources },
    terrain: null,
    styleReady: true,
    sky: options.style.sky,
    markers: [],
    handlers: {},
    onceHandlers: {},
    once(event, fn) {
      if (event === "load" || event === "idle") { fn(); return; }
      (this.onceHandlers[event] ||= []).push(fn);
    },
    on(event, second, third) {
      const key = third ? `${event}:${second}` : event;
      (this.handlers[key] ||= []).push(third || second);
    },
    off(event, fn) {
      if (!this.handlers[event]) return;
      this.handlers[event] = this.handlers[event].filter(handler => handler !== fn);
    },
    isStyleLoaded() { return this.styleReady; },
    getCanvas: () => canvas,
    addControl(control) { this.control = control; },
    touchZoomRotate: { disableRotation() { lastMap.rotationDisabled = true; } },
    getSource(id) { return this.sources[id] || this.rasterSpecs[id]; },
    setPaintProperty(layer, prop, value) { (this.paint[layer] ||= {})[prop] = value; },
    setLayoutProperty(layer, prop, value) { (this.layout[layer] ||= {})[prop] = value; },
    querySourceFeatures(sourceId, options) {
      return this.sourceFeatures[`${sourceId}:${options.sourceLayer}`] || [];
    },
    setTerrain(value) { this.terrain = value; },
    setSky(value) { this.sky = value; },
    getStyle() { return { layers: this.layerDefs }; },
    getLayer(id) { return this.layerDefs.find(layer => layer.id === id); },
    removeLayer(id) { this.layerDefs = this.layerDefs.filter(layer => layer.id !== id); },
    removeSource(id) { delete this.rasterSpecs[id]; },
    addSource(id, spec) { this.rasterSpecs[id] = spec; },
    addLayer(layer, before) {
      const at = before ? this.layerDefs.findIndex(l => l.id === before) : this.layerDefs.length;
      this.layerDefs.splice(at < 0 ? this.layerDefs.length : at, 0, layer);
    },
    resize() {},
    stop() { this.stopped = true; },
    triggerRepaint() { this.repainted = true; },
    jumpTo() {},
    // Replacing the style throws away every layer, source, and the terrain mesh,
    // exactly as MapLibre does.
    setStyle(style) {
      this.layerDefs = style.layers.map(layer => ({ ...layer }));
      this.rasterSpecs = { ...style.sources };
      this.sources = {};
      Object.entries(style.sources).forEach(([id, spec]) => {
        if (spec.type === "geojson") this.sources[id] = { data: spec.data, setData(next) { this.data = next; } };
      });
      this.paint = {};
      this.layout = {};
      this.sky = style.sky;
      this.terrain = null;
      // Real MapLibre reports styledata before the style will accept paint or
      // sky calls, so the stub does too.
      this.styleReady = false;
      (this.handlers.styledata || []).slice().forEach(fn => fn());
      this.styleReady = true;
      (this.handlers.styledata || []).slice().forEach(fn => fn());
    },
    view: { zoom: options.zoom, bounds: [60, 20, 80, 40] },
    getZoom() { return this.view.zoom; },
    getCenter() {
      const [west, south, east, north] = this.view.bounds;
      return { lng: (west + east) / 2, lat: (south + north) / 2 };
    },
    getBearing: () => 0,
    getPitch: () => 55,
    getBounds() {
      const [west, south, east, north] = this.view.bounds;
      return { getWest: () => west, getSouth: () => south, getEast: () => east, getNorth: () => north };
    },
    moveTo(zoom, bounds) {
      this.view = { zoom, bounds };
      (this.handlers.moveend || []).forEach(handler => handler());
    },
    queryRenderedFeatures(geometry, options) {
      this.queries.push({ geometry, layers: options?.layers });
      for (const layer of options?.layers || []) {
        const hits = this.renderedByLayer[layer];
        if (hits) return hits;
      }
      return [];
    },
  };
}

class StubPopup {
  constructor(options) { this.options = options; }
  setText(text) { this.text = text; return this; }
  setHTML(html) { this.html = html; return this; }
  setLngLat(lngLat) { this.lngLat = lngLat; return this; }
  addTo() { return this; }
}

class StubMarker {
  constructor(options) { this.element = options.element; this.removed = false; }
  setPopup(popup) { this.popup = popup; return this; }
  getPopup() { return this.popup; }
  setLngLat(lngLat) { this.lngLat = lngLat; return this; }
  addTo(map) {
    // Real MapLibre reads the coordinate while attaching and throws without
    // one, so the stub refuses an unpositioned marker too.
    if (!this.lngLat) throw new TypeError("marker added before it was positioned");
    map.markers.push(this);
    return this;
  }
  remove() { this.removed = true; }
}

sandbox.maplibregl = {
  Map: function (options) { lastMap = makeMap(options); return lastMap; },
  Popup: StubPopup,
  Marker: StubMarker,
  NavigationControl: function (options) { this.options = options; },
  addProtocol() { sandbox.protocolAdded = true; },
};
sandbox.pmtiles = { Protocol: function () { this.tile = () => {}; } };
const VECTOR_STYLE = {
  version: 8,
  name: "dark",
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: { openmaptiles: { type: "vector", url: "https://tiles.openfreemap.org/planet" } },
  layers: [
    { id: "background", type: "background" },
    { id: "water", type: "fill", source: "openmaptiles", "source-layer": "water" },
    { id: "place-labels", type: "symbol", source: "openmaptiles", "source-layer": "place" },
  ],
};
sandbox.fetch = url => Promise.resolve({
  ok: url.startsWith("https://tiles.openfreemap.org/styles/"),
  status: 200,
  json: () => Promise.resolve(JSON.parse(JSON.stringify(VECTOR_STYLE))),
});
sandbox.window.eqmonMapModes = {
  emit: (name, payload) => intents.push([name, payload]),
  // The offset the coordinator owns: 256px tiles in 2D against 512px in 3D.
  toLeafletZoom: zoom => zoom + 1,
  toMapLibreZoom: zoom => zoom - 1,
};

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("web/map-style-config.js", "utf8"), sandbox, { filename: "map-style-config.js" });
vm.runInContext(fs.readFileSync("web/overlay-format.js", "utf8"), sandbox, { filename: "overlay-format.js" });
vm.runInContext(fs.readFileSync("web/buildings-config.js", "utf8"), sandbox, { filename: "buildings-config.js" });
vm.runInContext(fs.readFileSync("web/maplibre-3d.js", "utf8"), sandbox, { filename: "maplibre-3d.js" });
const adapter = sandbox.window.eqmonMapLibre3d;

const MMI_FC = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", properties: { mmi_lower: 5, color: "#7aff93" },
      geometry: { type: "Polygon", coordinates: [[[69, 30], [70, 30], [70, 31], [69, 30]]] } },
    { type: "Feature", properties: { mmi_lower: 7, color: "#ffc800" },
      geometry: { type: "Polygon", coordinates: [[[69, 30], [69.5, 30], [69.5, 30.5], [69, 30]]] } },
  ],
};

(async () => {
  await adapter.ensureMapLibre3d({ center: [69.3, 30.4], zoom: 4, bearing: 0, pitch: 55 });
  const map = lastMap;

  // --- style ---------------------------------------------------------------
  const layerIds = map.layerDefs.map(layer => layer.id);
  assert.deepStrictEqual(JSON.stringify(layerIds), JSON.stringify([
    "basemap", "terrain-hillshade", "current-mmi-fill", "current-mmi-line", "map-events-circle",
  ]), `unexpected layer order: ${layerIds}`);
  // Stronger bands must sort above weaker ones or they vanish under them.
  const fill = map.getLayer("current-mmi-fill");
  assert.deepStrictEqual(JSON.stringify(fill.layout["fill-sort-key"]), JSON.stringify(["get", "mmi_lower"]));
  // Terrain came up at true scale.
  assert.strictEqual(map.terrain.exaggeration, 1);
  assert.strictEqual(adapter.hasTerrain(), true);
  // Gestures: touch drag stays a pan.
  assert.strictEqual(map.options.touchPitch, false);
  assert.strictEqual(map.rotationDisabled, true);
  assert.strictEqual(map.control.options.showCompass, true);

  adapter.setPaused(true);
  assert.strictEqual(map.stopped, true);
  assert.strictEqual(adapter.isPaused(), true);
  adapter.setPaused(false);
  assert.strictEqual(map.repainted, true);

  let rendererFailure = null;
  adapter.onRendererFailure(error => { rendererFailure = error; });
  let prevented = false;
  map.getCanvas().listeners.webglcontextlost[0]({ preventDefault() { prevented = true; } });
  assert.strictEqual(prevented, true);
  assert.ok(rendererFailure.message.includes("context lost"));

  // --- basemap swap --------------------------------------------------------
  assert.strictEqual(adapter.getBasemap(), "OpenStreetMap");
  adapter.applyState({ basemap: "Topographic", theme: "light" });
  assert.strictEqual(adapter.getBasemap(), "Topographic");
  // Rebuilt, so the new zoom ceiling actually takes effect...
  assert.strictEqual(map.rasterSpecs.basemap.maxzoom, 17);
  // ...and the basemap stays underneath everything else.
  assert.strictEqual(map.layerDefs[0].id, "basemap");
  assert.strictEqual(map.layerDefs.length, 5);

  // --- theme ---------------------------------------------------------------
  adapter.applyState({ basemap: "Topographic", theme: "dark" });
  assert.strictEqual(map.sky["sky-color"], "#0d141c");
  adapter.applyState({ basemap: "Topographic", theme: "light" });
  assert.strictEqual(map.sky["sky-color"], "#8fb3d9");

  // --- MMI bands -----------------------------------------------------------
  adapter.applyState({
    currentMmi: { featureCollection: MMI_FC, visible: true, opacity: 0.6, selectedLevel: null, hoveredLevel: null },
  });
  assert.strictEqual(map.sources["current-mmi"].data.features.length, 2);
  // No selection: every band sits at the published opacity.
  assert.strictEqual(map.paint["current-mmi-fill"]["fill-opacity"], 0.6);
  assert.strictEqual(map.paint["current-mmi-line"]["line-width"], 1);

  adapter.applyState({
    currentMmi: {
      featureCollection: MMI_FC, visible: true, opacity: 0.6,
      selectedLevel: 7, hoveredLevel: 5,
      emphasis: { selected: { weight: 3, fillOpacity: 0.8 }, hovered: { weight: 2.5, fillOpacity: 0.7 } },
    },
  });
  assert.deepStrictEqual(
    JSON.stringify(map.paint["current-mmi-fill"]["fill-opacity"]),
    JSON.stringify(["case", ["==", ["get", "mmi_lower"], 7], 0.8, ["==", ["get", "mmi_lower"], 5], 0.7, 0.6]),
    "selected and hovered bands must take the 2D emphasis"
  );
  assert.deepStrictEqual(
    JSON.stringify(map.paint["current-mmi-line"]["line-width"]),
    JSON.stringify(["case", ["==", ["get", "mmi_lower"], 7], 3, ["==", ["get", "mmi_lower"], 5], 2.5, 1])
  );

  // Hidden means no geometry, so hit testing cannot find an invisible band.
  adapter.applyState({ currentMmi: { featureCollection: MMI_FC, visible: false, opacity: 0.6 } });
  assert.strictEqual(map.sources["current-mmi"].data.features.length, 0);

  // --- event bubbles -------------------------------------------------------
  adapter.applyState({
    mapEvents: {
      events: [
        { lat: 34.37, lon: 73.47, symbol: { radius: 9.1, color: "#E15A43", strokeWidth: 1.4 },
          popupHtml: "<b>Muzaffarabad</b>", ariaLabel: "Muzaffarabad, magnitude 6.2, depth 12.0 km" },
        { lat: null, lon: null, symbol: { radius: 3, color: "#6E7B85", strokeWidth: 1.4 } },
      ],
      opacity: 0.7,
      strokeColor: "#F4F6F8",
    },
  });
  const eventFeatures = map.sources["map-events"].data.features;
  // The event without coordinates is dropped rather than drawn at null island.
  assert.strictEqual(eventFeatures.length, 1);
  assert.deepStrictEqual(JSON.stringify(eventFeatures[0].geometry.coordinates), JSON.stringify([73.47, 34.37]));
  assert.strictEqual(eventFeatures[0].properties.radius, 9.1);
  assert.strictEqual(eventFeatures[0].properties.color, "#E15A43");
  assert.strictEqual(map.paint["map-events-circle"]["circle-opacity"], 0.7);

  // --- epicenter -----------------------------------------------------------
  adapter.applyState({ activeEvent: { lat: 34.37, lon: 73.47, magnitude: 6.2, epicenterLabel: "Epicenter — M6.2" } });
  assert.strictEqual(map.markers.length, 1);
  assert.deepStrictEqual(JSON.stringify(map.markers[0].lngLat), JSON.stringify([73.47, 34.37]));
  assert.strictEqual(map.markers[0].popup.text, "Epicenter — M6.2");
  assert.ok(map.markers[0].element.innerHTML.includes("epicenter-3d-pulse"));
  // Moving the event reuses the one marker instead of stacking new ones.
  adapter.applyState({ activeEvent: { lat: 24.86, lon: 67.0, epicenterLabel: "Epicenter" } });
  assert.strictEqual(map.markers.length, 1);
  assert.deepStrictEqual(JSON.stringify(map.markers[0].lngLat), JSON.stringify([67.0, 24.86]));
  // Clearing the active event takes the marker away.
  adapter.applyState({ activeEvent: null });
  assert.strictEqual(map.markers[0].removed, true);

  // --- intents -------------------------------------------------------------
  // A band click reports intent; it does not mutate anything locally.
  const bandClick = map.handlers["click:current-mmi-fill"][0];
  bandClick({ features: [{ properties: { mmi_lower: 7 } }] });
  assert.deepStrictEqual(JSON.stringify(intents.at(-1)), JSON.stringify(["selectMmiBand", 7]));
  const bandHover = map.handlers["mousemove:current-mmi-fill"][0];
  bandHover({ features: [{ properties: { mmi_lower: 5 } }] });
  assert.deepStrictEqual(JSON.stringify(intents.at(-1)), JSON.stringify(["hoverMmiBand", 5]));
  // Bare map clears the selection, as clicking the 2D map does.
  const mapClick = map.handlers.click.at(-1);
  mapClick({ point: [10, 10] });
  assert.strictEqual(intents.at(-1)[0], "clearMmiSelection");
  // An event click opens the popup the 2D map would have shown, verbatim.
  const eventClick = map.handlers["click:map-events-circle"][0];
  eventClick({ features: [{ properties: { popupHtml: "<b>Muzaffarabad</b>" }, geometry: { coordinates: [73.47, 34.37] } }] });

  // --- reference overlays (Phase 5) ---------------------------------------
  const OVERLAYS = {
    National: {
      id: "national", visible: true, color: "#444", width: 1.5, opacity: 1,
      fillColor: null, fillOpacity: null, lineOnly: false, faultStyle: false,
      namedFill: null, categorical: null, hover: null,
    },
    "Major Faults": {
      id: "major_faults", visible: false, color: "#A67C1F", width: 1.4, opacity: 0.95,
      fillColor: null, fillOpacity: null, lineOnly: true, faultStyle: true,
      namedFill: null, categorical: null,
      hover: {
        fields: ["FAULTNAME", "Fault_Type", "Mmax", "Slip_rate"],
        labels: { FAULTNAME: null, Fault_Type: "Type", Mmax: "Mmax", Slip_rate: "Slip rate" },
        units: { Slip_rate: "mm/yr" },
        tolerancePx: 12,
      },
    },
    "PGA Zones": {
      id: "pga_zones", visible: true, color: "#232323", width: 0.6, opacity: 0.55,
      fillColor: null, fillOpacity: 0.55, lineOnly: false, faultStyle: false,
      namedFill: null,
      categorical: { prop: "PGA", colors: { "Zone 1": "#53741a", "Zone 2A": "#16381d" } },
      hover: { fields: ["PGA"], labels: { PGA: null }, units: null, tolerancePx: 0 },
    },
    "Tectonic Zones": {
      id: "pak_tectonic_zones", visible: true, color: "#8C5A3C", width: 0.5, opacity: 0.7,
      fillColor: "#8C5A3C", fillOpacity: 0.3, lineOnly: false, faultStyle: false,
      namedFill: "Name", categorical: null, hover: null,
    },
  };

  adapter.applyState({ overlays: OVERLAYS });

  // Vector sources point at the same archives the 2D map reads.
  assert.strictEqual(map.rasterSpecs["overlay-national"].type, "vector");
  assert.ok(map.rasterSpecs["overlay-national"].url.endsWith("/tiles/national.pmtiles"));
  assert.ok(map.rasterSpecs["overlay-national"].url.startsWith("pmtiles://"));

  // Line-only overlays get no fill layer; filled ones do.
  assert.strictEqual(map.getLayer("overlay-national-fill"), undefined);
  assert.ok(map.getLayer("overlay-national-line"));
  assert.ok(map.getLayer("overlay-pga_zones-fill"));

  // Overlays sit above MMI and below the event bubbles, matching the 2D panes.
  const order = map.layerDefs.map(layer => layer.id);
  assert.ok(order.indexOf("overlay-national-line") > order.indexOf("current-mmi-line"),
    `overlays must draw above MMI: ${order}`);
  assert.ok(order.indexOf("overlay-national-line") < order.indexOf("map-events-circle"),
    `overlays must draw below events: ${order}`);

  // Default visibility is carried through, not assumed.
  assert.strictEqual(map.getLayer("overlay-national-line").layout.visibility, "visible");
  assert.strictEqual(map.getLayer("overlay-major_faults-line").layout.visibility, "none");

  // Published PGA zone colours are reproduced exactly, and an unlisted class
  // stays transparent rather than borrowing one.
  assert.deepStrictEqual(
    JSON.stringify(map.getLayer("overlay-pga_zones-fill").paint["fill-color"]),
    JSON.stringify(["match", ["get", "PGA"], "Zone 1", "#53741a", "Zone 2A", "#16381d", "rgba(0,0,0,0)"])
  );

  // Pitch widens lines so they carry the same weight as they do flat.
  assert.strictEqual(map.getLayer("overlay-national-line").paint["line-width"], 1.5 * 1.25);

  // --- toggling and editing ------------------------------------------------
  const layersBefore = map.layerDefs.length;
  const sourcesBefore = Object.keys(map.rasterSpecs).length;
  adapter.applyState({
    overlays: {
      ...OVERLAYS,
      National: { ...OVERLAYS.National, visible: false, color: "#111", width: 3, opacity: 0.4 },
      "Major Faults": { ...OVERLAYS["Major Faults"], visible: true },
    },
  });
  // Toggling edits layers in place; it never accumulates duplicates.
  assert.strictEqual(map.layerDefs.length, layersBefore, "layers were duplicated on toggle");
  assert.strictEqual(Object.keys(map.rasterSpecs).length, sourcesBefore, "sources were duplicated");
  assert.strictEqual(map.layout["overlay-national-line"].visibility, "none");
  assert.strictEqual(map.layout["overlay-major_faults-line"].visibility, "visible");
  assert.strictEqual(map.paint["overlay-national-line"]["line-color"], "#111");
  assert.strictEqual(map.paint["overlay-national-line"]["line-width"], 3 * 1.25);
  assert.strictEqual(map.paint["overlay-national-line"]["line-opacity"], 0.4);

  // --- name-hashed fill ----------------------------------------------------
  // The pastel lookup can only be built once tile features exist.
  map.sourceFeatures["overlay-pak_tectonic_zones:pak_tectonic_zones"] = [
    { properties: { Name: "Kirthar Fold Belt" } },
    { properties: { Name: "Sulaiman Lobe" } },
    { properties: { Name: "Kirthar Fold Belt" } },
  ];
  adapter.applyState({ overlays: OVERLAYS });
  const namedFill = map.paint["overlay-pak_tectonic_zones-fill"]["fill-color"];
  const format = sandbox.window.eqmonOverlayFormat;
  assert.deepStrictEqual(
    JSON.stringify(namedFill),
    JSON.stringify(["match", ["get", "Name"],
      "Kirthar Fold Belt", format.pastelFromName("Kirthar Fold Belt"),
      "Sulaiman Lobe", format.pastelFromName("Sulaiman Lobe"),
      "rgba(0,0,0,0)"]),
    "tectonic pastels must match the shared hash, once per distinct name"
  );

  // --- hover ---------------------------------------------------------------
  // Only visible overlays are hit tested, so turn the fault layer back on.
  adapter.applyState({
    overlays: { ...OVERLAYS, "Major Faults": { ...OVERLAYS["Major Faults"], visible: true } },
  });
  map.renderedByLayer["overlay-major_faults-line"] = [{
    properties: { FAULTNAME: "Chaman Fault", Fault_Type: "Strike-slip", Mmax: 7.8, Slip_rate: 10 },
  }];
  const hover = map.handlers.mousemove.at(-1);
  hover({ point: { x: 100, y: 100 }, lngLat: [69, 30] });
  // Exactly the 2D tooltip: unlabelled name in bold, configured labels, units.
  assert.strictEqual(
    format.tooltipHtml("Major Faults", {
      hoverFields: OVERLAYS["Major Faults"].hover.fields,
      hoverLabels: OVERLAYS["Major Faults"].hover.labels,
      hoverUnits: OVERLAYS["Major Faults"].hover.units,
    }, map.renderedByLayer["overlay-major_faults-line"][0].properties),
    "<b>Chaman Fault</b><br>Type: Strike-slip<br>Mmax: 7.8<br>Slip rate: 10 mm/yr"
  );
  // A line overlay is queried with a padded box; its tolerance is 12px.
  const faultQuery = map.queries.at(-1);
  assert.deepStrictEqual(JSON.stringify(faultQuery.geometry),
    JSON.stringify([[88, 88], [112, 112]]), "hover box must use the configured tolerance");

  // A hidden overlay is never hit tested, so a tooltip cannot describe a layer
  // the operator has switched off.
  map.queries.length = 0;
  adapter.applyState({ overlays: OVERLAYS });   // Major Faults back to hidden
  hover({ point: { x: 100, y: 100 }, lngLat: [69, 30] });
  assert.ok(
    map.queries.every(query => !query.layers.includes("overlay-major_faults-line")),
    "a hidden overlay must not be hit tested"
  );


  // --- building extrusions (Phase 6) --------------------------------------
  const buildingsConfig = sandbox.window.eqmonBuildingsConfig;
  const CATALOG = [
    { id: "Lahore_buildings", label: "Lahore", bounds: [74.05, 31.25, 74.65, 31.71] },
    { id: "Sheikhupura_buildings", label: "Sheikhupura", bounds: [73.6, 31.4, 74.2, 32.0] },
    { id: "Karachi_buildings", label: "Karachi", bounds: [66.8, 24.7, 67.4, 25.1] },
  ];
  const buildingsState = (patch = {}) => ({
    enabled: true, selected: "", minZoom: 12, catalog: CATALOG,
    districts: [], opacity: 0.75, maxSources: 6, ...patch,
  });

  // Lahore only: Sheikhupura is off the east edge, Karachi is 700 km away.
  map.moveTo(12, [74.25, 31.2, 74.7, 31.6]);
  adapter.applyState({ buildings: buildingsState() });
  assert.deepStrictEqual(JSON.stringify(adapter.liveBuildingDistricts()), JSON.stringify(["Lahore_buildings"]));

  const extrusion = map.getLayer("buildings-Lahore_buildings-extrusion");
  assert.strictEqual(extrusion.type, "fill-extrusion");
  assert.strictEqual(extrusion["source-layer"], "buildings");
  // Below the catalog's minimum zoom the layer draws nothing, in MapLibre's scale.
  assert.strictEqual(extrusion.minzoom, 11);
  assert.strictEqual(extrusion.paint["fill-extrusion-opacity"], 0.75);
  assert.strictEqual(
    map.rasterSpecs["buildings-Lahore_buildings"].tiles[0],
    "http://localhost:8000/buildings/tiles/Lahore_buildings/{z}/{x}/{y}.pbf"
  );

  // Buildings are context: they draw under the shaking footprint and the events.
  const withBuildings = map.layerDefs.map(layer => layer.id);
  assert.ok(
    withBuildings.indexOf("buildings-Lahore_buildings-extrusion") < withBuildings.indexOf("current-mmi-fill"),
    `extrusions must draw below MMI: ${withBuildings}`
  );

  // Height and colour come from the same bands the legend prints, and an
  // unknown height is a 2 m stub in grey rather than anything tower-like.
  assert.deepStrictEqual(
    JSON.stringify(extrusion.paint["fill-extrusion-height"]),
    JSON.stringify(["let", "h", ["to-number", ["get", "height"], -1],
      ["case", [">", ["var", "h"], 0], ["var", "h"], 2]])
  );
  assert.deepStrictEqual(
    JSON.stringify(extrusion.paint["fill-extrusion-color"]),
    JSON.stringify(["let", "h", ["to-number", ["get", "height"], -1],
      ["case",
        ["<=", ["var", "h"], 0], "#5A6570",
        ["<=", ["var", "h"], 3], "#C8C1B2",
        ["<=", ["var", "h"], 8], "#D8B22C",
        ["<=", ["var", "h"], 15], "#E08A34",
        "#DD5730"]])
  );
  assert.strictEqual(buildingsConfig.heightBand(-1), buildingsConfig.UNKNOWN);
  assert.strictEqual(buildingsConfig.heightBand(40).color, "#DD5730");

  // Panning to another district evicts the one left behind, source included.
  map.moveTo(12, [66.9, 24.8, 67.3, 25.0]);
  assert.deepStrictEqual(JSON.stringify(adapter.liveBuildingDistricts()), JSON.stringify(["Karachi_buildings"]));
  assert.strictEqual(map.getLayer("buildings-Lahore_buildings-extrusion"), undefined);
  assert.strictEqual(map.rasterSpecs["buildings-Lahore_buildings"], undefined);

  // Below the minimum zoom nothing is live at all: no source, no request.
  map.moveTo(8, [60, 20, 80, 40]);
  assert.deepStrictEqual(JSON.stringify(adapter.liveBuildingDistricts()), JSON.stringify([]));

  // A wide view holds all three, but the cap keeps only the nearest to centre.
  map.moveTo(12, [66, 24, 75, 32]);
  assert.strictEqual(adapter.liveBuildingDistricts().length, 3);
  adapter.applyState({ buildings: buildingsState({ maxSources: 1 }) });
  assert.deepStrictEqual(JSON.stringify(adapter.liveBuildingDistricts()), JSON.stringify(["Karachi_buildings"]));

  // Selecting a district narrows the view to it alone.
  adapter.applyState({ buildings: buildingsState({ selected: "Lahore_buildings" }) });
  assert.deepStrictEqual(JSON.stringify(adapter.liveBuildingDistricts()), JSON.stringify(["Lahore_buildings"]));

  // Opacity is shared with 2D and edits in place.
  adapter.applyState({ buildings: buildingsState({ selected: "Lahore_buildings", opacity: 0.4 }) });
  assert.strictEqual(map.paint["buildings-Lahore_buildings-extrusion"]["fill-extrusion-opacity"], 0.4);

  // Switching the layer off tears every source down.
  adapter.applyState({ buildings: buildingsState({ enabled: false }) });
  assert.deepStrictEqual(JSON.stringify(adapter.liveBuildingDistricts()), JSON.stringify([]));
  assert.ok(Object.keys(map.rasterSpecs).every(id => !id.startsWith("buildings-")),
    "a disabled layer must leave no sources behind");

  // --- raster hazards (Phase 7) -------------------------------------------
  const landslides = {
    opacity: 0.62,
    active: ["AJK", "KP"],
    regions: [
      { key: "AJK", label: "Azad Jammu and Kashmir", url: "landslides/ajk.pmtiles", minZoom: 4, maxZoom: 13, enabled: true },
      { key: "GB", label: "Gilgit-Baltistan", url: "landslides/gb.pmtiles", minZoom: 4, maxZoom: 13, enabled: false },
      { key: "KP", label: "Khyber Pakhtunkhwa", url: "landslides/kp.pmtiles", minZoom: 4, maxZoom: 14, enabled: true },
      { key: "Baloch", label: "Balochistan", url: "landslides/baloch.pmtiles", minZoom: 4, maxZoom: 12, enabled: false },
    ],
  };
  const pga = {
    enabled: true, returnPeriod: 475, opacity: 0.55,
    bounds: [60.87, 23.81, 79.30, 37.09], image: "pga/pga_475.png",
    label: "475-year", attribution: "PGA model",
  };
  adapter.applyState({ landslides, pga });
  assert.strictEqual(map.rasterSpecs["landslide-AJK"].type, "raster");
  assert.ok(map.rasterSpecs["landslide-AJK"].url.startsWith("pmtiles://"));
  assert.strictEqual(map.getLayer("landslide-AJK-raster").layout.visibility, "visible");
  assert.strictEqual(map.getLayer("landslide-GB-raster").layout.visibility, "none");
  assert.strictEqual(map.getLayer("landslide-AJK-raster").paint["raster-resampling"], "nearest");
  assert.strictEqual(map.getLayer("pga-hazard-raster").paint["raster-resampling"], "nearest");
  assert.strictEqual(map.rasterSpecs["pga-hazard"].type, "image");
  assert.deepStrictEqual(JSON.stringify(map.rasterSpecs["pga-hazard"].coordinates),
    JSON.stringify([[60.87, 37.09], [79.30, 37.09], [79.30, 23.81], [60.87, 23.81]]));
  const hazardOrder = map.layerDefs.map(layer => layer.id);
  assert.ok(hazardOrder.indexOf("landslide-AJK-raster") < hazardOrder.indexOf("current-mmi-fill"));
  assert.ok(hazardOrder.indexOf("pga-hazard-raster") < hazardOrder.indexOf("current-mmi-fill"));

  // Toggling and opacity edit existing regional layers rather than duplicating them.
  const hazardLayerCount = map.layerDefs.length;
  const hazardSourceCount = Object.keys(map.rasterSpecs).length;
  adapter.applyState({
    landslides: {
      ...landslides, opacity: 0.3,
      regions: landslides.regions.map(region => ({ ...region, enabled: region.key === "GB" })),
    },
    pga: { ...pga, opacity: 0.25 },
  });
  assert.strictEqual(map.layerDefs.length, hazardLayerCount);
  assert.strictEqual(Object.keys(map.rasterSpecs).length, hazardSourceCount);
  assert.strictEqual(map.layout["landslide-AJK-raster"].visibility, "none");
  assert.strictEqual(map.layout["landslide-GB-raster"].visibility, "visible");
  assert.strictEqual(map.paint["landslide-GB-raster"]["raster-opacity"], 0.3);
  assert.strictEqual(map.getLayer("pga-hazard-raster").paint["raster-opacity"], 0.25);


  // --- vector basemaps -----------------------------------------------------
  // A keyless OpenFreeMap style replaces the whole MapLibre style, so everything
  // this renderer draws has to come back from the published state alone.
  const settle = () => new Promise(resolve => setTimeout(resolve, 0));
  const FULL_STATE = {
    basemap: "Dark",
    theme: "dark",
    overlays: OVERLAYS,
    currentMmi: { featureCollection: MMI_FC, visible: true, opacity: 0.45 },
    mapEvents: { events: [{ lat: 34.37, lon: 73.47, symbol: { radius: 9.1, color: "#E15A43", strokeWidth: 1.4 } }] },
    buildings: buildingsState({ selected: "Karachi_buildings" }),
    landslides,
    pga,
  };

  map.moveTo(13, [66.9, 24.8, 67.3, 25.0]);
  adapter.applyState(FULL_STATE);
  for (let i = 0; i < 5; i++) await settle();

  assert.strictEqual(adapter.getBasemap(), "Dark");
  const vectorOrder = map.layerDefs.map(layer => layer.id);
  // Relief slips under the basemap's own labels; analysis stays above them.
  assert.deepStrictEqual(JSON.stringify(vectorOrder.slice(0, 4)),
    JSON.stringify(["background", "water", "terrain-hillshade", "place-labels"]),
    `hillshade must sit under the labels: ${vectorOrder}`);
  assert.ok(vectorOrder.indexOf("current-mmi-fill") > vectorOrder.indexOf("place-labels"));
  // The style's own vector source survived alongside ours.
  assert.strictEqual(map.rasterSpecs.openmaptiles.type, "vector");
  // Terrain is rebuilt, because setStyle drops the mesh with everything else.
  assert.strictEqual(map.terrain.exaggeration, 1);
  // Published analysis is registered again, never refetched.
  assert.strictEqual(map.sources["current-mmi"].data.features.length, 2);
  assert.ok(map.getLayer("overlay-national-line"), "overlays were lost across the style swap");
  assert.ok(map.getLayer("buildings-Karachi_buildings-extrusion"), "extrusions were lost across the style swap");
  assert.ok(map.getLayer("landslide-AJK-raster"), "landslides were lost across the style swap");
  assert.ok(map.getLayer("pga-hazard-raster"), "PGA was lost across the style swap");

  // Going back to a raster basemap rebuilds the style the other way.
  adapter.applyState({ ...FULL_STATE, basemap: "OpenStreetMap", theme: "light" });
  for (let i = 0; i < 5; i++) await settle();
  assert.strictEqual(adapter.getBasemap(), "OpenStreetMap");
  assert.strictEqual(map.layerDefs[0].id, "basemap");
  assert.strictEqual(map.rasterSpecs.openmaptiles, undefined);
  assert.ok(map.getLayer("overlay-national-line"));


  // --- labelled satellite --------------------------------------------------
  // Imagery carries the vector style's place names and nothing else, with the
  // relief between them.
  adapter.applyState({ ...FULL_STATE, basemap: "Satellite + labels", theme: "light" });
  for (let i = 0; i < 5; i++) await settle();
  assert.strictEqual(adapter.getBasemap(), "Satellite + labels");
  const hybridOrder = map.layerDefs.map(layer => layer.id);
  assert.deepStrictEqual(JSON.stringify(hybridOrder.slice(0, 3)),
    JSON.stringify(["basemap", "terrain-hillshade", "place-labels"]),
    `labels must sit over the imagery: ${hybridOrder}`);
  // Only symbols survive the filter: the style's own background and fills would
  // hide the imagery they are drawn over.
  assert.ok(!hybridOrder.includes("water"), "a fill layer leaked into the hybrid");
  assert.ok(!hybridOrder.includes("background"), "the style background hid the imagery");
  assert.ok(map.rasterSpecs.basemap.tiles[0].includes("s2cloudless"));
  assert.ok(map.getLayer("overlay-national-line"), "overlays were lost across the style swap");

  console.log("maplibre-3d runtime checks passed");
})().catch(err => { console.error(err.stack || err.message); process.exit(1); });
