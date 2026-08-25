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
  location: { href: "http://localhost:8000/" },
  URL,
  Date,
  Set,
};
sandbox.window = sandbox;

// --- stub DOM -------------------------------------------------------------
function stubElement(tag) {
  return {
    tag, dataset: {}, style: {}, className: "", innerHTML: "",
    setAttribute() {}, appendChild() {}, remove() {},
    addEventListener() {}, querySelectorAll: () => [],
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
    sky: options.style.sky,
    markers: [],
    handlers: {},
    once(event, fn) { if (event === "load" || event === "idle") fn(); },
    on(event, second, third) {
      const key = third ? `${event}:${second}` : event;
      (this.handlers[key] ||= []).push(third || second);
    },
    off() {},
    getCanvas: () => ({ style: {} }),
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
    jumpTo() {},
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
sandbox.window.eqmonMapModes = { emit: (name, payload) => intents.push([name, payload]) };

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("web/map-style-config.js", "utf8"), sandbox, { filename: "map-style-config.js" });
vm.runInContext(fs.readFileSync("web/overlay-format.js", "utf8"), sandbox, { filename: "overlay-format.js" });
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

  console.log("maplibre-3d runtime checks passed");
})().catch(err => { console.error(err.stack || err.message); process.exit(1); });
