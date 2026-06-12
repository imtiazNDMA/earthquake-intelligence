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

const OVERLAY_CONFIG = {
  National:        { id: "national",         color: "#444",   width: 1.5, defaultOn: true },
  Provinces:       { id: "provinces",        color: "#666",   width: 1.0, defaultOn: true },
  Districts:       { id: "districts",        color: "#999",   width: 0.6, defaultOn: false },
  Tehsils:         { id: "tehsils",          color: "#bbb",   width: 0.4, defaultOn: false },
  "Global Faults": { id: "faults",          color: "#111", width: 0.8, defaultOn: false, lineOnly: true, faultStyle: true },
  "Plate boundaries": { id: "plate_boundaries", color: "#ff8800", width: 1.6, defaultOn: false, lineOnly: true },
  "Pakistan Major": { id: "pak_faults_major", color: "#111", width: 0.9, defaultOn: false, lineOnly: true, faultStyle: true },
  "Pakistan Minor": { id: "pak_faults_minor", color: "#111", width: 1.1, defaultOn: true, lineOnly: true, faultStyle: true },
  "Tectonic Zones":{ id: "pak_tectonic_zones", color: "#444", width: 0.5, defaultOn: true,
                     fillColor: "#888", fillOpacity: 0.7 },
};

function _pastelFromName(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
  return `hsl(${((h % 360) + 360) % 360}, 45%, 75%)`;
}

