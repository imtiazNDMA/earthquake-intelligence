const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

const nodes = {
  "filter-minmag": { value: "4" },
  "filter-maxmag": { value: "" },
  "filter-after": { value: "2026-08-01T00:00:00Z" },
  "filter-before": { value: "" },
  "filter-search": { value: "Quetta" },
};
const state = {
  activeEvent: { id: "evt-123", place: "untrusted label" },
  currentMmi: { visible: true, opacity: 0.45, selectedLevel: 7,
                featureCollection: { type: "FeatureCollection", features: [{ huge: true }] } },
  mapEvents: { startIndex: 0, endIndex: 24, events: [{ private: "not projected" }] },
  basemap: "OpenStreetMap",
  overlays: { National: { id: "national", visible: true, opacity: 1, color: "red" } },
  landslides: { opacity: 0.62, regions: [{ key: "GB", enabled: true, url: "secret" }] },
  pga: { enabled: false, returnPeriod: 475, opacity: 0.55, image: "large.png" },
  buildings: { enabled: true, selected: null, opacity: 0.68, catalog: [{ large: true }] },
  theme: "dark",
};
const sandbox = {
  console,
  Date,
  document: {
    getElementById: id => nodes[id] || null,
    querySelector(selector) {
      if (selector === ".cat-tab.active") return { dataset: { src: "USGS" } };
      if (selector === ".rail-ic.active[data-section]") return { dataset: { section: "event" } };
      return null;
    },
  },
  matchMedia: () => ({ matches: false }),
  eqmonMapModes: {
    getMode: () => "2d",
    getCamera: () => ({ center: [73.47, 34.37], zoom: 11, bearing: 0, pitch: 0 }),
    getState: () => JSON.parse(JSON.stringify(state)),
  },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync("web/ai-context.js", "utf8"), sandbox,
                { filename: "ai-context.js" });

const context = sandbox.eqmonAiContext.collect();
assert.strictEqual(context.schema_version, "1.0");
assert.deepStrictEqual([...context.map.center], [73.47, 34.37]);
assert.strictEqual(context.selection.event_id, "evt-123");
assert.strictEqual(context.selection.sidebar_section, "event");
assert.deepStrictEqual([...context.event_filters.sources], ["USGS"]);
assert.strictEqual(context.event_filters.date_from, "2026-08-01T00:00:00Z");
assert.deepStrictEqual([...context.event_filters.time_window_indices], [0, 24]);
assert.strictEqual(context.layers.reference[0].id, "national");
assert.strictEqual(context.layers.landslides[0].id, "GB");
const serialized = JSON.stringify(context);
for (const forbidden of ["FeatureCollection", "private", "large.png", "secret", "untrusted label", "color"]) {
  assert.ok(!serialized.includes(forbidden), `context leaked ${forbidden}`);
}
console.log("ai-context runtime checks passed");
