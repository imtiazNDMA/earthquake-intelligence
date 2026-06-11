const map = L.map("map").setView([30.4, 69.3], 5); // Primary Focus Country: Pakistan

// --- Basemaps (all free + keyless; tile servers reachable without a token) ---
const OSM_ATTR = "© OpenStreetMap contributors";
const CARTO_ATTR = OSM_ATTR + " © CARTO";
const ESRI_ATTR = "Tiles © Esri";
const BASEMAPS = {
  "OpenStreetMap": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: OSM_ATTR, maxZoom: 19,
  }),
  "Humanitarian (HOT)": L.tileLayer("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
    attribution: OSM_ATTR + " © Humanitarian OpenStreetMap Team", maxZoom: 19,
  }),
  "Topographic": L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    attribution: OSM_ATTR + " © OpenTopoMap (CC-BY-SA)", maxZoom: 17,
  }),
  "Light (Positron)": L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: CARTO_ATTR, subdomains: "abcd", maxZoom: 20,
  }),
  "Dark (Dark Matter)": L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: CARTO_ATTR, subdomains: "abcd", maxZoom: 20,
  }),
  "Satellite (Esri)": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: ESRI_ATTR + ", Maxar, Earthstar Geographics", maxZoom: 19,
  }),
};
BASEMAPS["OpenStreetMap"].addTo(map); // default basemap

// --- Vector-tile reference overlays (protomaps-leaflet over pmtiles) ---
// `dataLayer` MUST equal the tippecanoe -l layer id used in scripts/build_tiles.py.
const Line = (color, width) => new protomapsL.LineSymbolizer({ color, width });
// Admin outlines: a PolygonSymbolizer fills + strokes its rings under a single
// canvas globalAlpha = `opacity`. The fill is fully transparent so only the
// stroke shows; `opacity` MUST stay > 0 or the stroke is drawn invisibly too.
const Outline = (color, width) =>
  new protomapsL.PolygonSymbolizer({ fill: "rgba(0,0,0,0)", opacity: 1, stroke: color, width });

function overlay(id, symbolizer) {
  return protomapsL.leafletLayer({
    url: `/tiles/${id}.pmtiles`,
    paintRules: [{ dataLayer: id, symbolizer }],
    backgroundColor: "rgba(0,0,0,0)",
  });
}

const OVERLAYS = {
  National: overlay("national", Outline("#444", 1.5)),
  Provinces: overlay("provinces", Outline("#666", 1.0)),
  Districts: overlay("districts", Outline("#999", 0.6)),
  Tehsils: overlay("tehsils", Outline("#bbb", 0.4)),
  Faults: overlay("faults", Line("#d00000", 1.2)),
  "Plate boundaries": overlay("plate_boundaries", Line("#ff8800", 1.6)),
  Plates: overlay("plates",
    new protomapsL.PolygonSymbolizer({ fill: "#ffcc66", opacity: 0.12 })),
};

// Default-on overlays (others toggle via the control to avoid clutter).
OVERLAYS.National.addTo(map);
OVERLAYS.Provinces.addTo(map);
// Move the zoom control clear of the left-edge sidebar shell.
map.zoomControl.setPosition("topright");

// --- Map config panel: overlay checklist + basemap radios ---
// Hosts the controls that used to be the floating Leaflet layer control.
// `BASEMAPS` / `OVERLAYS` are defined above and unchanged.
const BASEMAP_NAMES = Object.keys(BASEMAPS);
let currentBasemap = "OpenStreetMap";
function setBasemap(name) {
  if (name === currentBasemap) return;
  map.removeLayer(BASEMAPS[currentBasemap]);
  BASEMAPS[name].addTo(map);
  currentBasemap = name;
}

const OVERLAY_COLORS = {
  National: "#444", Provinces: "#666", Districts: "#999", Tehsils: "#bbb",
  Faults: "#d00000", "Plate boundaries": "#ff8800", Plates: "#ffcc66",
};
const OVERLAY_DEFAULT_ON = new Set(["National", "Provinces"]); // mirrors addTo() above

function buildConfigPanel() {
  const ovEl = document.getElementById("overlay-list");
  Object.keys(OVERLAYS).forEach((name) => {
    const row = document.createElement("label");
    row.className = "cfg-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = OVERLAY_DEFAULT_ON.has(name);
    cb.addEventListener("change", () => {
      if (cb.checked) OVERLAYS[name].addTo(map);
      else map.removeLayer(OVERLAYS[name]);
    });
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = OVERLAY_COLORS[name];
    const txt = document.createElement("span");
    txt.textContent = name;
    row.append(cb, sw, txt);
    ovEl.appendChild(row);
  });

  const bmEl = document.getElementById("basemap-list");
  BASEMAP_NAMES.forEach((name) => {
    const row = document.createElement("label");
    row.className = "cfg-row";
    const rb = document.createElement("input");
    rb.type = "radio";
    rb.name = "basemap";
    rb.checked = (name === currentBasemap);
    rb.addEventListener("change", () => { if (rb.checked) setBasemap(name); });
    const txt = document.createElement("span");
    txt.textContent = name;
    row.append(rb, txt);
    bmEl.appendChild(row);
  });
}
buildConfigPanel();

// MMI legend (colors mirror _MMI_COLORS in src/eqmon/contours.py).
const MMI_PALETTE = [
  [2, "#bfccff"], [3, "#a0e6ff"], [4, "#80ffff"], [5, "#7aff93"],
  [6, "#ffff00"], [7, "#ffc800"], [8, "#ff9100"], [9, "#ff0000"], [10, "#c80000"],
];
const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  div.style.cssText = "background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,.3)";
  div.innerHTML = "<strong>MMI</strong><br>" +
    MMI_PALETTE.map(([m, c]) => `<i style="background:${c}"></i>${m}`).join("<br>");
  return div;
};
legend.addTo(map);

