/* Exercises web/map-modes.js against stub renderers: camera round-trip drift,
   state isolation, and the no-refetch invariant. */
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const sameCenter = (a, b) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), `center ${JSON.stringify(a)} != ${JSON.stringify(b)}`);

function el(extra = {}) {
  return Object.assign({
    style: {}, dataset: {}, hidden: false, classList: { add() {}, remove() {}, toggle() {} },
    setAttribute() {}, removeAttribute() {}, addEventListener() {}, querySelectorAll: () => [],
  }, extra);
}

const buttons = {
  "2d": el({ dataset: { mapMode: "2d" }, addEventListener(_, fn) { this.click = fn; } }),
  "3d": el({ dataset: { mapMode: "3d" }, addEventListener(_, fn) { this.click = fn; } }),
};
const control = el({ querySelectorAll: () => [buttons["2d"], buttons["3d"]] });
const nodes = { map: el(), "map-3d": el(), "map-mode-control": control, "map-mode-loading": el() };

// --- stub 2D renderer: 256px-tile zoom, [lat, lon] order -------------------
const leaflet = {
  center: { lat: 30.4, lng: 69.3 }, zoom: 5, handlers: {},
  getCenter() { return this.center; },
  getZoom() { return this.zoom; },
  setView([lat, lon], zoom) {
    this.center = { lat, lng: lon };
    this.zoom = zoom;
    (this.handlers.moveend || []).forEach(fn => fn());   // synchronous, like a non-animated move
  },
  on(event, fn) { (this.handlers[event] ||= []).push(fn); },
  invalidateSize() {},
};

// --- stub 3D renderer: 512px-tile zoom ------------------------------------
let listener = null;
const maplibre = {
  camera: null, created: 0,
  // Mirrors the real adapter: builds at most one map and reuses it afterwards.
  ensureMapLibre3d(camera) {
    if (!maplibre.camera) { maplibre.created += 1; maplibre.camera = { ...camera }; }
    return Promise.resolve({});
  },
  hasInstance: () => maplibre.camera !== null,
  resize() {},
  setCamera(camera) { maplibre.camera = { ...camera }; if (listener) listener({ ...camera }); },
  getCamera: () => maplibre.camera,
  onCameraChange(fn) { listener = fn; },
  applied: [],
  applyState(state) { maplibre.applied.push(state); },
};

const store = {};
const sandbox = {
  console,
  setTimeout, clearTimeout,
  document: { getElementById: id => nodes[id] || null, body: { classList: { add() {}, remove() {} } } },
  localStorage: {
    getItem: k => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = v; },
    removeItem: k => { delete store[k]; },
  },
  MutationObserver: class { observe() {} },
  CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
  map: leaflet,
  fetch: () => { throw new Error("mode switching must not fetch"); },
};
sandbox.window = sandbox;
sandbox.window.dispatchEvent = () => {};
sandbox.window.setTimeout = setTimeout;
sandbox.window.clearTimeout = clearTimeout;
sandbox.window.eqmonMapLibre3d = maplibre;
sandbox.window.eqmonMapState = { queue: [{ basemap: "OpenStreetMap" }], publish(p) { this.queue.push(p); } };
// A WebGL2 context is reported as available.
sandbox.document.createElement = () => ({ getContext: () => ({ getExtension: () => ({ loseContext() {} }) }) });
sandbox.document.documentElement = { dataset: { theme: "dark" } };
sandbox.devicePixelRatio = 1;

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("web/map-style-config.js", "utf8"), sandbox, { filename: "map-style-config.js" });
vm.runInContext(fs.readFileSync("web/map-modes.js", "utf8"), sandbox, { filename: "map-modes.js" });
const modes = sandbox.window.eqmonMapModes;
const styles = sandbox.window.eqmonMapStyleConfig;

