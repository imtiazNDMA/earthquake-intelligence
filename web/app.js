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

async function refreshEvents(append = false) {
  const search = document.getElementById("filter-search").value.trim();
  const minmag = document.getElementById("filter-minmag").value;
  const maxmag = document.getElementById("filter-maxmag").value;
  const source = document.getElementById("filter-source").value;
  const sort = document.getElementById("filter-sort").value;
  let url = "/events?limit=20";
  if (search) url += "&search=" + encodeURIComponent(search);
  if (minmag) url += "&min_magnitude=" + encodeURIComponent(minmag);
  if (maxmag) url += "&max_magnitude=" + encodeURIComponent(maxmag);
  if (source) url += "&source=" + encodeURIComponent(source);
  if (sort) url += "&orderby=" + encodeURIComponent(sort);
  if (append) url += "&offset=" + eventsEl._offset;
  const resp = await fetch(url);
  if (!resp.ok) return;
  const data = await resp.json();
  let events = data.events || data;
  const total = data.total;
  if (append) {
    events = (eventsEl._allEvents || []).concat(events);
  }
  eventsEl._allEvents = events;
  eventsEl._offset = events.length;
  eventsEl._total = total;
  eventsEl._filter = `?limit=20${search ? "&search=" + encodeURIComponent(search) : ""}${minmag ? "&min_magnitude=" + encodeURIComponent(minmag) : ""}${maxmag ? "&max_magnitude=" + encodeURIComponent(maxmag) : ""}${source ? "&source=" + encodeURIComponent(source) : ""}${sort ? "&orderby=" + encodeURIComponent(sort) : ""}`;
  renderEventList(events, total);
}

function renderEventList(events, total) {
  eventsEl.innerHTML = `<strong>Catalog</strong> <span style="color:#999;font-weight:400;font-size:11px">${total != null ? "(" + events.length + " of " + total + ")" : ""}</span>` + (
    events.length === 0 ? '<div style="color:#999;padding:8px 0;font-size:12px">No events yet — pull the USGS feed or calculate intensity</div>'
    : events.map(ev => {
    const alertClass = ev.alert ? `evt-alert ${ev.alert}` : "";
    const alertText = ev.alert ? ev.alert.toUpperCase() : "";
    return `<div class="evt" data-id="${ev.id}">
      <button class="evt-del" data-del-id="${ev.id}" title="Delete event">✕</button>
      <div class="evt-head">
        <span class="evt-mag">M${ev.magnitude.toFixed(1)}${ev.mag_type ? ` <span class="evt-magtype">${escapeHtml(ev.mag_type)}</span>` : ""}</span>
        ${ev.alert ? `<span class="${alertClass}">${alertText}</span>` : ""}
        ${ev.tsunami ? `<span class="evt-tsunami" title="Tsunami warning">🌊</span>` : ""}
        ${ev.sig ? `<span class="evt-sig">${ev.sig}</span>` : ""}
      </div>
      ${ev.place ? `<div class="evt-place">${escapeHtml(ev.place)}</div>` : ""}
      <div class="evt-meta">${ev.source} · ${new Date(ev.occurred_at).toLocaleString()}</div>
    </div>`;
  }).join("") + (total != null && events.length < total
    ? `<button id="load-more" style="width:100%;padding:4px;margin-top:6px;cursor:pointer;font-size:11px;background:transparent;color:#0366d6;border:1px solid #c0d8f0;border-radius:4px">Load ${Math.min(20, total - events.length)} more…</button>`
    : ""));
  document.querySelectorAll(".evt").forEach(el =>
    el.addEventListener("click", (e) => {
      if (e.target.closest(".evt-del")) return;  // ignore delete button clicks
      showImpact(el.dataset.id);
    }));
  document.querySelectorAll(".evt-del").forEach(btn =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDelete(parseInt(btn.dataset.delId));
    }));
  const loadMore = document.getElementById("load-more");
  if (loadMore) loadMore.addEventListener("click", () => refreshEvents(true));
}

// --- Confirmation dialog for delete ---
const confirmOverlay = document.getElementById("confirm-overlay");
const confirmMsg = document.getElementById("confirm-msg");
const confirmOk = document.getElementById("confirm-ok");
let _pendingDeleteId = null;

function confirmDelete(eventId) {
  _pendingDeleteId = eventId;
  confirmMsg.textContent = "Delete this event and all its data?";
  confirmOverlay.classList.add("open");
}