class NamedPolySymbolizer {
  constructor(opts) {
    this.stroke = opts.stroke;
    this.width = opts.width;
    this.alpha = opts.opacity;
    this._prop = opts.prop;
    this._cache = {};
  }
  draw(ctx, geom, z, feature) {
    const name = feature.props[this._prop] || "";
    let fill = this._cache[name];
    if (!fill) { fill = _pastelFromName(name); this._cache[name] = fill; }
    ctx.globalAlpha = this.alpha;
    ctx.fillStyle = fill;
    ctx.strokeStyle = this.stroke;
    ctx.lineWidth = this.width;
    for (const poly of geom) {
      ctx.beginPath();
      for (let p = 0; p < poly.length - 1; p++) {
        const pt = poly[p];
        p === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
  }
}

class FaultLineSymbolizer {
  constructor(opts) {
    this.color = opts.color;
    this.width = opts.width;
    this.spacing = opts.spacing ?? 28;
    this.size = opts.size ?? 5;
  }
  draw(ctx, geom) {
    ctx.save();
    ctx.strokeStyle = this.color;
    ctx.fillStyle = this.color;
    ctx.lineWidth = this.width;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (const line of geom) {
      if (line.length < 2) continue;
      ctx.beginPath();
      line.forEach((pt, i) => i === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y));
      ctx.stroke();
      this._drawTeeth(ctx, line);
    }
    ctx.restore();
  }
  _drawTeeth(ctx, line) {
    let next = this.spacing;
    for (let i = 1; i < line.length; i++) {
      const a = line[i - 1], b = line[i];
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.hypot(dx, dy);
      if (!len) continue;
      const ux = dx / len, uy = dy / len;
      const px = -uy, py = ux;
      while (next <= len) {
        const t = next / len;
        const x = a.x + dx * t, y = a.y + dy * t;
        const backX = x - ux * this.size, backY = y - uy * this.size;
        ctx.beginPath();
        ctx.moveTo(x + ux * this.size * 0.55, y + uy * this.size * 0.55);
        ctx.lineTo(backX + px * this.size * 0.55, backY + py * this.size * 0.55);
        ctx.lineTo(backX - px * this.size * 0.55, backY - py * this.size * 0.55);
        ctx.closePath();
        ctx.fill();
        next += this.spacing;
      }
      next -= len;
    }
  }
}

function buildOverlay(name) {
  const c = OVERLAY_CONFIG[name];

  if (name === "Tectonic Zones") {
    return protomapsL.leafletLayer({
      url: `/tiles/${c.id}.pmtiles`,
      paintRules: [{ dataLayer: c.id, symbolizer: new NamedPolySymbolizer({ prop: "Name", stroke: c.color, width: c.width, opacity: c.fillOpacity ?? 0.7 }) }],
      backgroundColor: "rgba(0,0,0,0)"
    });
  }

  let sym;
  if (c.fillColor) {
    sym = new protomapsL.PolygonSymbolizer({ fill: c.fillColor, opacity: c.fillOpacity, stroke: c.color, width: c.width });
  } else if (c.faultStyle) {
    sym = new FaultLineSymbolizer({ color: c.color, width: c.width });
  } else if (c.lineOnly) {
    sym = new protomapsL.LineSymbolizer({ color: c.color, width: c.width });
  } else {
    sym = new protomapsL.PolygonSymbolizer({ fill: "rgba(0,0,0,0)", opacity: 1, stroke: c.color, width: c.width });
  }
  return protomapsL.leafletLayer({ url: `/tiles/${c.id}.pmtiles`, paintRules: [{ dataLayer: c.id, symbolizer: sym }], backgroundColor: "rgba(0,0,0,0)" });
}

function rebuildOverlay(name) {
  const c = OVERLAY_CONFIG[name];
  const old = OVERLAYS[name];
  const on = old && map.hasLayer(old);
  if (on) map.removeLayer(old);
  OVERLAYS[name] = buildOverlay(name);
  if (on) OVERLAYS[name].addTo(map);
}

const OVERLAYS = {};
Object.keys(OVERLAY_CONFIG).forEach(name => {
  OVERLAYS[name] = buildOverlay(name);
  if (OVERLAY_CONFIG[name].defaultOn) OVERLAYS[name].addTo(map);
});

// Move the zoom control clear of the left-edge sidebar shell.
map.zoomControl.setPosition("topright");

// --- Map config panel: overlay checklist + basemap radios ---
const BASEMAP_NAMES = Object.keys(BASEMAPS);
let currentBasemap = "OpenStreetMap";
function setBasemap(name) {
  if (name === currentBasemap) return;
  map.removeLayer(BASEMAPS[currentBasemap]);
  BASEMAPS[name].addTo(map);
  currentBasemap = name;
}

function buildConfigPanel() {
  const ovEl = document.getElementById("overlay-list");
  Object.keys(OVERLAY_CONFIG).forEach((name) => {
    const c = OVERLAY_CONFIG[name];
    const row = document.createElement("div");
    row.className = "cfg-row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!c.defaultOn;
    cb.addEventListener("change", () => {
      if (cb.checked) OVERLAYS[name].addTo(map);
      else map.removeLayer(OVERLAYS[name]);
      controls.style.display = cb.checked ? "flex" : "none";
    });
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = c.color;
    sw.addEventListener("click", () => colPick.click());
    const txt = document.createElement("span");
    txt.className = "ov-name";
    txt.textContent = name;
    const controls = document.createElement("span");
    controls.className = "ov-controls";
    controls.style.display = cb.checked ? "flex" : "none";
    const w = document.createElement("input");
    w.type = "number";
    w.className = "ov-width";
    w.value = c.width;
    w.step = "0.1"; w.min = "0.1"; w.max = "5";
    w.title = "Line width";
    w.addEventListener("change", () => { c.width = parseFloat(w.value) || c.width; rebuildOverlay(name); });
    controls.appendChild(w);
    const colPick = document.createElement("input");
    colPick.type = "color";
    colPick.className = "ov-color";
    colPick.value = c.color;
    colPick.title = "Line color";
    colPick.addEventListener("input", () => {
      c.color = colPick.value;
      sw.style.background = c.color;
      if (c.fillColor) c.fillColor = colPick.value;
      rebuildOverlay(name);
    });
    controls.appendChild(colPick);
    if (c.fillColor) {
      const o = document.createElement("input");
      o.type = "range";
      o.className = "ov-opacity";
      o.min = "0"; o.max = "1"; o.step = "0.05"; o.value = c.fillOpacity;
      o.title = "Fill opacity";
      o.addEventListener("input", () => { c.fillOpacity = parseFloat(o.value); rebuildOverlay(name); });
      controls.appendChild(o);
    }
    row.append(cb, sw, txt, controls);
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

let _legendItems = {};
let _mmiLayers = {};

function highlightByLevel(level) {
  Object.keys(_legendItems).forEach(k => {
    _legendItems[k].classList.toggle("active", parseInt(k) === level);
  });
  Object.entries(_mmiLayers).forEach(([k, layers]) => {
    const on = parseInt(k) === level;
    layers.forEach(l => l.setStyle({ weight: on ? 2.5 : 1, fillOpacity: on ? 0.7 : 0.45 }));
  });
}

function unhighlightAll() {
  Object.values(_legendItems).forEach(el => el.classList.remove("active"));
  Object.values(_mmiLayers).forEach(group => {
    group.forEach(l => l.setStyle({ weight: 1, fillOpacity: 0.45 }));
  });
}

const legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  const div = L.DomUtil.create("div", "legend");
  div.innerHTML = "<div class='legend-title'>MMI</div>" +
    MMI_PALETTE.map(([m, c]) =>
      `<div class="legend-item" data-level="${m}"><span class="legend-swatch" style="background:${c}"></span><span class="legend-label">${m}</span></div>`
    ).join("");
  div.querySelectorAll(".legend-item").forEach(el => {
    const level = parseInt(el.dataset.level);
    el.addEventListener("mouseenter", () => highlightByLevel(level));
    el.addEventListener("mouseleave", () => unhighlightAll());
    _legendItems[level] = el;
  });
  return div;
};
legend.addTo(map);

function onMmiFeature(f, l) {
  const level = f.properties.mmi_lower;
  if (!_mmiLayers[level]) _mmiLayers[level] = [];
  _mmiLayers[level].push(l);
  l.bindPopup(`MMI ${f.properties.mmi_lower}–${f.properties.mmi_upper}`);
  l.on("mouseover", () => highlightByLevel(level));
  l.on("mouseout", () => unhighlightAll());
}

let intensityLayer = null;
let epicenterMarker = null;
const statusEl = document.getElementById("status");
// --- Comparison mode state ---
let _compareMode = false;
let _compareIds = [];
let _compLayers = [];
let _cmpLegendCtrl = null;
let _timelineExpanded = true;

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
    _mmiLayers = {};
    if (intensityLayer) map.removeLayer(intensityLayer);
    intensityLayer = L.geoJSON(fc, {
      style,
      onEachFeature: onMmiFeature,
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
  const after = document.getElementById("filter-after").value;
  const before = document.getElementById("filter-before").value;
  let url = "/events?limit=20";
  if (search) url += "&search=" + encodeURIComponent(search);
  if (minmag) url += "&min_magnitude=" + encodeURIComponent(minmag);
  if (maxmag) url += "&max_magnitude=" + encodeURIComponent(maxmag);
  if (source) url += "&source=" + encodeURIComponent(source);
  if (sort) url += "&orderby=" + encodeURIComponent(sort);
  if (after) url += "&occurred_after=" + encodeURIComponent(after);
  if (before) url += "&occurred_before=" + encodeURIComponent(before);
  if (append && eventsEl._offset != null) url += "&offset=" + eventsEl._offset;
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
  const f = (id, name) => { const v = document.getElementById(id).value; return v ? `&${name}=` + encodeURIComponent(v) : ""; };
  eventsEl._filter = `?limit=20${f("filter-search","search")}${f("filter-minmag","min_magnitude")}${f("filter-maxmag","max_magnitude")}${f("filter-source","source")}${f("filter-sort","orderby")}${f("filter-after","occurred_after")}${f("filter-before","occurred_before")}`;
  renderEventList(events, total);
}

function renderEventList(events, total) {
  eventsEl.innerHTML = `<div style="display:flex;align-items:center;gap:4px"><strong>Catalog</strong> <span style="color:#999;font-weight:400;font-size:11px">${total != null ? "(" + events.length + " of " + total + ")" : ""}</span><button id="cmp-toggle" class="cmp-toggle${_compareMode ? " active" : ""}">${_compareMode ? "✕" : "Compare"}</button><span class="export-wrap"><button id="export-btn" class="export-btn" title="Download">↓</button><div id="export-menu" class="export-menu"><a class="export-opt" data-format="csv">CSV</a><a class="export-opt" data-format="geojson">GeoJSON</a></div></span></div>` + (
    events.length === 0 ? '<div style="color:#999;padding:8px 0;font-size:12px">No events yet — pull the USGS feed or calculate intensity</div>'
    : events.map(ev => {
    const alertClass = ev.alert ? `evt-alert ${ev.alert}` : "";
    const alertText = ev.alert ? ev.alert.toUpperCase() : "";
    const cmpIdx = _compareIds.indexOf(ev.id);
    const cmpClass = cmpIdx === 0 ? " selected1" : cmpIdx === 1 ? " selected2" : "";
    return `<div class="evt${_compareMode ? " evt-comp" : ""}" data-id="${ev.id}">
      <button class="evt-del" data-del-id="${ev.id}" title="Delete event">✕</button>
      ${_compareMode ? `<div class="cmp-radio${cmpClass}">${cmpIdx >= 0 ? cmpIdx + 1 : ""}</div>` : ""}
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
      if (e.target.closest(".evt-del")) return;
      if (_compareMode) { selectForComparison(el.dataset.id); return; }
      showImpact(el.dataset.id);
    }));
  const cmpToggle = document.getElementById("cmp-toggle");
  if (cmpToggle) cmpToggle.addEventListener("click", (e) => { e.stopPropagation(); toggleCompareMode(); });
  document.querySelectorAll(".evt-del").forEach(btn =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      confirmDelete(parseInt(btn.dataset.delId));
    }));
  const loadMore = document.getElementById("load-more");
  if (loadMore) loadMore.addEventListener("click", () => refreshEvents(true));
  renderTimelineChart(events);
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
  _compLayers.forEach(l => map.removeLayer(l));
  _compLayers = [];
  if (_cmpLegendCtrl) { map.removeControl(_cmpLegendCtrl); _cmpLegendCtrl = null; }
  if (_compareMode) toggleCompareMode();
  const detailEl = document.getElementById("detail");
  impactEl.textContent = "Computing impact…";
  detailEl.innerHTML = "";
  const [evtResp, impactResp] = await Promise.all([
    fetch(`/events/${id}`),
    fetch(`/events/${id}/impact`, { method: "POST" }),
  ]);
  if (!impactResp.ok) { impactEl.textContent = "Impact failed"; return; }
  const evt = evtResp.ok ? await evtResp.json() : null;
  const data = await impactResp.json();
  // Render intensity bands on map
  _mmiLayers = {};
  if (intensityLayer) map.removeLayer(intensityLayer);
  intensityLayer = L.geoJSON(data.bands, { style, onEachFeature: onMmiFeature }).addTo(map);
  if (evt && (evt.lat != null || evt.lon != null)) {
    if (epicenterMarker) map.removeLayer(epicenterMarker);
    epicenterMarker = L.circleMarker([evt.lat, evt.lon], {
      radius: 6, color: "#000", fillColor: "#fff", fillOpacity: 1,
    }).addTo(map).bindPopup(`Epicenter — M${evt.magnitude.toFixed(1)}`);
  }
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
    "<table style='width:100%'><tr><th align=left>Name</th><th>Max MMI</th></tr>" +
    top.map(d => `<tr><td>${escapeHtml(d.name ?? "?")}</td>` +
                 `<td align=center>${d.mmi_max}</td></tr>`).join("") +
    "</table>";
  document.getElementById("rollup-level").addEventListener("change", (e) =>
    renderRollup(impactEl._rollups, e.target.value));
}

// Minimal HTML escaper for server-supplied names rendered via innerHTML.
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- Timeline chart ---
function renderTimelineChart(events) {
  let wrap = document.getElementById("tl-wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "tl-wrap";
    wrap.innerHTML = `<div class="tl-header"><span class="tl-title">Timeline</span><button class="tl-toggle">−</button></div><canvas id="tl-canvas"></canvas>`;
    eventsEl.parentNode.insertBefore(wrap, eventsEl);
    wrap.querySelector(".tl-toggle").addEventListener("click", () => {
      _timelineExpanded = !_timelineExpanded;
      const c = document.getElementById("tl-canvas");
      if (c) c.style.display = _timelineExpanded ? "" : "none";
      wrap.querySelector(".tl-toggle").textContent = _timelineExpanded ? "−" : "+";
      if (_timelineExpanded && eventsEl._allEvents) drawTimeline(eventsEl._allEvents);
    });
  }
  drawTimeline(events);
}
function drawTimeline(events) {
  const canvas = document.getElementById("tl-canvas");
  if (!canvas) return;
  const sorted = [...events].filter(e => e.magnitude != null && e.occurred_at).sort((a, b) => new Date(a.occurred_at) - new Date(b.occurred_at));
  if (sorted.length < 2) { canvas.style.display = "none"; return; }
  canvas.style.display = "";
  const w = canvas.width = canvas.parentElement.clientWidth - 4 || 228;
  const h = canvas.height = 120;
  const ctx = canvas.getContext("2d");
  const pad = { top: 6, right: 6, bottom: 18, left: 30 };
  const pw = w - pad.left - pad.right, ph = h - pad.top - pad.bottom;
  const t0 = new Date(sorted[0].occurred_at).getTime(), t1 = new Date(sorted[sorted.length - 1].occurred_at).getTime(), ts = t1 - t0 || 1;
  const mm0 = Math.max(0, Math.min(...sorted.map(e => e.magnitude)) - 0.3), mm1 = Math.max(...sorted.map(e => e.magnitude)) + 0.3, ms = mm1 - mm0 || 1;
  const x = e => pad.left + ((new Date(e.occurred_at).getTime() - t0) / ts) * pw;
  const y = e => pad.top + ph - ((e.magnitude - mm0) / ms) * ph;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#eee"; ctx.lineWidth = 1; ctx.font = "9px sans-serif";
  for (let m = Math.ceil(mm0); m <= Math.floor(mm1); m++) {
    const yy = pad.top + ph - ((m - mm0) / ms) * ph;
    ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(w - pad.right, yy); ctx.stroke();
    ctx.fillStyle = "#ccc"; ctx.textAlign = "right"; ctx.fillText(m + ".0", pad.left - 4, yy + 3);
  }
  ctx.textAlign = "center"; ctx.fillStyle = "#ccc";
  for (let i = 0; i < Math.min(4, sorted.length); i++) {
    const idx = Math.floor((i / (Math.min(4, sorted.length) - 1)) * (sorted.length - 1));
    ctx.fillText(new Date(sorted[idx].occurred_at).toLocaleDateString(), x(sorted[idx]), h - 4);
  }
  const AC = { green: "#28a745", yellow: "#ffc107", orange: "#fd7e14", red: "#dc3545" };
  sorted.forEach(e => {
    ctx.beginPath(); ctx.arc(x(e), y(e), 4, 0, Math.PI * 2);
    ctx.fillStyle = AC[e.alert] || "#666";
    ctx.fill(); ctx.strokeStyle = "#fff"; ctx.lineWidth = 1; ctx.stroke();
  });
  canvas.onmousemove = function(ev) {
    const r = canvas.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    for (const e of sorted) {
      if ((mx - x(e)) ** 2 + (my - y(e)) ** 2 < 64) {
        canvas.title = `M${e.magnitude.toFixed(1)} ${e.place || ""} (${new Date(e.occurred_at).toLocaleDateString()})`;
        canvas.style.cursor = "pointer"; return;
      }
    }
    canvas.title = ""; canvas.style.cursor = "default";
  };
  canvas.onclick = function(ev) {
    const r = canvas.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    for (const e of sorted) {
      if ((mx - x(e)) ** 2 + (my - y(e)) ** 2 < 64) { showImpact(e.id); return; }
    }
  };
}
// --- Comparison mode ---
function toggleCompareMode() {
  _compareMode = !_compareMode;
  if (!_compareMode) exitComparison();
  _compareIds = [];
  if (eventsEl._allEvents) renderEventList(eventsEl._allEvents, eventsEl._total);
  updateCompareBar();
}
function selectForComparison(id) {
  const idx = _compareIds.indexOf(id);
  if (idx >= 0) _compareIds.splice(idx, 1);
  else if (_compareIds.length < 2) _compareIds.push(id);
  else _compareIds = [_compareIds[1], id];
  if (eventsEl._allEvents) renderEventList(eventsEl._allEvents, eventsEl._total);
  updateCompareBar();
}
function updateCompareBar() {
  let bar = document.getElementById("compare-bar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "compare-bar";
    eventsEl.parentNode.insertBefore(bar, document.getElementById("tl-wrap") || eventsEl);
  }
  if (!_compareMode) { bar.style.display = "none"; return; }
  bar.style.display = "flex";
  bar.innerHTML = `<span class="cmp-count">${_compareIds.length}/2 selected</span><button class="cmp-show"${_compareIds.length < 2 ? " disabled" : ""}>Compare</button><button class="cmp-exit">Exit</button>`;
  bar.querySelector(".cmp-show").addEventListener("click", showComparison);
  bar.querySelector(".cmp-exit").addEventListener("click", () => toggleCompareMode());
}
async function showComparison() {
  if (_compareIds.length < 2) return;
  const [id1, id2] = _compareIds;
  const [r1, r2] = await Promise.all([
    fetch(`/events/${id1}/impact`, { method: "POST" }),
    fetch(`/events/${id2}/impact`, { method: "POST" }),
  ]);
  if (!r1.ok || !r2.ok) return;
  const [d1, d2] = await Promise.all([r1.json(), r2.json()]);
  const [ev1, ev2] = await Promise.all([
    fetch(`/events/${id1}`).then(r => r.ok ? r.json() : null),
    fetch(`/events/${id2}`).then(r => r.ok ? r.json() : null),
  ]);
  _mmiLayers = {};
  _compLayers.forEach(l => map.removeLayer(l));
  _compLayers = [];
  if (intensityLayer) { map.removeLayer(intensityLayer); intensityLayer = null; }
  const BLUE = ["#dbeafe","#93c5fd","#60a5fa","#3b82f6","#2563eb","#1d4ed8","#1e40af","#1e3a8a","#172554"];
  const ORANGE = ["#fff7ed","#fed7aa","#fdba74","#fb923c","#f97316","#ea580c","#c2410c","#9a3412","#7c2d12"];
  const mkStyle = p => f => { const i = Math.max(0, Math.min(8, (f.properties.mmi_lower || 2) - 2)); const c = p[i]; return { color: c, weight: 1, fillColor: c, fillOpacity: 0.45 }; };
  const l1 = L.geoJSON(d1.bands, { style: mkStyle(BLUE), onEachFeature: (f, l) => l.bindPopup(`Event 1: MMI ${f.properties.mmi_lower}–${f.properties.mmi_upper}`) }).addTo(map);
  const l2 = L.geoJSON(d2.bands, { style: mkStyle(ORANGE), onEachFeature: (f, l) => l.bindPopup(`Event 2: MMI ${f.properties.mmi_lower}–${f.properties.mmi_upper}`) }).addTo(map);
  _compLayers = [l1, l2];
  if (ev1 && ev1.lat != null) _compLayers.push(L.circleMarker([ev1.lat, ev1.lon], { radius: 6, color: "#2563eb", fillColor: "#fff", fillOpacity: 1 }).addTo(map).bindPopup(`Event 1 — M${ev1.magnitude.toFixed(1)}`));
  if (ev2 && ev2.lat != null) _compLayers.push(L.circleMarker([ev2.lat, ev2.lon], { radius: 6, color: "#ea580c", fillColor: "#fff", fillOpacity: 1 }).addTo(map).bindPopup(`Event 2 — M${ev2.magnitude.toFixed(1)}`));
  const b = l1.getBounds().extend(l2.getBounds());
  if (b.isValid()) map.fitBounds(b);
  if (_cmpLegendCtrl) map.removeControl(_cmpLegendCtrl);
  _cmpLegendCtrl = L.control({ position: "bottomright" });
  _cmpLegendCtrl.onAdd = function() {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `<div class="legend-title">Comparison</div><div style="display:flex;align-items:center;gap:6px;font-size:12px;padding:2px 0"><span style="display:inline-block;width:20px;height:14px;border-radius:3px;background:#2563eb"></span>Event 1${ev1 ? " M" + ev1.magnitude.toFixed(1) : ""}</div><div style="display:flex;align-items:center;gap:6px;font-size:12px;padding:2px 0"><span style="display:inline-block;width:20px;height:14px;border-radius:3px;background:#ea580c"></span>Event 2${ev2 ? " M" + ev2.magnitude.toFixed(1) : ""}</div>`;
    return div;
  };
  _cmpLegendCtrl.addTo(map);
}
function exitComparison() {
  _compLayers.forEach(l => map.removeLayer(l));
  _compLayers = [];
  _compareIds = [];
  if (_cmpLegendCtrl) { map.removeControl(_cmpLegendCtrl); _cmpLegendCtrl = null; }
  updateCompareBar();
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
["filter-search", "filter-minmag", "filter-maxmag", "filter-source", "filter-sort", "filter-after", "filter-before"].forEach(id => {
  const el = document.getElementById(id);
  const ev = el.tagName === "SELECT" ? "change" : "input";
  el.addEventListener(ev, () => refreshEvents());
});

// --- Sidebar rail: section switching + collapse ---
const SECTIONS = { event: "sec-event", catalog: "sec-catalog", dashboard: "sec-dashboard", config: "sec-config" };
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
  if (key === activeSection && !sidebarCollapsed) { setCollapsed(true); return; }
  const wasDashboard = activeSection === "dashboard";
  const nowDashboard = key === "dashboard";
  activeSection = key;
  setCollapsed(false);
  document.getElementById("map").style.display = nowDashboard ? "none" : "";
  document.getElementById("dashboard-view").classList.toggle("open", nowDashboard);
  if (nowDashboard && !wasDashboard) renderDashboard();
  if (wasDashboard && !nowDashboard) setTimeout(() => map.invalidateSize(), 100);
  for (const [k, id] of Object.entries(SECTIONS)) {
    document.getElementById(id).style.display = (k === key) ? "block" : "none";
  }
  document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
    b.classList.toggle("active", b.dataset.section === key));
}

// --- Export button ---
document.addEventListener("click", (e) => {
  const menu = document.getElementById("export-menu");
  if (!menu) return;
  if (e.target.closest("#export-btn") || e.target.closest(".export-opt")) return;
  menu.classList.remove("open");
});
document.addEventListener("click", (e) => {
  const btn = e.target.closest("#export-btn");
  if (!btn) return;
  e.stopPropagation();
  document.getElementById("export-menu").classList.toggle("open");
});
document.addEventListener("click", (e) => {
  const opt = e.target.closest(".export-opt");
  if (!opt) return;
  e.stopPropagation();
  const fmt = opt.dataset.format;
  const filter = (eventsEl._filter || "").replace(/^\?limit=\d+/, "");
  window.open("/events/export?format=" + fmt + filter, "_blank");
  document.getElementById("export-menu").classList.remove("open");
});

// --- Dashboard ---
let _dashCharts = [];

function destroyCharts() {
  _dashCharts.forEach(c => c.destroy());
  _dashCharts = [];
}

function animateCounter(el, target, duration = 800) {
  const from = 0;
  const start = performance.now();
  const isFloat = target !== Math.floor(target);
  function tick(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    const val = from + (target - from) * eased;
    el.textContent = isFloat ? val.toFixed(2) : Math.round(val);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function mk(id, conf) {
  const c = document.getElementById(id);
  if (!c) return null;
  const ch = new Chart(c, {
    ...conf,
    options: { responsive: true, maintainAspectRatio: false, ...conf.options },
  });
  _dashCharts.push(ch);
  return ch;
}

const C_ = {
  blue: "#2563eb", orange: "#ea580c", teal: "#0d9488", red: "#dc2626",
  purple: "#7c3aed", amber: "#d97706", green: "#16a34a", gray: "#94a3b8",
};

function barDelay(ctx) {
  const n = Math.max(ctx.chart.data.labels.length, 1);
  return ctx.dataIndex * (900 / n);
}

async function renderDashboard() {
  let resp;
  try { resp = await fetch("/events/stats"); } catch (e) {
    document.getElementById("dash-main").innerHTML = `<div style="color:#999;padding:20px">Network error: ${e.message}</div>`;
    return;
  }
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "unknown");
    document.getElementById("dash-main").innerHTML = `<div style="color:#999;padding:20px">Failed to load stats (HTTP ${resp.status}: ${txt.substring(0, 200)})</div>`;
    return;
  }
  let s;
  try { s = await resp.json(); } catch (e) {
    document.getElementById("dash-main").innerHTML = `<div style="color:#999;padding:20px">Stats response not JSON (${e.message})</div>`;
    return;
  }
  destroyCharts();

  const el = document.getElementById("dash-main");
  const top1 = s.top_significant?.[0];
  el.innerHTML = `
    <div class="dash-stat-grid">
      <div class="dash-stat-box"><div class="dash-stat-val" id="ds-total">0</div><div class="dash-stat-lbl">Recorded Earthquakes</div></div>
      <div class="dash-stat-box"><div class="dash-stat-val" id="ds-meanmag">—</div><div class="dash-stat-lbl">Average Strength</div></div>
      <div class="dash-stat-box"><div class="dash-stat-val" id="ds-maxmag">—</div><div class="dash-stat-lbl">Strongest Event</div></div>
      <div class="dash-stat-box"><div class="dash-stat-val" id="ds-bval">—</div><div class="dash-stat-lbl">Activity Pattern</div></div>
      <div class="dash-stat-box"><div class="dash-stat-val" id="ds-tsunami">0</div><div class="dash-stat-lbl">Tsunami Flags</div></div>
      <div class="dash-stat-box"><div class="dash-stat-val" id="ds-topsig">0</div><div class="dash-stat-lbl">Highest Impact Score</div></div>
    </div>
    <div class="dash-row">
      <div class="dash-card" style="flex:1.4"><canvas id="ch-gr"></canvas></div>
      <div class="dash-card" style="flex:1"><canvas id="ch-depth"></canvas></div>
    </div>
    <div class="dash-row">
      <div class="dash-card"><canvas id="ch-moment"></canvas></div>
    </div>
    <div class="dash-row">
      <div class="dash-card" style="flex:1.2"><canvas id="ch-rate"></canvas></div>
      <div class="dash-card" style="flex:1"><canvas id="ch-hour"></canvas></div>
    </div>
    <div class="dash-row">
      <div class="dash-card" style="flex:1.3"><canvas id="ch-top"></canvas></div>
      <div class="dash-card" style="flex:1"><canvas id="ch-alert"></canvas></div>
    </div>
    <div class="dash-foot">All recorded events · Overview refreshes when opened</div>`;

  animateCounter(document.getElementById("ds-total"), s.total_events);
  if (s.mean_magnitude != null) {
    document.getElementById("ds-meanmag").textContent = s.mean_magnitude.toFixed(2);
  }
  if (s.max_magnitude != null) {
    document.getElementById("ds-maxmag").textContent = s.max_magnitude.toFixed(1);
  }
  document.getElementById("ds-bval").textContent = s.b_value != null ? s.b_value.toFixed(3) : "—";
  animateCounter(document.getElementById("ds-tsunami"), s.tsunami_count);
  animateCounter(document.getElementById("ds-topsig"), top1?.sig ?? 0);

  // --- 1. Gutenberg‑Richter (semi‑log cumulative + per‑bin bars) ---
  const grLbl = s.gr_data.map(r => r.mag_low.toFixed(1));
  mk("ch-gr", {
    type: "line",
    data: {
      labels: grLbl,
      datasets: [
        {
          label: "At least this strong",
          data: s.gr_data.map(r => r.cumulative),
          borderColor: C_.orange,
          backgroundColor: "rgba(234,88,12,0.06)",
          fill: true, tension: 0,
          pointRadius: s.gr_data.map(r => r.cumulative > 0 ? 3 : 0),
          pointBackgroundColor: C_.orange,
          pointHoverRadius: 5,
          order: 1,
        },
        {
          label: "Number in range",
          data: s.gr_data.map(r => r.count),
          backgroundColor: "rgba(234,88,12,0.25)",
          borderColor: "rgba(234,88,12,0.4)",
          borderWidth: 1,
          type: "bar", order: 2, yAxisID: "y1", borderRadius: 2,
        },
      ],
    },
    options: {
      animation: { duration: 1200, easing: "easeOutQuart" },
      plugins: {
        legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
        title: { display: true, text: "How Often Stronger Earthquakes Occur", font: { size: 12, weight: "600" } },
        tooltip: {
          callbacks: {
            label: ctx => ctx.dataset.label === "At least this strong"
              ? `Events at or above this strength: ${ctx.parsed.y}` : `Events in this strength range: ${ctx.parsed.y}`,
          },
        },
      },
      scales: {
        x: { title: { display: true, text: "Earthquake strength", font: { size: 10 } }, ticks: { font: { size: 9 } } },
        y: {
          type: "logarithmic",
          title: { display: true, text: "Number of events", font: { size: 10 } },
          ticks: { font: { size: 9 }, callback: v => v >= 1 ? v : "" },
          min: 0.5,
        },
        y1: {
          position: "right", title: { display: true, text: "Events", font: { size: 10 } },
          grid: { drawOnChartArea: false }, ticks: { font: { size: 9 } },
        },
      },
    },
  });

  // --- 2. Depth distribution (animated bars) ---
  const depthLbl = s.depth_bins.map(r => `${r.depth_low}–${r.depth_low + 10}`);
  mk("ch-depth", {
    type: "bar",
    data: {
      labels: depthLbl,
      datasets: [{
        label: "Events", data: s.depth_bins.map(r => r.count),
        backgroundColor: C_.teal, borderRadius: 3,
      }],
    },
    options: {
      animation: { duration: 1000, easing: "easeOutQuart", delay: barDelay },
      plugins: {
        legend: { display: false },
        title: { display: true, text: "How Deep Earthquakes Occurred", font: { size: 12, weight: "600" } },
      },
      scales: {
        x: { title: { display: true, text: "Depth below ground (km)", font: { size: 10 } }, ticks: { font: { size: 8 }, maxRotation: 60 } },
        y: { beginAtZero: true, ticks: { font: { size: 9 } } },
      },
    },
  });

  // --- 3. Cumulative Moment Release (animated growing line) ---
  const momLbl = s.daily_cumulative.map(d => {
    const p = d.day.split("-");
    return p[1] + "/" + p[2];
  });
  mk("ch-moment", {
    type: "line",
    data: {
      labels: momLbl,
      datasets: [{
        label: "Estimated total energy",
        data: s.daily_cumulative.map(d => d.cum_moment),
        borderColor: C_.blue,
        backgroundColor: ctx => {
          if (!ctx.chart.chartArea) return "transparent";
          const g = ctx.chart.ctx.createLinearGradient(0, ctx.chart.chartArea.top, 0, ctx.chart.chartArea.bottom);
          g.addColorStop(0, "rgba(37,99,235,0.2)"); g.addColorStop(1, "rgba(37,99,235,0.01)");
          return g;
        },
        fill: true, tension: 0.1, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
      }],
    },
    options: {
      animation: { duration: 2000, easing: "easeInOutQuad" },
      plugins: {
        legend: { display: false },
        title: { display: true, text: "Estimated Energy Released Over Time", font: { size: 12, weight: "600" } },
        tooltip: {
          callbacks: {
            label: ctx => `Estimated total: ${(+ctx.parsed.y).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
          },
        },
      },
      scales: {
        x: { ticks: { font: { size: 8 }, maxTicksLimit: 20 } },
        y: {
          title: { display: true, text: "Estimated total energy", font: { size: 10 } },
          ticks: {
            font: { size: 9 },
            callback: v => v >= 1000 ? (v / 1000).toFixed(0) + "k" : v,
          },
        },
      },
    },
  });

  // --- 4. Seismicity Rate (daily bars + 7‑day rolling avg line) ---
  const rateLabels = momLbl;
  const chRate = document.getElementById("ch-rate");
  if (chRate) {
    const ch = new Chart(chRate, {
      type: "bar",
      data: {
        labels: rateLabels,
        datasets: [
          {
            label: "Daily earthquakes",
            data: s.daily_cumulative.map(d => d.count),
            backgroundColor: "rgba(37,99,235,0.25)",
            borderWidth: 0, order: 2, borderRadius: 2,
          },
          {
            label: "7-day trend",
            data: s.daily_cumulative.map(d => d.rate_7day),
            type: "line",
            borderColor: C_.red,
            fill: false, tension: 0.3, pointRadius: 0, pointHoverRadius: 4,
            borderWidth: 2.5, order: 1,
          },
        ],
      },
      options: {
        animation: { duration: 1500, easing: "easeOutQuart" },
        plugins: {
          legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
          title: { display: true, text: "Daily Earthquake Activity", font: { size: 12, weight: "600" } },
        },
        scales: {
          x: { ticks: { font: { size: 8 }, maxTicksLimit: 20 } },
          y: { beginAtZero: true, ticks: { font: { size: 9 } } },
        },
      },
    });
    _dashCharts.push(ch);
  }

  // --- 5. Diurnal Periodicity (animated 24h bars) ---
  const hrLbl = s.hour_dist.map(h => h.hour.toString().padStart(2, "0") + ":00");
  const hrCnt = s.hour_dist.map(h => h.count);
  const hrMax = Math.max(...hrCnt, 1);
  const hrColors = hrCnt.map(v => `rgba(124,58,237,${0.2 + (v / hrMax) * 0.65})`);
  mk("ch-hour", {
    type: "bar",
    data: {
      labels: hrLbl,
      datasets: [{
        label: "Events", data: hrCnt,
        backgroundColor: hrColors, borderRadius: 2,
      }],
    },
    options: {
      animation: { duration: 1200, easing: "easeOutQuart", delay: barDelay },
      plugins: {
        legend: { display: false },
        title: { display: true, text: "Time of Day Pattern (UTC)", font: { size: 12, weight: "600" } },
        tooltip: { callbacks: { label: ctx => `${ctx.parsed.y} events` } },
      },
      scales: {
        x: { ticks: { font: { size: 8 }, maxTicksLimit: 12 } },
        y: { beginAtZero: true, ticks: { font: { size: 9 } } },
      },
    },
  });

  // --- 6. Most Significant Events (animated horizontal bars) ---
  const alertColors = { green: C_.green, yellow: C_.amber, orange: C_.orange, red: C_.red, none: C_.gray };
  mk("ch-top", {
    type: "bar",
    data: {
      labels: s.top_significant.map(e => (e.place || "?").substring(0, 24)),
      datasets: [{
        label: "Impact score",
        data: s.top_significant.map(e => e.sig),
        backgroundColor: s.top_significant.map(e => alertColors[e.alert] || alertColors.none),
        borderRadius: 3,
      }],
    },
    options: {
      indexAxis: "y",
      animation: { duration: 1000, easing: "easeOutQuart", delay: ctx => ctx.dataIndex * 60 },
      plugins: {
        legend: { display: false },
        title: { display: true, text: "Events Needing Most Attention", font: { size: 12, weight: "600" } },
        tooltip: {
          callbacks: {
            label: ctx => {
              const e = s.top_significant[ctx.dataIndex];
              return `Impact: ${e.sig} · Strength: ${e.magnitude?.toFixed(1) ?? "?"}`;
            },
          },
        },
      },
      scales: {
        x: { beginAtZero: true, ticks: { font: { size: 9 } } },
        y: { ticks: { font: { size: 9 } } },
      },
    },
  });

  // --- 7. Alert Distribution (animated rotated doughnut) ---
  mk("ch-alert", {
    type: "doughnut",
    data: {
      labels: s.alert_dist.map(a =>
        a.alert === "none" ? "No Alert" : a.alert.charAt(0).toUpperCase() + a.alert.slice(1)
      ),
      datasets: [{
        data: s.alert_dist.map(a => a.count),
        backgroundColor: s.alert_dist.map(a => alertColors[a.alert] || alertColors.none),
        borderWidth: 2, borderColor: "#fff",
      }],
    },
    options: {
      animation: { animateRotate: true, duration: 1200, easing: "easeOutQuart" },
      cutout: "55%",
      plugins: {
        legend: { position: "bottom", labels: { font: { size: 10 }, boxWidth: 12 } },
        title: { display: true, text: "Current Alert Levels", font: { size: 12, weight: "600" } },
      },
    },
  });
}

document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
  b.addEventListener("click", () => showSection(b.dataset.section)));
document.getElementById("rail-collapse")
  .addEventListener("click", () => setCollapsed(!sidebarCollapsed));

showSection("event"); // default panel on load