(async () => {
  // Buffered publications survive the coordinator loading last.
  assert.strictEqual(modes.getState().basemap, "OpenStreetMap");

  // Operator moves the 2D map, then switches.
  leaflet.setView([34.37, 73.47], 11);
  const start = modes.getCamera();
  sameCenter(start.center, [73.47, 34.37]);
  assert.strictEqual(start.zoom, 11);

  await modes.setMode("3d");
  assert.strictEqual(modes.getMode(), "3d");
  // Same ground scale, one zoom level apart, and DG-3 pitch applied.
  assert.strictEqual(maplibre.camera.zoom, 10);
  sameCenter(maplibre.camera.center, [73.47, 34.37]);
  assert.strictEqual(maplibre.camera.pitch, 55);

  for (let i = 0; i < 20; i++) {
    modes.setMode("2d");
    await modes.setMode("3d");
  }
  const after = modes.getCamera();
  sameCenter(after.center, start.center);
  assert.strictEqual(after.zoom, start.zoom, `zoom drifted to ${after.zoom}`);
  assert.strictEqual(after.pitch, 55);
  assert.strictEqual(maplibre.created, 1, `built ${maplibre.created} 3D instances`);

  // A 3D move is reflected on return to 2D.
  maplibre.setCamera({ center: [67.0, 24.86], zoom: 9, bearing: 40, pitch: 60 });
  modes.setMode("2d");
  assert.strictEqual(leaflet.zoom, 10);
  assert.strictEqual(leaflet.center.lat, 24.86);
  assert.strictEqual(modes.getCamera().bearing, 40, "2D must not reset bearing");
  assert.strictEqual(modes.getCamera().pitch, 60, "2D must not reset pitch");

  // Shared state is a JSON snapshot, not a live handle.
  modes.publish({ currentMmi: { featureCollection: { type: "FeatureCollection", features: [] }, visible: true } });
  const snapshot = modes.getState();
  snapshot.currentMmi.visible = false;
  assert.strictEqual(modes.getState().currentMmi.visible, true, "getState leaked a reference");
  modes.publish({ intensityLayer: "leaflet layer" });
  assert.ok(!("intensityLayer" in modes.getState()), "unknown keys must be rejected");
  JSON.stringify(modes.getState());

  // --- shared basemap catalogue (Phase 3) ---------------------------------
  // Every row must describe both renderers from one definition.
  for (const def of styles.BASEMAP_DEFS) {
    const source = styles.maplibreSource(def.name);
    assert.strictEqual(source.maxzoom, def.maxZoom, `${def.name} zoom ceiling diverged`);
    assert.strictEqual(source.attribution, styles.leafletOptions(def).attribution,
      `${def.name} credit diverged`);
    assert.ok(source.tiles.length >= 1, `${def.name} has no tile URL`);
    for (const url of source.tiles) {
      // MapLibre understands neither placeholder.
      assert.ok(!url.includes("{s}"), `${def.name} left a host placeholder: ${url}`);
      assert.ok(!url.includes("{r}"), `${def.name} left a retina placeholder: ${url}`);
    }
  }
  // Host rotation becomes one URL per subdomain.
  assert.strictEqual(styles.maplibreSource("OpenStreetMap").tiles.length, 3);
  assert.strictEqual(styles.maplibreSource("Light (Positron)").tiles.length, 4);
  assert.strictEqual(styles.maplibreSource("Satellite (Esri)").tiles.length, 1);
  assert.strictEqual(styles.themeBasemap("dark"), "Dark (Dark Matter)");
  assert.strictEqual(styles.themeBasemap("light"), "OpenStreetMap");
  // An unknown name must still yield a usable basemap rather than throwing.
  assert.ok(styles.maplibreSource("no such basemap").tiles.length >= 1);
  // Terrain is described at true scale with a bounded wait.
  assert.strictEqual(styles.TERRAIN.exaggeration, 1.0);
  assert.strictEqual(styles.TERRAIN.encoding, "terrarium");
  assert.ok(styles.TERRAIN.timeoutMs > 0);

  // Basemap and theme reach the 3D renderer as state, not as a direct call.
  maplibre.applied.length = 0;
  modes.publish({ basemap: "Voyager", theme: "dark" });
  const last = maplibre.applied.at(-1);
  assert.strictEqual(last.basemap, "Voyager");
  assert.strictEqual(last.theme, "dark");

  console.log("map-modes runtime checks passed");
})().catch(err => { console.error(err.message); process.exit(1); });