confirmOk.addEventListener("click", async () => {
  if (_pendingDeleteId === null) return;
  const id = _pendingDeleteId;
  _pendingDeleteId = null;
  confirmOverlay.classList.remove("open");
  try {
    const r = await fetch(`/events/${id}`, { method: "DELETE" });
    if (r.ok) {
      document.getElementById("detail").innerHTML = "";
      impactEl.innerHTML = "";
      refreshEvents();
    }
  } catch (e) {
    // ignore
  }
});

document.getElementById("confirm-cancel").addEventListener("click", () => {
  _pendingDeleteId = null;
  confirmOverlay.classList.remove("open");
});

confirmOverlay.addEventListener("click", (e) => {
  if (e.target === confirmOverlay) {
    _pendingDeleteId = null;
    confirmOverlay.classList.remove("open");
  }
});

async function showImpact(id) {
  const detailEl = document.getElementById("detail");
  impactEl.textContent = "Computing impact…";
  detailEl.innerHTML = "";
  // Fetch event detail + impact in parallel
  const [evtResp, impactResp] = await Promise.all([
    fetch(`/events/${id}`),
    fetch(`/events/${id}/impact`, { method: "POST" }),
  ]);
  if (!impactResp.ok) { impactEl.textContent = "Impact failed"; return; }
  const evt = evtResp.ok ? await evtResp.json() : null;
  const data = await impactResp.json();
  // Render intensity bands on map
  if (intensityLayer) map.removeLayer(intensityLayer);
  intensityLayer = L.geoJSON(data.bands, { style }).addTo(map);
  if (epicenterMarker) map.removeLayer(epicenterMarker);
  epicenterMarker = L.circleMarker([evt.lat, evt.lon], {
    radius: 6, color: "#000", fillColor: "#fff", fillOpacity: 1,
  }).addTo(map).bindPopup(`Epicenter — M${evt.magnitude.toFixed(1)}`);
  if (intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
  // Render USGS detail card
  renderDetail(evt);
  // Render impact table
  impactEl._rollups = data.rollups;
  renderRollup(data.rollups, "district");
}

function renderDetail(evt) {
  const el = document.getElementById("detail");
  el.innerHTML = "";
  if (!evt) return;
  const detail = evt.usgs_detail;
  const props = detail?.properties;
  if (!evt.source_event_id) {
    // Manual event — show edit + delete buttons
    el.innerHTML = `<div class="evt-detail">
      <div class="detail-info">Manual event — no USGS data.</div>
      <button class="btn-edit" data-edit-id="${evt.id}">✏️ Edit</button>
      <button class="btn-del-detail" data-del-id="${evt.id}">✕ Delete event</button>
    </div>`;
    el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
    el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
    return;
  }
  if (!props) {
    // Have source_event_id but no cached detail
    el.innerHTML = `<div class="evt-detail">
      <div class="detail-info">No USGS detail cached.</div>
      <button class="btn-refresh" style="margin-bottom:4px">🔄 Refresh from USGS</button>
      <button class="btn-edit" data-edit-id="${evt.id}">✏️ Edit</button>
      <button class="btn-del-detail" data-del-id="${evt.id}">✕ Delete event</button>
    </div>`;
    el.querySelector(".btn-refresh").addEventListener("click", () => refreshFromUsgs(evt.id));
    el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
    el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
    return;
  }
    return;
  }
  const prods = props.products || {};
  const badges = [];
  if (prods.shakemap?.length) badges.push("🏛 ShakeMap");
  if (prods["moment-tensor"]?.length) badges.push("🌀 Moment Tensor");
  if (prods.dyfi?.length) badges.push("📊 DYFI");
  if (prods["focal-mechanism"]?.length) badges.push("⚙ Focal Mechanism");
  const alertBadge = props.alert
    ? `<span class="evt-alert ${props.alert}">${props.alert.toUpperCase()}</span>` : "";
  el.innerHTML = `<div class="evt-detail">
    <div class="detail-head">
      <span class="detail-title">USGS Detail</span>
      ${alertBadge}
      ${props.tsunami ? '<span class="evt-tsunami" title="Tsunami warning">🌊</span>' : ""}
    </div>
    <div class="detail-info">
      ${props.place ? `<div>📍 ${escapeHtml(props.place)}</div>` : ""}
      <div>M${props.mag} ${props.magType || ""} · depth ${props.depth} km</div>
      <div>${props.felt ? `👤 ${props.felt} felt · ` : ""}${props.sig ? `⚡ sig ${props.sig}` : ""}</div>
      ${badges.length ? `<div class="detail-prods">${badges.join(" · ")}</div>` : ""}
      ${props.url ? `<a href="${escapeHtml(props.url)}" target="_blank" class="detail-link">View on USGS ↗</a>` : ""}
    </div>
    <button class="btn-refresh" style="margin-bottom:4px">🔄 Refresh from USGS</button>
    <button class="btn-edit" data-edit-id="${evt.id}">✏️ Edit</button>
    <button class="btn-del-detail" data-del-id="${evt.id}">✕ Delete event</button>
  </div>`;
  el.querySelector(".btn-refresh").addEventListener("click", () => refreshFromUsgs(evt.id));
  el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
  el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
}