let intensityLayer = null;
let epicenterMarker = null;
const statusEl = document.getElementById("status");

function style(feature) {
  return { color: feature.properties.color, weight: 1,
           fillColor: feature.properties.color, fillOpacity: 0.45 };
}

async function calculate() {
  const payload = {
    magnitude: parseFloat(document.getElementById("magnitude").value),
    depth_km:  parseFloat(document.getElementById("depth_km").value),
    lat:       parseFloat(document.getElementById("lat").value),
    lon:       parseFloat(document.getElementById("lon").value),
  };
  statusEl.textContent = "Calculating…";
  try {
    const resp = await fetch("/intensity", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json();
      statusEl.textContent = "Error: " + JSON.stringify(err.detail ?? err);
      return;
    }
    const fc = await resp.json();
    if (intensityLayer) map.removeLayer(intensityLayer);
    intensityLayer = L.geoJSON(fc, {
      style,
      onEachFeature: (f, l) =>
        l.bindPopup(`MMI ${f.properties.mmi_lower}–${f.properties.mmi_upper}`),
    }).addTo(map);

    if (epicenterMarker) map.removeLayer(epicenterMarker);
    epicenterMarker = L.circleMarker([payload.lat, payload.lon], {
      radius: 6, color: "#000", fillColor: "#fff", fillOpacity: 1,
    }).addTo(map).bindPopup("Epicenter");

    statusEl.textContent = `${fc.features.length} intensity bands`;
    if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  } catch (e) {
    statusEl.textContent = "Request failed: " + e.message;
  }
}

document.getElementById("calc").addEventListener("click", calculate);

// --- Event catalog (Plan B) ---
const eventsEl = document.getElementById("events");
const impactEl = document.getElementById("impact");

async function refreshEvents() {
  const resp = await fetch("/events?limit=20");
  if (!resp.ok) return;
  const events = await resp.json();
  eventsEl.innerHTML = "<strong>Catalog</strong>" + events.map(e =>
    `<div class="evt" data-id="${e.id}" style="cursor:pointer;padding:3px 0;border-bottom:1px solid #eee">
       M${e.magnitude.toFixed(1)} · ${e.source} · ${new Date(e.occurred_at).toLocaleString()}
     </div>`).join("");
  document.querySelectorAll(".evt").forEach(el =>
    el.addEventListener("click", () => showImpact(el.dataset.id)));
}

async function showImpact(id) {
  impactEl.textContent = "Computing impact…";
  const resp = await fetch(`/events/${id}/impact`, { method: "POST" });
  if (!resp.ok) { impactEl.textContent = "Impact failed"; return; }
  const data = await resp.json();
  if (intensityLayer) map.removeLayer(intensityLayer);
  intensityLayer = L.geoJSON(data.bands, { style }).addTo(map);
  if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  impactEl._rollups = data.rollups;
  renderRollup(data.rollups, "district");
}

// Render one admin level's rollup as a table with a level switcher.
function renderRollup(rollups, level) {
  const top = (rollups[level] || []).filter(d => d.mmi_max > 0).slice(0, 12);
  const opts = ["province", "district", "tehsil"]
    .map(l => `<option value="${l}"${l === level ? " selected" : ""}>${l}</option>`).join("");
  impactEl.innerHTML =
    `<strong>Impact</strong> by <select id="rollup-level">${opts}</select>` +
    "<table style='width:100%'><tr><th align=left>Name</th><th>Max</th><th>Repr</th></tr>" +
    top.map(d => `<tr><td>${escapeHtml(d.name ?? "?")}</td>` +
                 `<td align=center>${d.mmi_max}</td>` +
                 `<td align=center>${d.mmi_repr}</td></tr>`).join("") +
    "</table>";
  document.getElementById("rollup-level").addEventListener("change", (e) =>
    renderRollup(impactEl._rollups, e.target.value));
}

// Minimal HTML escaper for server-supplied names rendered via innerHTML.
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.getElementById("ingest").addEventListener("click", async () => {
  statusEl.textContent = "Pulling USGS feed…";
  try {
    const r = await fetch("/events/ingest", { method: "POST" });
    const res = await r.json();
    statusEl.textContent = `Ingest: ${res.inserted} new of ${res.fetched}`;
  } catch (e) {
    statusEl.textContent = "Ingest failed: " + e.message;
  }
  refreshEvents();
});

refreshEvents();

// --- Sidebar rail: section switching + collapse ---
const SECTIONS = { event: "sec-event", catalog: "sec-catalog", config: "sec-config" };
let activeSection = "event";
let sidebarCollapsed = false;

function setCollapsed(value) {
  sidebarCollapsed = value;
  document.getElementById("sidebar").classList.toggle("collapsed", value);
  document.getElementById("rail-collapse").textContent = value ? "›" : "‹";
}

function showSection(key) {
  // Clicking the already-active icon toggles the panel closed.
  if (key === activeSection && !sidebarCollapsed) { setCollapsed(true); return; }
  activeSection = key;
  setCollapsed(false);
  for (const [k, id] of Object.entries(SECTIONS)) {
    document.getElementById(id).style.display = (k === key) ? "block" : "none";
  }
  document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
    b.classList.toggle("active", b.dataset.section === key));
}

document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
  b.addEventListener("click", () => showSection(b.dataset.section)));
document.getElementById("rail-collapse")
  .addEventListener("click", () => setCollapsed(!sidebarCollapsed));

showSection("event"); // default panel on load