async function refreshFromUsgs(eventId) {
  const btn = document.querySelector(".btn-refresh");
  if (btn) { btn.disabled = true; btn.textContent = "Refreshing…"; }
  try {
    const r = await fetch(`/events/${eventId}/refresh-from-usgs`, { method: "POST" });
    if (r.ok) {
      const evt = await r.json();
      renderDetail(evt);
    } else {
      document.getElementById("detail").innerHTML = `<div class="evt-detail">USGS refresh failed.</div>`;
    }
  } catch (e) {
    document.getElementById("detail").innerHTML = `<div class="evt-detail">USGS refresh failed: ${e.message}</div>`;
  }
}

function showEditForm(evt) {
  const el = document.getElementById("detail");
  el.innerHTML = `<div class="evt-detail">
    <div class="detail-info">
      <div class="edit-row"><label>Mag</label><input id="edit-mag" type="number" step="0.1" value="${evt.magnitude}"></div>
      <div class="edit-row"><label>Depth</label><input id="edit-depth" type="number" step="0.1" value="${evt.depth_km}"></div>
      <div class="edit-row"><label>Lat</label><input id="edit-lat" type="number" step="0.01" value="${evt.lat}"></div>
      <div class="edit-row"><label>Lon</label><input id="edit-lon" type="number" step="0.01" value="${evt.lon}"></div>
      <div class="edit-row"><label>Place</label><input id="edit-place" type="text" value="${escapeHtml(evt.place || "")}"></div>
    </div>
    <div class="btn-group">
      <button id="edit-save" class="btn-refresh" style="margin:0">💾 Save</button>
      <button id="edit-cancel" class="btn-edit" style="margin:0">Cancel</button>
    </div>
    <button class="btn-del-detail" data-del-id="${evt.id}">✕ Delete event</button>
  </div>`;
  document.getElementById("edit-cancel").addEventListener("click", () => renderDetail(evt));
  document.getElementById("edit-save").addEventListener("click", async () => {
    const body = {
      magnitude: parseFloat(document.getElementById("edit-mag").value),
      depth_km: parseFloat(document.getElementById("edit-depth").value),
      lat: parseFloat(document.getElementById("edit-lat").value),
      lon: parseFloat(document.getElementById("edit-lon").value),
      place: document.getElementById("edit-place").value || null,
    };
    try {
      const r = await fetch(`/events/${evt.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        const updated = await r.json();
        renderDetail(updated);
        refreshEvents();
      }
    } catch (e) { /* ignore */ }
  });
  el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
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
  const minmag = document.getElementById("ingest-minmag").value;
  let url = "/events/ingest";
  if (minmag) url += "?min_magnitude=" + encodeURIComponent(minmag);
  try {
    const r = await fetch(url, { method: "POST" });
    const res = await r.json();
    statusEl.textContent = `Ingest: ${res.inserted} new of ${res.fetched}`;
  } catch (e) {
    statusEl.textContent = "Ingest failed: " + e.message;
  }
  refreshEvents();
});

// Ingest status indicator
function updateIngestStatus() {
  fetch("/events/ingest/status").then(r => r.json()).then(s => {
    const el = document.getElementById("ingest-status");
    if (s.last_sync) el.textContent = "Last sync: " + new Date(s.last_sync).toLocaleString();
    else el.textContent = "";
  });
}
updateIngestStatus();
setInterval(updateIngestStatus, 30000);

refreshEvents();

// Catalog filter auto-refresh on change
["filter-search", "filter-minmag", "filter-maxmag", "filter-source", "filter-sort"].forEach(id => {
  const el = document.getElementById(id);
  const ev = el.tagName === "SELECT" ? "change" : "input";
  el.addEventListener(ev, refreshEvents);
});

// --- Sidebar rail: section switching + collapse ---
const SECTIONS = { event: "sec-event", catalog: "sec-catalog", config: "sec-config" };
// Start as null (not "event") so the initial showSection("event") renders the
// section instead of matching the active-icon-toggle guard and collapsing.
let activeSection = null;
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
