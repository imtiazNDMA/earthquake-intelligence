// ============================================================
//  Icon system — one coherent visual language.
//  • Base: crisp inline SVGs (Lucide-style, inherit currentColor) — always work.
//  • Upgrade: set a Lordicon "Copy CDN link" url as `src` below and that icon
//    renders as an animated <lord-icon> instead. Until then the SVG shows, so
//    nothing is ever broken.  Browse the `page` url, click "Copy CDN link".
// ============================================================
const LORD_ICONS = {
  //  key        page (browse → "Copy CDN link" → paste into src)                          src (paste here)
  event:     { page: "https://lordicon.com/icons/system/regular/12-plus",        src: "" },
  catalog:   { page: "https://lordicon.com/icons/system/regular/2-line-list",     src: "" },
  aftershock:{ page: "https://lordicon.com/icons/system/regular/61-target",      src: "" },
  dashboard: { page: "https://lordicon.com/icons/system/regular/10-analytics",    src: "" },
  config:    { page: "https://lordicon.com/icons/system/regular/53-settings",     src: "" },
  refresh:   { page: "https://lordicon.com/icons/system/regular/103-refresh",     src: "" },
  edit:      { page: "https://lordicon.com/icons/system/regular/18-edit",         src: "" },
  trash:     { page: "https://lordicon.com/icons/system/regular/39-trash",        src: "" },
};

const SVG_PATHS = {
  plus:     '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  list:     '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  chart:    '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  "chevron-left":  '<polyline points="15 18 9 12 15 6"/>',
  "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
  refresh:  '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  edit:     '<path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/>',
  save:     '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
  trash:    '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
  x:        '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  check:    '<polyline points="20 6 9 17 4 12"/>',
  info:     '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  alert:    '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  pin:      '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  user:     '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  zap:      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  building: '<path d="M3 21h18"/><path d="M5 21V7l8-4v18"/><path d="M19 21V11l-6-4"/>',
  waves:    '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 12c.6.5 1.2 1 2.5 1C7 13 7 11 9.5 11c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 18c.6.5 1.2 1 2.5 1C7 19 7 17 9.5 17c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
  target:   '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
  maximize: '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
  moon:     '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  sun:      '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>',
};

const MMI_STYLE = { opacity: 0.45 };

// Inline-SVG markup for a named icon (inherits text color via currentColor).
function svgIcon(name, size = 16) {
  const p = SVG_PATHS[name];
  if (!p) return "";
  return `<svg class="ic ic-${name}" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
}

// Rail icon: animated Lordicon if a CDN url is configured, else the SVG fallback.
function railIconMarkup(key, glyph, active) {
  const L = LORD_ICONS[key];
  if (L && L.src) {
    const primary = active ? "#ffffff" : "#5B6675";
    return `<lord-icon src="${L.src}" trigger="loop-on-hover" colors="primary:${primary}" style="width:20px;height:20px"></lord-icon>`;
  }
  return svgIcon(glyph, 20);
}

// ---- Toasts, spinner, skeletons (feedback states) ----
function _toastHost() {
  let h = document.getElementById("toast-host");
  if (!h) {
    h = document.createElement("div");
    h.id = "toast-host";
    h.setAttribute("aria-live", "polite");
    document.body.appendChild(h);
  }
  return h;
}
const _TOAST_IC = { success: "check", error: "alert", warn: "alert", info: "info" };
// Transient notification. type: success | error | warn | info.
function toast(message, type = "info", duration = 3800) {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.setAttribute("role", type === "error" ? "alert" : "status");
  t.innerHTML = `${svgIcon(_TOAST_IC[type] || "info", 15)}<div class="toast-msg"></div><button class="toast-close" aria-label="Dismiss">${svgIcon("x", 13)}</button>`;
  t.querySelector(".toast-msg").textContent = message;
  _toastHost().appendChild(t);
  requestAnimationFrame(() => t.classList.add("show"));
  let timer = setTimeout(close, duration);
  function close() { clearTimeout(timer); t.classList.remove("show"); setTimeout(() => t.remove(), 280); }
  t.querySelector(".toast-close").addEventListener("click", close);
  t.addEventListener("mouseenter", () => clearTimeout(timer));
  t.addEventListener("mouseleave", () => { timer = setTimeout(close, 1500); });
  return close;
}

function spinnerHTML() { return '<span class="spinner" aria-hidden="true"></span>'; }

// Placeholder rows shown while the catalog is loading.
function catalogSkeleton(n = 5) {
  let s = '<div style="display:flex;align-items:center;gap:4px"><strong>Catalog</strong></div>';
  for (let i = 0; i < n; i++) {
    s += `<div class="skel-card"><div class="skeleton skel-line" style="width:${42 + (i * 11) % 40}%"></div>` +
         `<div class="skeleton skel-line" style="width:${62 + (i * 7) % 28}%"></div></div>`;
  }
  return s;
}

const map = L.map("map").setView([30.4, 69.3], 5); // Primary Focus Country: Pakistan
map.createPane("referencePane");
map.getPane("referencePane").style.zIndex = 410;
map.getPane("referencePane").style.pointerEvents = "none";
map.on("click", () => {
  if (_selectedMmiLevel != null) {
    _selectedMmiLevel = null;
    Object.values(_legendItems).forEach(el => el.classList.remove("selected"));
    _applyMmiStyles();
  }
});

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
  "Voyager": L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: CARTO_ATTR, subdomains: "abcd", maxZoom: 20,
  }),
  "Dark (Dark Matter)": L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: CARTO_ATTR, subdomains: "abcd", maxZoom: 20,
  }),
  "CyclOSM": L.tileLayer("https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png", {
    attribution: OSM_ATTR + " © CyclOSM", subdomains: "abc", maxZoom: 20,
  }),
  "Transport (OPNVKarte)": L.tileLayer("https://tileserver.memomaps.de/tilegen/{z}/{x}/{y}.png", {
    attribution: OSM_ATTR + " © ÖPNVKarte", maxZoom: 18,
  }),
  "Satellite (Esri)": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: ESRI_ATTR + ", Maxar, Earthstar Geographics", maxZoom: 19,
  }),
};
BASEMAPS["OpenStreetMap"].addTo(map); // default basemap

// --- Vector-tile reference overlays (protomaps-leaflet over pmtiles) ---
// `dataLayer` MUST equal the tippecanoe -l layer id used in scripts/build_tiles.py.

const OVERLAY_CONFIG = {
  National:        { id: "national",         color: "#444",   width: 1.5, defaultOn: true, opacity: 1, hoverFields: ["Name", "name", "NAME"], hoverTolerancePx: 16 },
  Provinces:       { id: "provinces",        color: "#666",   width: 1.0, defaultOn: true, opacity: 1, hoverFields: ["Name", "name", "NAME", "province", "PROVINCE"], hoverTolerancePx: 16 },
  Districts:       { id: "districts",        color: "#999",   width: 0.6, defaultOn: false, opacity: 0.8, hoverFields: ["Name", "name", "NAME", "district", "DISTRICT"], hoverTolerancePx: 16 },
  Tehsils:         { id: "tehsils",          color: "#bbb",   width: 0.4, defaultOn: false, opacity: 0.7, hoverFields: ["Name", "name", "NAME", "tehsil", "TEHSIL"], hoverTolerancePx: 16 },
  "Global Faults": { id: "faults",           color: "#C42A2E", width: 0.8, defaultOn: false, lineOnly: true, faultStyle: true, opacity: 0.9, hoverTolerancePx: 12 },
  "Plate boundaries": { id: "plate_boundaries", color: "#D8B22C", width: 1.6, defaultOn: false, lineOnly: true, opacity: 0.85, hoverFields: ["Name_Full", "Name"], hoverTolerancePx: 12 },
  "Pakistan Major": { id: "pak_faults_major", color: "#C42A2E", width: 1.1, defaultOn: true, lineOnly: true, faultStyle: true, opacity: 0.9, hoverFields: ["Name", "Symbols", "Type"], hoverTolerancePx: 12 },
  // 34 named faults characterised with Mmax and slip rate — the hazard-relevant
  // attributes. "Pakistan Major" above has finer geometry but its Type/Symbols
  // columns are almost entirely empty, so the two complement rather than repeat.
  "Major Faults": { id: "major_faults", color: "#A67C1F", width: 1.4, defaultOn: false,
                    lineOnly: true, faultStyle: true, opacity: 0.95,
                    hoverFields: ["FAULTNAME", "Fault_Type", "Mmax", "Slip_rate"],
                    // null label = the name is the tooltip's heading, not a field.
                    hoverLabels: { FAULTNAME: null, Fault_Type: "Type", Mmax: "Mmax",
                                   Slip_rate: "Slip rate" },
                    hoverUnits: { Slip_rate: "mm/yr" },
                    hoverTolerancePx: 12 },
  "Tectonic Zones":{ id: "pak_tectonic_zones", color: "#8C5A3C", width: 0.5, defaultOn: false,
                     fillColor: "#8C5A3C", fillOpacity: 0.3, opacity: 0.7 },
};

const DEFAULT_HOVER_FIELDS = ["Name", "name", "Fault_Name", "FAULT", "fault", "TYPE", "Type", "type", "Length_km", "Fault_Leng", "SlipRate"];

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
    this.opacity = opts.opacity ?? 1;
    this.spacing = opts.spacing ?? 28;
    this.size = opts.size ?? 5;
  }
  draw(ctx, geom) {
    ctx.save();
    ctx.globalAlpha = this.opacity;
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
  const paintRules = [{
    dataLayer: c.id,
    symbolizer: _buildSymbolizer(name, c),
  }];

  const opts = {
    url: `/tiles/${c.id}.pmtiles`,
    paintRules,
    backgroundColor: "rgba(0,0,0,0)",
    pane: "referencePane",
  };

  return protomapsL.leafletLayer(opts);
}

function _setupFaultHover() {
  let tip = null;
  let lastQuery = 0;
  const THROTTLE = 50;

  function hoverQueryPoints(e, tolerancePx) {
    if (!tolerancePx) return [map.wrapLatLng(e.latlng)];
    const p = e.containerPoint;
    return [
      p,
      L.point(p.x - tolerancePx, p.y),
      L.point(p.x + tolerancePx, p.y),
      L.point(p.x, p.y - tolerancePx),
      L.point(p.x, p.y + tolerancePx),
    ].map(pt => map.wrapLatLng(map.containerPointToLatLng(pt)));
  }

  function needsHover(name) {
    const cfg = OVERLAY_CONFIG[name];
    return !!cfg?.hoverFields || name.includes("Fault") || name.includes("fault") || name === "Tectonic Zones";
  }

  map.on("mousemove", function (e) {
    const now = Date.now();
    if (now - lastQuery < THROTTLE) return;
    lastQuery = now;

    let found = null;

    for (const [name, layer] of Object.entries(OVERLAYS)) {
      if (!map.hasLayer(layer) || !needsHover(name)) continue;
      const c = OVERLAY_CONFIG[name];
      const hoverFields = c.hoverFields ?? DEFAULT_HOVER_FIELDS;
      const hoverPoints = hoverQueryPoints(e, c.hoverTolerancePx ?? ((c.lineOnly || c.faultStyle) ? 8 : 0));
      const hoverTolerancePx = c.hoverTolerancePx ?? ((c.lineOnly || c.faultStyle) ? 8 : 16);
      for (const point of hoverPoints) {
        const results = layer.queryTileFeaturesDebug(point.lng, point.lat, hoverTolerancePx);
        for (const [, features] of results) {
          for (const picked of features) {
            if (picked.layerName !== c.id) continue;
            const props = picked.feature.props;
            const labels = c.hoverLabels || {};
            const units = c.hoverUnits || {};
            const lines = [];
            for (const k of hoverFields) {
              if (props[k] == null || props[k] === "") continue;
              // A configured label wins; otherwise fall back to the raw column
              // name, de-underscored. An explicit null means "no label" — the
              // value stands on its own as the tooltip's heading.
              const label = k in labels ? labels[k] : k.replace(/_/g, " ");
              const unit = units[k] ? ` ${escapeHtml(units[k])}` : "";
              const value = escapeHtml(String(props[k])) + unit;
              lines.push(label ? `${escapeHtml(label)}: ${value}` : `<b>${value}</b>`);
            }
            if (lines.length === 0) lines.push(escapeHtml(name));
            const html = hoverFields.length === 1 && lines.length === 1
              ? escapeHtml(String(props[hoverFields[0]]))
              : lines.join("<br>");
            found = { latlng: e.latlng, html };
            break;
          }
          if (found) break;
        }
        if (found) break;
      }
      if (found) break;
    }

    if (found) {
      if (!tip) tip = L.tooltip({ direction: "top", offset: L.point(0, -8), className: "fault-tooltip" });
      tip.setLatLng(found.latlng).setContent(found.html).addTo(map);
    } else if (tip) {
      tip.remove();
      tip = null;
    }
  });

  map.on("mouseout", function () {
    if (tip) { tip.remove(); tip = null; }
  });
}

function _buildSymbolizer(overlayName, c) {
  const opacity = c.opacity ?? 1;
  if (overlayName === "Tectonic Zones" || c.fillColor) {
    const fillOpacity = c.fillOpacity ?? opacity;
    if (overlayName === "Tectonic Zones") {
      return new NamedPolySymbolizer({ prop: "Name", stroke: c.color, width: c.width, opacity: fillOpacity });
    }
    return new protomapsL.PolygonSymbolizer({ fill: c.fillColor ?? "rgba(0,0,0,0)", opacity: fillOpacity, stroke: c.color, width: c.width });
  }
  if (c.faultStyle) {
    return new FaultLineSymbolizer({ color: c.color, width: c.width, opacity });
  }
  if (c.lineOnly) {
    return new protomapsL.LineSymbolizer({ color: c.color, width: c.width, opacity });
  }
  return new protomapsL.PolygonSymbolizer({ fill: "rgba(0,0,0,0)", opacity: 1, stroke: c.color, width: c.width });
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
_setupFaultHover();

// Move the zoom control clear of the left-edge sidebar shell.
map.zoomControl.setPosition("topright");

// --- Map config panel: overlay checklist + basemap radios ---
const BASEMAP_NAMES = Object.keys(BASEMAPS);
let currentBasemap = "OpenStreetMap";
let _userPickedBasemap = false;   // once true, theme no longer auto-switches the basemap
const _basemapRadios = {};        // name -> radio input, for keeping the config panel in sync
function setBasemap(name) {
  if (!BASEMAPS[name] || name === currentBasemap) return;
  if (BASEMAPS[currentBasemap] && map.hasLayer(BASEMAPS[currentBasemap])) {
    map.removeLayer(BASEMAPS[currentBasemap]);
  }
  BASEMAPS[name].addTo(map);
  if (typeof BASEMAPS[name].bringToBack === "function") BASEMAPS[name].bringToBack();
  currentBasemap = name;
}

function refreshMmiLayerStyles() {
  if (intensityLayer) intensityLayer.setStyle(style);
  _compLayers.forEach((layer) => {
    if (typeof layer.setStyle === "function" && layer.feature == null) layer.setStyle({
      opacity: MMI_STYLE.opacity,
      fillOpacity: MMI_STYLE.opacity,
    });
  });
}

function buildMmiOpacityControl() {
  const section = document.getElementById("sec-config");
  if (!section) return;

  const group = document.createElement("div");
  group.className = "cfg-group";
  const title = document.createElement("div");
  title.className = "field-label";
  title.textContent = "MMI intensity";
  const row = document.createElement("label");
  row.className = "cfg-row";
  const txt = document.createElement("span");
  txt.className = "ov-name";
  txt.textContent = "Polygon opacity";
  const controls = document.createElement("span");
  controls.className = "ov-controls";
  const slider = document.createElement("input");
  slider.type = "range";
  slider.className = "ov-opacity";
  slider.min = "0";
  slider.max = "1";
  slider.step = "0.05";
  slider.value = String(MMI_STYLE.opacity);
  slider.title = "MMI polygon opacity";
  const value = document.createElement("span");
  value.className = "cfg-value";
  const syncValue = () => { value.textContent = `${Math.round(parseFloat(slider.value) * 100)}%`; };
  syncValue();
  slider.addEventListener("input", () => {
    MMI_STYLE.opacity = parseFloat(slider.value);
    syncValue();
    refreshMmiLayerStyles();
  });
  controls.append(slider, value);
  row.append(txt, controls);
  group.append(title, row);
  section.appendChild(group);
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
    // Opacity slider for all layers (controls line + fill opacity together).
    const o = document.createElement("input");
    o.type = "range";
    o.className = "ov-opacity";
    o.min = "0"; o.max = "1"; o.step = "0.05"; o.value = c.opacity ?? 1;
    o.title = "Opacity";
    o.addEventListener("input", () => {
      const v = parseFloat(o.value);
      c.opacity = v;
      if (c.fillOpacity != null) c.fillOpacity = v;
      rebuildOverlay(name);
    });
    controls.appendChild(o);
    row.append(cb, sw, txt, controls);
    ovEl.appendChild(row);
    if (c.note) {
      const note = document.createElement("div");
      note.className = "cfg-note overlay-note";
      note.textContent = c.note;
      ovEl.appendChild(note);
    }
  });

  const bmEl = document.getElementById("basemap-list");
  BASEMAP_NAMES.forEach((name) => {
    const row = document.createElement("label");
    row.className = "cfg-row";
    const rb = document.createElement("input");
    rb.type = "radio";
    rb.name = "basemap";
    rb.checked = (name === currentBasemap);
    _basemapRadios[name] = rb;
    rb.addEventListener("change", () => { if (rb.checked) { _userPickedBasemap = true; setBasemap(name); } });
    const txt = document.createElement("span");
    txt.textContent = name;
    row.append(rb, txt);
    bmEl.appendChild(row);
  });
}
buildConfigPanel();
buildMmiOpacityControl();

// MMI legend (colors mirror _MMI_COLORS in src/eqmon/contours.py).
const MMI_PALETTE = [
  [2, "#bfccff"], [3, "#a0e6ff"], [4, "#80ffff"], [5, "#7aff93"],
  [6, "#ffff00"], [7, "#ffc800"], [8, "#ff9100"], [9, "#ff0000"], [10, "#c80000"],
];

// MMI class -> [Roman numeral, perceived-shaking descriptor]. Mirrors MMI_CLASSES
// in src/eqmon/config.py (the classification_range.md scheme). Class I is "Not
// Felt": never contoured, shown only as the un-shaded-background reference row.
const MMI_CLASSES = {
  1: ["I", "Not Felt"], 2: ["II", "Weak"], 3: ["III", "Weak"], 4: ["IV", "Light"],
  5: ["V", "Moderate"], 6: ["VI", "Strong"], 7: ["VII", "Very Strong"],
  8: ["VIII", "Severe"], 9: ["IX", "Violent"], 10: ["X", "Extreme"],
};
function mmiClassLabel(level) {
  const [roman, name] = MMI_CLASSES[level] || [String(level), ""];
  return name ? `${roman} (${name})` : roman;
}

let _legendItems = {};
let _mmiLayers = {};
let _lastFc = null;
let _legendDiv = null;
const _legendCheckboxes = {};
let _selectedMmiLevel = null;

function _applyMmiStyles() {
  Object.entries(_mmiLayers).forEach(([k, layers]) => {
    const level = parseInt(k);
    const isHover = _hoveredMmiLevel === level;
    const isSelected = _selectedMmiLevel === level;
    const w = isSelected ? 3 : isHover ? 2.5 : 1;
    const fo = isSelected ? 0.8 : isHover ? 0.7 : 0.45;
    layers.forEach(l => l.setStyle({ weight: w, fillOpacity: fo }));
  });
}

let _hoveredMmiLevel = null;

function highlightByLevel(level) {
  _hoveredMmiLevel = level;
  Object.keys(_legendItems).forEach(k => {
    _legendItems[k].classList.toggle("active", parseInt(k) === level);
  });
  _applyMmiStyles();
}

function unhighlightAll() {
  _hoveredMmiLevel = null;
  Object.values(_legendItems).forEach(el => el.classList.remove("active"));
  _applyMmiStyles();
}

function selectMmiLevel(level) {
  if (_selectedMmiLevel === level) {
    _selectedMmiLevel = null; // deselect
  } else {
    _selectedMmiLevel = level;
  }
  Object.keys(_legendItems).forEach(k => {
    const el = _legendItems[k];
    el.classList.toggle("selected", parseInt(k) === _selectedMmiLevel);
  });
  _applyMmiStyles();
}

function presentLevels(fc) {
  const set = new Set((fc && fc.features ? fc.features : []).map(f => (f.properties || {}).mmi_lower));
  return MMI_PALETTE.map(([m]) => m).filter(m => set.has(m));
}

function updateExportEnabled() {
  const btn = _legendDiv && _legendDiv.querySelector("#legend-export");
  if (!btn) return;
  const anyChecked = Object.values(_legendCheckboxes).some(cb => cb.checked);
  btn.disabled = !(_lastFc && anyChecked);
}

// Render the MMI ladder: one rung per band, severe at the top so the spine
// reads like the map (hot core first). A rung is pressed when its band is
// included in the shapefile export; the hidden checkbox keeps the export
// selection API unchanged.
function renderLegend(fc) {
  if (!_legendDiv) return;
  _legendItems = {};
  Object.keys(_legendCheckboxes).forEach(k => delete _legendCheckboxes[k]);
  const colorOf = Object.fromEntries(MMI_PALETTE);
  const hasData = !!(fc && fc.features && fc.features.length);
  const levels = hasData ? presentLevels(fc) : MMI_PALETTE.map(([m]) => m);

  let html = `<div class="ladder-cap">Mercalli band</div><div class="ladder-rungs">`;
  levels.slice().reverse().forEach(m => {
    const [roman, name] = MMI_CLASSES[m] || [String(m), ""];
    const cb = hasData
      ? `<input type="checkbox" class="legend-cb" data-level="${m}" checked hidden aria-label="Include MMI ${mmiClassLabel(m)} in export">`
      : "";
    html += `<button type="button" class="rung" data-level="${m}" aria-pressed="${hasData}"` +
      ` title="MMI ${roman} — ${name}">${cb}` +
      `<span class="rung-fill" style="background:${colorOf[m]}"></span>` +
      `<span class="rung-num">${roman}</span>` +
      `<span class="rung-label">${roman} · ${name}</span></button>`;
  });
  // Class I (Not Felt) is never contoured (no band below MMI 2); show it as a
  // dashed reference rung so the full scheme is represented.
  html += `<span class="rung rung-note" title="MMI I — Not Felt">` +
    `<span class="rung-fill"></span><span class="rung-num">I</span>` +
    `<span class="rung-label">I · Not Felt</span></span>`;
  // Both actions belong to the footprint the ladder describes, so they live
  // with it — the exposure strip would strand them, it only appears for
  // catalog events and never for a hand-drawn footprint.
  html += `</div><button type="button" id="ladder-arc" class="ladder-export ladder-arc"` +
    `${hasData ? "" : " disabled"} title="Count people and infrastructure under the shaking">` +
    `At risk</button>`;
  html += `<button type="button" id="legend-export" class="ladder-export"` +
    `${hasData ? "" : " disabled"}>Export</button>`;
  _legendDiv.innerHTML = html;

  _legendDiv.querySelectorAll(".rung[data-level]").forEach(el => {
    const level = parseInt(el.dataset.level);
    el.addEventListener("mouseenter", () => highlightByLevel(level));
    el.addEventListener("mouseleave", () => unhighlightAll());
    el.addEventListener("focus", () => highlightByLevel(level));
    el.addEventListener("blur", () => unhighlightAll());
    el.addEventListener("click", () => {
      const cb = _legendCheckboxes[level];
      if (!cb) return;
      cb.checked = !cb.checked;
      el.setAttribute("aria-pressed", String(cb.checked));
      updateExportEnabled();
    });
    _legendItems[level] = el;
  });
  _legendDiv.querySelectorAll(".legend-cb").forEach(cb => {
    _legendCheckboxes[parseInt(cb.dataset.level)] = cb;
  });
  const btn = _legendDiv.querySelector("#legend-export");
  if (btn) btn.addEventListener("click", exportShapefile);
  const arcBtn = _legendDiv.querySelector("#ladder-arc");
  if (arcBtn) arcBtn.addEventListener("click", _arcRun);
  updateExportEnabled();
}

async function exportShapefile() {
  if (!_lastFc) return;
  const levels = new Set(
    Object.entries(_legendCheckboxes).filter(([, cb]) => cb.checked).map(([level]) => parseInt(level))
  );
  const features = _lastFc.features.filter(f => levels.has((f.properties || {}).mmi_lower));
  if (!features.length) { toast("Select at least one MMI band to export", "error"); return; }
  toast(`Exporting ${levels.size} MMI band(s) (${features.length} feature(s)) as shapefile…`, "info");
  try {
    const resp = await fetch("/intensity/export/shapefile", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "FeatureCollection", features }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      toast("Export failed: " + JSON.stringify(err.detail ?? err), "error");
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "mmi_bands.zip";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast("Export request failed: " + e.message, "error");
  }
}

// The ladder is a fixed part of the shell (see #mmi-ladder in index.html), not
// a Leaflet control — it spans the full height of the map's right edge.
_legendDiv = document.getElementById("mmi-ladder");

function _showLegend(fc) {
  if (!_legendDiv) return;
  _legendDiv.hidden = false;
  document.body.classList.add("has-ladder");
  renderLegend(fc);
}

function _hideLegend() {
  if (!_legendDiv) return;
  _legendDiv.hidden = true;
  document.body.classList.remove("has-ladder");
  _legendDiv.innerHTML = "";
  _legendItems = {};
  Object.keys(_legendCheckboxes).forEach(k => delete _legendCheckboxes[k]);
}

function onMmiFeature(f, l) {
  const level = f.properties.mmi_lower;
  if (!_mmiLayers[level]) _mmiLayers[level] = [];
  _mmiLayers[level].push(l);
  l.bindPopup(`MMI ${mmiClassLabel(level)}<br><small>Click to select this band</small>`);
  l.on("mouseover", () => { _hoveredMmiLevel = level; highlightByLevel(level); });
  l.on("mouseout", () => { _hoveredMmiLevel = null; unhighlightAll(); });
  l.on("click", (e) => {
    L.DomEvent.stopPropagation(e);
    selectMmiLevel(level);
  });
}

let intensityLayer = null;
let epicenterMarker = null;
let _mmiVisible = true;
let _currentEvent = null;
const statusEl = document.getElementById("status");
// --- Comparison mode state ---
let _compareMode = false;
let _compareIds = [];
let _compLayers = [];
let _cmpLegendCtrl = null;
let _timelineExpanded = true;

async function fetchAdmin(url, options = {}) {
  return fetch(url, options);
}

function ingestErrorMessage(response, body) {
  if (response.status === 409) return "Another ingest is already running. Try again shortly.";
  return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
}

function style(feature) {
  return {
    color: feature.properties.color,
    weight: 1,
    opacity: MMI_STYLE.opacity,
    fillColor: feature.properties.color,
    fillOpacity: MMI_STYLE.opacity,
  };
}

function makeEpicenterMarker(lat, lon, color, popupText) {
  const icon = L.divIcon({
    className: "epicenter-star-wrap",
    html: `<svg class="epicenter-star" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M12 2.6l2.78 5.63 6.22.91-4.5 4.38 1.06 6.19L12 16.79 6.44 19.71l1.06-6.19L3 9.14l6.22-.91L12 2.6z" fill="#ffffff" stroke="${color}" stroke-width="2" stroke-linejoin="round"/></svg>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
  return L.marker([lat, lon], { icon }).bindPopup(popupText);
}

function syncMmiToggle() {
  const toggle = document.getElementById("current-mmi-toggle");
  if (toggle) toggle.checked = _mmiVisible;
}

function renderCurrentMmiLayer(fc) {
  _lastFc = fc;
  _mmiLayers = {};
  _selectedMmiLevel = null;
  // The footprint just changed, so any open ARC breakdown describes the old one.
  // (The button itself is re-rendered with the ladder, in renderLegend.)
  if (_arcData) { _arcData = null; _arcClose(); }
  if (intensityLayer) {
    map.removeLayer(intensityLayer);
    intensityLayer = null;
  }
  if (!_mmiVisible) {
    _hideLegend();
    syncMmiToggle();
    return null;
  }
  intensityLayer = L.geoJSON(fc, { style, onEachFeature: onMmiFeature }).addTo(map);
  if (fc.features.length > 0) _showLegend(fc);
  else _hideLegend();
  syncMmiToggle();
  return intensityLayer;
}

function setCurrentMmiVisible(visible) {
  _mmiVisible = visible;
  if (_lastFc) renderCurrentMmiLayer(_lastFc);
  else syncMmiToggle();
  updateCurrentEventCard(_currentEvent);
}

function updateCurrentEventCard(event) {
  const card = document.getElementById("current-event-card");
  if (!card) return;
  const main = document.getElementById("current-event-main");
  const place = document.getElementById("current-event-place");
  const meta = document.getElementById("current-event-meta");
  const label = document.getElementById("current-label");
  const pills = card.querySelector(".current-pills");
  if (!event) {
    _currentEvent = null;
    card.classList.remove("active");
    label.textContent = "No active event";
    main.textContent = "—";
    place.textContent = "Nothing selected";
    meta.textContent = "Draw a footprint or select an event from the catalog.";
    pills.innerHTML = "<span>Epicenter pending</span><span>MMI pending</span>";
    updateStatusBar(null);
    hideExposureStrip();
    return;
  }
  const mag = Number(event.magnitude);
  const depth = Number(event.depth_km);
  const lat = Number(event.lat);
  const lon = Number(event.lon);
  _currentEvent = event;
  card.classList.add("active");
  label.textContent = event.source
    ? `Active event · ${event.source} ${event.source === "PMD" ? "primary" : ""}`.trim()
    : "Active event · manual";
  main.innerHTML = `${Number.isFinite(mag) ? mag.toFixed(1) : "?"}` +
    `<span class="cur-unit">M${event.mag_type ? "" : "w"} · ` +
    `${Number.isFinite(depth) ? depth.toFixed(0) + " KM DEEP" : "DEPTH ?"}</span>`;
  place.textContent = event.place || "Location not named";
  const coords = Number.isFinite(lat) && Number.isFinite(lon)
    ? `${lat.toFixed(2)}° N &nbsp;${lon.toFixed(2)}° E` : "Coordinates pending";
  const when = event.occurred_at
    ? " · Origin " + new Date(event.occurred_at).toLocaleTimeString() : "";
  meta.innerHTML = `${coords}${when}`;
  pills.innerHTML = `<span>Epicenter pinned</span><span>${_mmiVisible ? "MMI visible" : "MMI hidden"}</span>`;
}

async function calculate() {
  const payload = {
    magnitude: parseFloat(document.getElementById("magnitude").value),
    depth_km:  parseFloat(document.getElementById("depth_km").value),
    lat:       parseFloat(document.getElementById("lat").value),
    lon:       parseFloat(document.getElementById("lon").value),
    save_to_catalog: document.getElementById("save-catalog").checked,
  };
  statusEl.innerHTML = spinnerHTML() + " Calculating…";
  try {
    const resp = await fetch("/intensity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      statusEl.textContent = "";
      toast("Intensity calc failed: " + JSON.stringify(err.detail ?? err), "error");
      return;
    }
    const fc = await resp.json();
    renderCurrentMmiLayer(fc);

    if (epicenterMarker) map.removeLayer(epicenterMarker);
    epicenterMarker = makeEpicenterMarker(payload.lat, payload.lon, "#000000", "Epicenter").addTo(map);
    updateCurrentEventCard(payload);
    // A manual footprint has no PAGER alert and no admin rollups, so the strip
    // stays down; the status bar still reports magnitude and peak intensity.
    const peakBand = (fc.features || [])
      .reduce((m, f) => Math.max(m, (f.properties || {}).mmi_lower || 0), 0);
    updateStatusBar({ magnitude: payload.magnitude, source: "MANUAL", alert: null,
                      occurred_at: new Date().toISOString() }, peakBand);
    hideExposureStrip();

    statusEl.textContent = `${fc.features.length} intensity bands`;
    if (intensityLayer && intensityLayer.getBounds().isValid()) map.fitBounds(intensityLayer.getBounds());
    else map.setView([payload.lat, payload.lon], 7);
    if (fc.event_id) { toast("Event saved to catalog", "success"); refreshEvents(); }
  } catch (e) {
    statusEl.textContent = "";
    toast("Request failed: " + e.message, "error");
  }
}

document.getElementById("calc").addEventListener("click", calculate);
document.getElementById("current-mmi-toggle")?.addEventListener("change", (e) =>
  setCurrentMmiVisible(e.target.checked));

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
  if (!append) eventsEl.innerHTML = catalogSkeleton();
  let resp;
  try {
    resp = await fetch(url);
  } catch (e) {
    if (!append) eventsEl.innerHTML = "";
    toast("Couldn't load catalog: " + e.message, "error");
    return;
  }
  if (!resp.ok) {
    if (!append) eventsEl.innerHTML = "";
    toast("Couldn't load catalog (HTTP " + resp.status + ")", "error");
    return;
  }
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
  // Update tab counts (no delay — lightweight COUNT queries)
  updateTabCounts();
}

function renderEventList(events, total) {
  eventsEl.innerHTML = `<div style="display:flex;align-items:center;gap:4px"><strong>Catalog</strong> <span style="color:var(--text-muted);font-weight:400;font-size:15px">${total != null ? "(" + events.length + " of " + total + ")" : ""}</span><button id="cmp-toggle" class="cmp-toggle${_compareMode ? " active" : ""}">${_compareMode ? svgIcon("x", 12) + " Exit" : "Compare"}</button><span class="export-wrap"><button id="export-btn" class="export-btn" title="Download" aria-label="Download">${svgIcon("download", 13)}</button><div id="export-menu" class="export-menu"><a class="export-opt" data-format="csv">CSV</a><a class="export-opt" data-format="geojson">GeoJSON</a></div></span></div>` + (
    events.length === 0 ? '<div style="color:var(--text-muted);padding:8px 0;font-size:16px">No events yet — pull the USGS feed or calculate intensity</div>'
    : events.map(ev => {
    const alertClass = ev.alert ? `evt-alert ${ev.alert}` : "";
    const alertText = ev.alert ? ev.alert.toUpperCase() : "";
    const cmpIdx = _compareIds.indexOf(ev.id);
    const cmpClass = cmpIdx === 0 ? " selected1" : cmpIdx === 1 ? " selected2" : "";
    const magColor = _magColor(ev.magnitude);
    return `<div class="evt${_compareMode ? " evt-comp" : ""}${ev.alert ? " alert-" + ev.alert : ""}" data-id="${ev.id}" tabindex="0" style="--evt-mag-color:${magColor}">
      <button class="evt-del" data-del-id="${ev.id}" title="Delete event" aria-label="Delete event">${svgIcon("x", 12)}</button>
      ${_compareMode ? `<div class="cmp-radio${cmpClass}">${cmpIdx >= 0 ? cmpIdx + 1 : ""}</div>` : ""}
      <div class="evt-head">
        <span class="evt-mag-swatch" aria-hidden="true"></span>
        <span class="evt-mag">M${ev.magnitude.toFixed(1)}${ev.mag_type ? ` <span class="evt-magtype">${escapeHtml(ev.mag_type)}</span>` : ""}</span>
        ${ev.alert ? `<span class="${alertClass}">${alertText}</span>` : ""}
        ${ev.tsunami ? `<span class="evt-tsunami" title="Tsunami warning">${svgIcon("waves", 14)}</span>` : ""}
        ${ev.sig ? `<span class="evt-sig">${ev.sig}</span>` : ""}
      </div>
      ${ev.place ? `<div class="evt-place">${escapeHtml(ev.place)}</div>` : ""}
      <div class="evt-meta">${ev.source} · ${new Date(ev.occurred_at).toLocaleString()}</div>
    </div>`;
  }).join("") + (total != null && events.length < total
    ? `<button id="load-more" style="width:100%;padding:4px;margin-top:6px;cursor:pointer;font-size:15px;background:transparent;color:var(--text);border:1px solid var(--border);border-radius:4px">Load ${Math.min(20, total - events.length)} more…</button>`
    : ""));
  document.querySelectorAll(".evt").forEach(el => {
    const activate = () => _compareMode ? selectForComparison(el.dataset.id) : showImpact(el.dataset.id);
    el.addEventListener("click", (e) => {
      if (e.target.closest(".evt-del")) return;
      activate();
    });
    el.addEventListener("keydown", (e) => {
      if (e.target !== el) return; // ignore keys aimed at the inner delete button
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
    });
  });
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

// --- Confirmation dialog for delete (accessible: focus-trap, Esc, focus restore) ---
const confirmOverlay = document.getElementById("confirm-overlay");
const confirmMsg = document.getElementById("confirm-msg");
const confirmOk = document.getElementById("confirm-ok");
const confirmCancel = document.getElementById("confirm-cancel");
let _pendingDeleteId = null;
let _confirmLastFocus = null;

function confirmDelete(eventId) {
  _pendingDeleteId = eventId;
  _confirmLastFocus = document.activeElement;       // restore here on close
  confirmMsg.textContent = "Delete this event and all its data?";
  confirmOverlay.classList.add("open");
  void confirmOverlay.offsetWidth;  // flush style so the dialog is focusable now
  confirmCancel.focus();            // focus the safe default (Cancel), not Delete
}

function closeConfirm() {
  confirmOverlay.classList.remove("open");
  _pendingDeleteId = null;
  const back = _confirmLastFocus;
  _confirmLastFocus = null;
  if (back && back.isConnected && back.focus) back.focus();
}

confirmOk.addEventListener("click", async () => {
  if (_pendingDeleteId === null) return;
  const id = _pendingDeleteId;
  closeConfirm();
  try {
    const r = await fetchAdmin(`/events/${id}`, { method: "DELETE" });
    if (r.ok) {
      document.getElementById("detail").innerHTML = "";
      impactEl.innerHTML = "";
      refreshEvents();
      toast("Event deleted", "success");
    } else {
      toast("Delete failed (HTTP " + r.status + ")", "error");
    }
  } catch (e) {
    toast("Delete failed: " + e.message, "error");
  }
});

confirmCancel.addEventListener("click", closeConfirm);

confirmOverlay.addEventListener("click", (e) => {
  if (e.target === confirmOverlay) closeConfirm();
});

// Esc closes; Tab cycles between the two buttons (modal focus-trap).
confirmOverlay.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { e.preventDefault(); closeConfirm(); return; }
  if (e.key === "Tab") {
    if (e.shiftKey && document.activeElement === confirmCancel) { e.preventDefault(); confirmOk.focus(); }
    else if (!e.shiftKey && document.activeElement === confirmOk) { e.preventDefault(); confirmCancel.focus(); }
  }
});

async function showImpact(id) {
  _compLayers.forEach(l => map.removeLayer(l));
  _compLayers = [];
  if (_cmpLegendCtrl) { map.removeControl(_cmpLegendCtrl); _cmpLegendCtrl = null; }
  if (_compareMode) toggleCompareMode();
  const detailEl = document.getElementById("detail");
  impactEl.innerHTML = spinnerHTML() + " Computing impact…";
  detailEl.innerHTML = "";
  let evtResp, impactResp;
  try {
    [evtResp, impactResp] = await Promise.all([
      fetch(`/events/${id}`),
      fetch(`/events/${id}/impact`, { method: "POST" }),
    ]);
  } catch (e) {
    impactEl.textContent = "";
    toast("Impact request failed: " + e.message, "error");
    return;
  }
  if (!impactResp.ok) { impactEl.textContent = ""; toast("Impact computation failed", "error"); return; }
  const evt = evtResp.ok ? await evtResp.json() : null;
  const data = await impactResp.json();
  // Render intensity bands on map
  renderCurrentMmiLayer(data.bands);
  const hasBands = data.bands.features.length > 0;
  if (!hasBands) {
    // Deep and/or small events produce surface shaking below MMI 2, so there
    // are no bands to draw. Center on the epicenter and explain the blank map
    // rather than leaving the user to wonder if rendering failed.
    if (evt && evt.lat != null && evt.lon != null) map.setView([evt.lat, evt.lon], 7);
    toast("No mapped intensity — shaking stays below MMI 2 for this event.", "info");
  }
  if (evt && evt.lat != null && evt.lon != null) {
    if (epicenterMarker) map.removeLayer(epicenterMarker);
    epicenterMarker = makeEpicenterMarker(evt.lat, evt.lon, "#000000", `Epicenter — M${evt.magnitude.toFixed(1)}`).addTo(map);
    updateCurrentEventCard(evt);
  }
  if (hasBands && intensityLayer && intensityLayer.getBounds().isValid()) {
    map.fitBounds(intensityLayer.getBounds());
  } else if (evt && evt.lat != null && evt.lon != null) {
    map.setView([evt.lat, evt.lon], 7);
  }
  // Render USGS detail card
  renderDetail(evt);
  // Render impact table
  impactEl._rollups = data.rollups;
  renderRollup(data.rollups, "district");
  // Peak intensity comes from the drawn bands, not the rollups: a footprint
  // outside the boundary dataset still has a real peak.
  const peak = (data.bands.features || [])
    .reduce((m, f) => Math.max(m, (f.properties || {}).mmi_lower || 0), 0);
  impactEl._peakMmi = peak;
  updateStatusBar(evt, peak);
  renderExposureStrip(data.rollups, document.getElementById("xs-level").value, peak);
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
      <button class="btn-edit" data-edit-id="${evt.id}">${svgIcon("edit")} Edit</button>
      <button class="btn-del-detail" data-del-id="${evt.id}">${svgIcon("trash")} Delete event</button>
    </div>`;
    el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
    el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
    return;
  }
  if (evt.source !== "USGS") {
    // Non-USGS feed event (e.g. PMD) — no USGS detail products.
    el.innerHTML = `<div class="evt-detail">
      <div class="detail-info">${escapeHtml(evt.source)} event${evt.place ? " — " + escapeHtml(evt.place) : ""}. No USGS detail available.</div>
      <button class="btn-edit" data-edit-id="${evt.id}">${svgIcon("edit")} Edit</button>
      <button class="btn-del-detail" data-del-id="${evt.id}">${svgIcon("trash")} Delete event</button>
    </div>`;
    el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
    el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
    return;
  }
  if (!props) {
    // Have source_event_id but no cached detail
    el.innerHTML = `<div class="evt-detail">
      <div class="detail-info">No USGS detail cached.</div>
      <button class="btn-refresh" style="margin-bottom:4px">${svgIcon("refresh")} Refresh from USGS</button>
      <button class="btn-edit" data-edit-id="${evt.id}">${svgIcon("edit")} Edit</button>
      <button class="btn-del-detail" data-del-id="${evt.id}">${svgIcon("trash")} Delete event</button>
    </div>`;
    el.querySelector(".btn-refresh").addEventListener("click", () => refreshFromUsgs(evt.id));
    el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
    el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
    return;
  }
  const prods = props.products || {};
  const badges = [];
  if (prods.shakemap?.length) badges.push(svgIcon("building", 12) + " ShakeMap");
  if (prods["moment-tensor"]?.length) badges.push(svgIcon("target", 12) + " Moment Tensor");
  if (prods.dyfi?.length) badges.push(svgIcon("chart", 12) + " DYFI");
  if (prods["focal-mechanism"]?.length) badges.push(svgIcon("settings", 12) + " Focal Mechanism");
  const alertBadge = props.alert
    ? `<span class="evt-alert ${props.alert}">${props.alert.toUpperCase()}</span>` : "";
  el.innerHTML = `<div class="evt-detail">
    <div class="detail-head">
      <span class="detail-title">USGS Detail</span>
      ${alertBadge}
      ${props.tsunami ? `<span class="evt-tsunami" title="Tsunami warning">${svgIcon("waves", 14)}</span>` : ""}
    </div>
    <div class="detail-info">
      ${props.place ? `<div>${svgIcon("pin", 12)} ${escapeHtml(props.place)}</div>` : ""}
      <div>M${props.mag} ${props.magType || ""} · depth ${props.depth} km</div>
      <div>${props.felt ? `${svgIcon("user", 12)} ${props.felt} felt · ` : ""}${props.sig ? `${svgIcon("zap", 12)} sig ${props.sig}` : ""}</div>
      ${badges.length ? `<div class="detail-prods">${badges.join(" · ")}</div>` : ""}
      ${props.url ? `<a href="${escapeHtml(props.url)}" target="_blank" class="detail-link">View on USGS ↗</a>` : ""}
    </div>
    <button class="btn-refresh" style="margin-bottom:4px">${svgIcon("refresh")} Refresh from USGS</button>
    <button class="btn-edit" data-edit-id="${evt.id}">${svgIcon("edit")} Edit</button>
    <button class="btn-del-detail" data-del-id="${evt.id}">${svgIcon("trash")} Delete event</button>
  </div>`;
  el.querySelector(".btn-refresh").addEventListener("click", () => refreshFromUsgs(evt.id));
  el.querySelector(".btn-edit").addEventListener("click", () => showEditForm(evt));
  el.querySelector(".btn-del-detail").addEventListener("click", () => confirmDelete(evt.id));
}

async function refreshFromUsgs(eventId) {
  const btn = document.querySelector(".btn-refresh");
  if (btn) { btn.disabled = true; btn.innerHTML = svgIcon("refresh") + " Refreshing…"; }
  try {
    const r = await fetchAdmin(`/events/${eventId}/refresh-from-usgs`, { method: "POST" });
    if (r.ok) {
      const evt = await r.json();
      renderDetail(evt);
      toast("USGS detail refreshed", "success");
    } else {
      if (btn) { btn.disabled = false; btn.innerHTML = svgIcon("refresh") + " Refresh from USGS"; }
      toast("USGS refresh failed (HTTP " + r.status + ")", "error");
    }
  } catch (e) {
    if (btn) { btn.disabled = false; btn.innerHTML = svgIcon("refresh") + " Refresh from USGS"; }
    toast("USGS refresh failed: " + e.message, "error");
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
      <button id="edit-save" class="btn-refresh" style="margin:0">${svgIcon("save")} Save</button>
      <button id="edit-cancel" class="btn-edit" style="margin:0">Cancel</button>
    </div>
    <button class="btn-del-detail" data-del-id="${evt.id}">${svgIcon("trash")} Delete event</button>
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
      const r = await fetchAdmin(`/events/${evt.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        const updated = await r.json();
        renderDetail(updated);
        refreshEvents();
        toast("Event updated", "success");
      } else {
        toast("Update failed (HTTP " + r.status + ")", "error");
      }
    } catch (e) { toast("Update failed: " + e.message, "error"); }
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

// ---- Status bar: the alert takeover -------------------------------------
// The whole console adopts the active event's PAGER alert level: --alert
// drives --brand, the room frame, and every accent derived from it. Events
// without a PAGER alert (manual entries, most PMD rows) read as "none", which
// resolves to a steel blue matching no PAGER level.
const _ALERT_TEXT = {
  green: "Green alert", yellow: "Yellow alert",
  orange: "Orange alert", red: "Red alert",
};

function setAlertLevel(level, label) {
  const lv = _ALERT_TEXT[level] ? level : "none";
  document.documentElement.dataset.alert = lv;
  const el = document.getElementById("alert-chip-text");
  if (el) el.textContent = lv === "none" ? (label || "No PAGER alert") : _ALERT_TEXT[lv];
  document.querySelectorAll("[data-alert-preview]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.alertPreview === lv ? "true" : "false");
  });
}

document.querySelectorAll("[data-alert-preview]").forEach((button) => {
  button.addEventListener("click", () => setAlertLevel(button.dataset.alertPreview));
});

// A running clock only means something while a response is live. Past 72 hours
// the elapsed count is noise, so the bar shows the origin date instead.
const _ELAPSED_MAX_S = 72 * 3600;
let _elapsedTimer = null;

function startElapsed(occurredAt) {
  const out = document.getElementById("sb-elapsed");
  const lbl = document.getElementById("sb-elapsed-label");
  if (!out) return;
  if (_elapsedTimer) { clearInterval(_elapsedTimer); _elapsedTimer = null; }
  const t0 = occurredAt ? new Date(occurredAt).getTime() : NaN;
  if (!Number.isFinite(t0)) {
    out.textContent = "—";
    if (lbl) lbl.textContent = "ELAPSED";
    return;
  }
  if ((Date.now() - t0) / 1000 > _ELAPSED_MAX_S) {
    if (lbl) lbl.textContent = "ORIGIN";
    out.textContent = new Date(t0).toLocaleDateString(undefined,
      { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
    return;
  }
  if (lbl) lbl.textContent = "ELAPSED";
  const tick = () => {
    const s = Math.max(0, Math.floor((Date.now() - t0) / 1000));
    const p = n => String(n).padStart(2, "0");
    out.textContent = `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
  };
  tick();
  _elapsedTimer = setInterval(tick, 1000);
}

// Reflect an event in the status bar. Called whenever an event becomes active.
function updateStatusBar(evt, peakMmi) {
  const id = document.getElementById("sb-event");
  const peak = document.getElementById("sb-peak");
  if (!evt) {
    setAlertLevel(null, "No active event");
    if (id) id.textContent = "—";
    if (peak) peak.textContent = "—";
    startElapsed(null);
    return;
  }
  setAlertLevel(evt.alert);
  if (id) {
    const mag = Number(evt.magnitude);
    id.textContent = `${Number.isFinite(mag) ? "M" + mag.toFixed(1) : "M?"} ${evt.source || ""}`.trim();
    id.title = evt.place || "";
  }
  if (peak) peak.textContent = peakMmi ? `MMI ${(MMI_CLASSES[peakMmi] || [peakMmi])[0]}` : "—";
  startElapsed(evt.occurred_at);
}

// Start with the room at rest: no alert frame, no event in the status bar.
updateStatusBar(null);

(function startClock() {
  const el = document.getElementById("sb-clock");
  if (!el) return;
  const tick = () => {
    el.textContent = new Date().toLocaleString(undefined, {
      hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short",
    }).toUpperCase();
  };
  tick();
  setInterval(tick, 30000);
})();

// ---- Exposure strip ------------------------------------------------------
// Administrative units by the peak intensity that reaches them. Segment width
// is that band's share of affected units, so the shape of the emergency reads
// without parsing numbers. Population and building counts are not available
// from the impact API, so units are what this reports.
function hideExposureStrip() {
  const strip = document.getElementById("exposure-strip");
  if (!strip) return;
  strip.hidden = true;
  document.body.classList.remove("has-strip");
}

function renderExposureStrip(rollups, level, peakBand) {
  const strip = document.getElementById("exposure-strip");
  if (!strip || !rollups) return;
  const rows = (rollups[level] || []).filter(d => d.mmi_max > 0);
  const bandsEl = document.getElementById("xs-bands");
  const noun = level === "province" ? "Provinces" : level === "tehsil" ? "Tehsils" : "Districts";

  strip.hidden = false;
  document.body.classList.add("has-strip");
  if (map) setTimeout(() => map.invalidateSize(), 60);

  const byBand = new Map();
  rows.forEach(d => byBand.set(d.mmi_max, (byBand.get(d.mmi_max) || 0) + 1));
  const strong = rows.filter(d => d.mmi_max >= 6).length;
  const peak = peakBand || rows.reduce((m, d) => Math.max(m, d.mmi_max), 0);
  const colorOf = Object.fromEntries(MMI_PALETTE);

  document.getElementById("xs-lead-label").textContent = `${noun} at MMI VI and above`;
  document.getElementById("xs-lead-val").textContent = strong.toLocaleString();
  document.getElementById("xs-lead-sub").textContent =
    `of ${rows.length.toLocaleString()} ${noun.toLowerCase()} in the footprint`;
  document.getElementById("xs-peak-val").textContent =
    peak ? (MMI_CLASSES[peak] || [String(peak)])[0] : "—";
  document.getElementById("xs-total-val").textContent = rows.length.toLocaleString();

  if (!byBand.size) {
    // Distinguish "nothing shakes" from "the footprint is off the map we hold
    // boundaries for" — both return no rows, but they mean different things.
    bandsEl.innerHTML = `<div class="xs-empty">${peak
      ? "Shaking reaches MMI " + (MMI_CLASSES[peak] || [peak])[0] +
        ", but the footprint falls outside the district boundary dataset."
      : "No administrative unit reaches MMI 2."}</div>`;
    return;
  }
  bandsEl.innerHTML = [...byBand.entries()].sort((a, b) => a[0] - b[0]).map(([m, n]) => {
    const [roman, name] = MMI_CLASSES[m] || [String(m), ""];
    return `<button type="button" class="xs-band" data-level="${m}" style="flex:${n}"` +
      ` title="MMI ${roman} — ${name}: ${n} ${noun.toLowerCase()}">` +
      `<i style="background:${colorOf[m] || "#888"}"></i>` +
      `<span class="xs-lab"><u>${roman}</u><span>${n}</span></span></button>`;
  }).join("");

  // Hovering a segment highlights the same band's polygons on the map.
  bandsEl.querySelectorAll(".xs-band").forEach(el => {
    const lv = parseInt(el.dataset.level);
    el.addEventListener("mouseenter", () => highlightByLevel(lv));
    el.addEventListener("mouseleave", () => unhighlightAll());
    el.addEventListener("click", () => selectMmiLevel(lv));
  });
}

document.getElementById("xs-level").addEventListener("change", (e) => {
  if (impactEl._rollups) {
    renderExposureStrip(impactEl._rollups, e.target.value, impactEl._peakMmi);
  }
});

// Fetch per-source counts for catalog tabs.
function updateTabCounts() {
  const params = new URLSearchParams();
  const minmag = document.getElementById("filter-minmag").value;
  const maxmag = document.getElementById("filter-maxmag").value;
  const search = document.getElementById("filter-search").value;
  const after = document.getElementById("filter-after").value;
  const before = document.getElementById("filter-before").value;
  if (minmag) params.set("min_magnitude", minmag);
  if (maxmag) params.set("max_magnitude", maxmag);
  if (search) params.set("search", search);
  if (after) params.set("occurred_after", after);
  if (before) params.set("occurred_before", before);
  const q = params.toString();
  Promise.all([
    fetch("/events?limit=1&" + q).then(r => r.json()).then(d => d.total).catch(() => null),
    fetch("/events?limit=1&source=USGS&" + q).then(r => r.json()).then(d => d.total).catch(() => null),
    fetch("/events?limit=1&source=PMD&" + q).then(r => r.json()).then(d => d.total).catch(() => null),
  ]).then(([all, usgs, pmd]) => {
    document.querySelectorAll(".cat-tab").forEach(t => {
      const src = t.dataset.src;
      const c = src === "USGS" ? usgs : src === "PMD" ? pmd : all;
      const label = t.childNodes[0]; // text node before <span class="tab-count">
      if (c != null) {
        if (!t.querySelector(".tab-count")) t.innerHTML = label.textContent + ` <span class="tab-count">(${c})</span>`;
        else t.querySelector(".tab-count").textContent = `(${c})`;
      }
    });
  });
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
  const _cs = getComputedStyle(document.documentElement);
  const gridC = _cs.getPropertyValue("--border").trim() || "#eee";
  const axisC = _cs.getPropertyValue("--text-muted").trim() || "#ccc";
  const ringC = _cs.getPropertyValue("--surface").trim() || "#fff";
  const pad = { top: 6, right: 6, bottom: 18, left: 30 };
  const pw = w - pad.left - pad.right, ph = h - pad.top - pad.bottom;
  const t0 = new Date(sorted[0].occurred_at).getTime(), t1 = new Date(sorted[sorted.length - 1].occurred_at).getTime(), ts = t1 - t0 || 1;
  const mm0 = Math.max(0, Math.min(...sorted.map(e => e.magnitude)) - 0.3), mm1 = Math.max(...sorted.map(e => e.magnitude)) + 0.3, ms = mm1 - mm0 || 1;
  const x = e => pad.left + ((new Date(e.occurred_at).getTime() - t0) / ts) * pw;
  const y = e => pad.top + ph - ((e.magnitude - mm0) / ms) * ph;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = gridC; ctx.lineWidth = 1; ctx.font = "12px sans-serif";
  for (let m = Math.ceil(mm0); m <= Math.floor(mm1); m++) {
    const yy = pad.top + ph - ((m - mm0) / ms) * ph;
    ctx.beginPath(); ctx.moveTo(pad.left, yy); ctx.lineTo(w - pad.right, yy); ctx.stroke();
    ctx.fillStyle = axisC; ctx.textAlign = "right"; ctx.fillText(m + ".0", pad.left - 4, yy + 3);
  }
  // Only the endpoints: the catalog's 20 newest events usually span hours, so
  // interior ticks repeat the same date and pile up on each other.
  ctx.fillStyle = axisC;
  const dateAt = e => new Date(e.occurred_at).toLocaleDateString();
  ctx.textAlign = "left";
  ctx.fillText(dateAt(sorted[0]), pad.left, h - 4);
  if (sorted.length > 1 && dateAt(sorted[0]) !== dateAt(sorted[sorted.length - 1])) {
    ctx.textAlign = "right";
    ctx.fillText(dateAt(sorted[sorted.length - 1]), w - pad.right, h - 4);
  }
  const AC = { green: "#2E9E5B", yellow: "#D8B22C", orange: "#DD5730", red: "#C42A2E" };
  sorted.forEach(e => {
    ctx.beginPath(); ctx.arc(x(e), y(e), 4, 0, Math.PI * 2);
    ctx.fillStyle = AC[e.alert] || "#666";
    ctx.fill(); ctx.strokeStyle = ringC; ctx.lineWidth = 1; ctx.stroke();
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
  _hideLegend();
  hideExposureStrip();
  // Two events, two ramps: steel against ember — no third hue enters the room.
  const BLUE =["#E4E1DA","#CBC7BD","#AFACA3","#94958F","#7A7D7B","#63696A","#4E5457","#3B4145","#2A2F33"];
  const ORANGE = ["#fff7ed","#fed7aa","#fdba74","#fb923c","#f97316","#ea580c","#c2410c","#9a3412","#7c2d12"];
  const mkStyle = p => f => {
    const i = Math.max(0, Math.min(8, (f.properties.mmi_lower || 2) - 2));
    const c = p[i];
    return { color: c, weight: 1, opacity: MMI_STYLE.opacity, fillColor: c, fillOpacity: MMI_STYLE.opacity };
  };
  const l1 = L.geoJSON(d1.bands, { style: mkStyle(BLUE), onEachFeature: (f, l) => l.bindPopup(`Event 1: MMI ${mmiClassLabel(f.properties.mmi_lower)}`) }).addTo(map);
  const l2 = L.geoJSON(d2.bands, { style: mkStyle(ORANGE), onEachFeature: (f, l) => l.bindPopup(`Event 2: MMI ${mmiClassLabel(f.properties.mmi_lower)}`) }).addTo(map);
  _compLayers = [l1, l2];
  if (ev1 && ev1.lat != null) _compLayers.push(makeEpicenterMarker(ev1.lat, ev1.lon, "#000000", `Event 1 — M${ev1.magnitude.toFixed(1)}`).addTo(map));
  if (ev2 && ev2.lat != null) _compLayers.push(makeEpicenterMarker(ev2.lat, ev2.lon, "#000000", `Event 2 — M${ev2.magnitude.toFixed(1)}`).addTo(map));
  const b = l1.getBounds().extend(l2.getBounds());
  if (b.isValid()) map.fitBounds(b);
  if (_cmpLegendCtrl) map.removeControl(_cmpLegendCtrl);
  _cmpLegendCtrl = L.control({ position: "bottomright" });
  _cmpLegendCtrl.onAdd = function() {
    const div = L.DomUtil.create("div", "legend");
    div.innerHTML = `<div class="legend-title">Comparison</div><div style="display:flex;align-items:center;gap:6px;font-size:16px;padding:2px 0"><span style="display:inline-block;width:20px;height:14px;border-radius:3px;background:#8A94A0"></span>Event 1${ev1 ? " M" + ev1.magnitude.toFixed(1) : ""}</div><div style="display:flex;align-items:center;gap:6px;font-size:16px;padding:2px 0"><span style="display:inline-block;width:20px;height:14px;border-radius:3px;background:#DD5730"></span>Event 2${ev2 ? " M" + ev2.magnitude.toFixed(1) : ""}</div>`;
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
document.getElementById("ingest").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = spinnerHTML() + " Pulling…";
  statusEl.innerHTML = spinnerHTML() + " Pulling USGS feed…";
  const minmag = document.getElementById("ingest-minmag").value;
  let url = "/events/ingest";
  if (minmag) url += "?min_magnitude=" + encodeURIComponent(minmag);
  try {
    const r = await fetchAdmin(url, { method: "POST" });
    const res = await r.json();
    if (!r.ok) throw new Error(ingestErrorMessage(r, res));
    statusEl.textContent = "";
    toast(`Ingested ${res.inserted} new event${res.inserted === 1 ? "" : "s"} of ${res.fetched} fetched`,
          res.inserted > 0 ? "success" : "info");
  } catch (err) {
    statusEl.textContent = "";
    toast("Ingest failed: " + err.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = orig;
  }
  refreshEvents();
});

// Pull the PMD feed — full catalog, no mag filter.
document.getElementById("ingest-pmd").addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = spinnerHTML() + " Pulling…";
  statusEl.innerHTML = spinnerHTML() + " Pulling PMD feed…";
  try {
    const r = await fetchAdmin("/events/ingest/pmd", { method: "POST" });
    const res = await r.json();
    if (!r.ok) throw new Error(ingestErrorMessage(r, res));
    statusEl.textContent = "";
    toast(`Ingested ${res.inserted} new event${res.inserted === 1 ? "" : "s"} of ${res.fetched} fetched`,
          res.inserted > 0 ? "success" : "info");
  } catch (err) {
    statusEl.textContent = "";
    toast("PMD ingest failed: " + err.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = orig;
  }
  updateIngestStatus();
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

// --- USGS/PMD earthquake map tab ---
let _mapEventsLayer = null;
let _mapEventsLoaded = false;

function _magRadius(mag) {
  // Quadratic scaling for area proportional to energy release (~10^(1.5*M))
  // Area scales with magnitude^3 roughly, so radius ~ magnitude^1.5
  const m = Math.max(0, mag || 0);
  return Math.max(3, Math.min(24, 2.5 + Math.pow(m, 1.5) * 1.1));
}

function _quakeMarker(event) {
  const mag = Math.max(0, event.magnitude || 0);
  const color = _magColor(mag);
  const radius = _magRadius(mag);
  const marker = L.circleMarker([event.lat, event.lon], {
    radius,
    color: "#fff",
    weight: 1.2,
    fillColor: color,
    fillOpacity: 0.85,
    opacity: 0.95,
    className: "quake-scatter-point",
  });
  marker.bindPopup(
    `<strong>M${Number(event.magnitude).toFixed(1)}</strong><br>` +
    `${escapeHtml(event.place || "Unknown location")}<br>` +
    `<span style="color:var(--text-muted)">${new Date(event.occurred_at).toLocaleString()}</span>`
  );
  return marker;
}

// Magnitude is ordered, so it reads as one ramp from quiet steel to hot ember
// rather than as unrelated hues.
function _magColor(mag) {
  if (mag >= 7.1) return "#A32226";   // deep ember
  if (mag >= 6.1) return "#DD5730";   // ember
  if (mag >= 5.1) return "#E08A34";   // light ember
  if (mag >= 4.1) return "#D8B22C";   // amber
  if (mag >= 3.1) return "#9AA4AF";   // steel
  return "#6E7B85";                   // deep steel (≤ 3.0)
}

async function loadMapEvents({ fit = true } = {}) {
  const status = document.getElementById("map-events-status");
  const btn = document.getElementById("map-events-refresh");
  const includeUSGS = document.getElementById("map-src-usgs")?.checked;
  const includePMD = document.getElementById("map-src-pmd")?.checked;
  const minmag = document.getElementById("map-minmag")?.value || "";
  const limit = Math.max(1, Math.min(1000, parseInt(document.getElementById("map-limit")?.value || "250", 10)));
  const sources = new Set([
    ...(includeUSGS ? ["USGS"] : []),
    ...(includePMD ? ["PMD"] : []),
  ]);

  if (btn) { btn.disabled = true; btn.innerHTML = spinnerHTML() + " Loading…"; }
  if (status) status.textContent = "Loading recent earthquakes…";

  try {
    let url = `/events?limit=${encodeURIComponent(limit)}&orderby=time`;
    if (minmag) url += `&min_magnitude=${encodeURIComponent(minmag)}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    const events = (data.events || data)
      .filter(e => sources.has(e.source) && e.lat != null && e.lon != null);

    if (_mapEventsLayer) map.removeLayer(_mapEventsLayer);
    _mapEventsLayer = L.layerGroup(events.map(_quakeMarker)).addTo(map);
    _mapEventsLoaded = true;
    if (status) status.textContent = events.length ? "Earthquakes shown on map" : "No matching USGS/PMD events found";

    if (fit && events.length) {
      const bounds = L.latLngBounds(events.map(e => [e.lat, e.lon]));
      if (bounds.isValid()) map.fitBounds(bounds.pad(0.15));
    }
  } catch (err) {
    if (status) status.textContent = "";
    toast("Could not load earthquake map: " + err.message, "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Show earthquakes"; }
  }
}

document.getElementById("map-events-refresh")?.addEventListener("click", () => loadMapEvents());
["map-src-usgs", "map-src-pmd"].forEach(id => {
  document.getElementById(id)?.addEventListener("change", () => loadMapEvents({ fit: false }));
});

// Catalog source tabs
document.querySelectorAll(".cat-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".cat-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    const src = tab.dataset.src;
    document.getElementById("filter-source").value = src;
    refreshEvents();
  });
});

// Keep tabs in sync when source dropdown changes directly
document.getElementById("filter-source").addEventListener("change", () => {
  const val = document.getElementById("filter-source").value;
  document.querySelectorAll(".cat-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.src === val);
  });
});

// Catalog filter auto-refresh on change
["filter-search", "filter-minmag", "filter-maxmag", "filter-sort", "filter-after", "filter-before"].forEach(id => {
  const el = document.getElementById(id);
  const ev = el.tagName === "SELECT" ? "change" : "input";
  el.addEventListener(ev, () => refreshEvents());
});

// --- Sidebar rail: section switching + collapse ---
const SECTIONS = { event: "sec-event", catalog: "sec-catalog", mapEvents: "sec-map-events", aftershock: "sec-aftershock", infra: "sec-infra", dashboard: "sec-dashboard", config: "sec-config" };
// Start as null (not "event") so the initial showSection("event") renders the
// section instead of matching the active-icon-toggle guard and collapsing.
let activeSection = null;
let sidebarCollapsed = false;

function setCollapsed(value) {
  sidebarCollapsed = value;
  document.getElementById("sidebar").classList.toggle("collapsed", value);
  const c = document.getElementById("rail-collapse");
  c.innerHTML = svgIcon(value ? "chevron-right" : "chevron-left", 18);
  c.setAttribute("aria-label", value ? "Expand panel" : "Collapse panel");
}

// (Re)render the rail icons, reflecting which section is active (for Lordicon coloring).
const RAIL_GLYPH = { event: "plus", catalog: "list", mapEvents: "pin", aftershock: "target", infra: "building", dashboard: "chart", config: "settings" };
function renderRailIcons() {
  document.querySelectorAll(".rail-ic").forEach((b) => {
    const section = b.dataset.section;
    const icon = b.dataset.icon || (section && RAIL_GLYPH[section]);
    if (icon) {
      const label = b.dataset.label;
      const iconHtml = section && LORD_ICONS[section] && LORD_ICONS[section].src
        ? railIconMarkup(section, icon, b.classList.contains("active"))
        : svgIcon(icon, 20);
      b.innerHTML = label
        ? `${iconHtml}<span class="rail-label">${escapeHtml(label)}</span>`
        : iconHtml;
    }
    if (!b.getAttribute("aria-label")) b.setAttribute("aria-label", b.title || section || icon);
  });
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
  renderRailIcons();
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
document.addEventListener("click", async (e) => {
  const opt = e.target.closest(".export-opt");
  if (!opt) return;
  e.stopPropagation();
  const fmt = opt.dataset.format;
  const filter = (eventsEl._filter || "").replace(/^\?limit=\d+/, "");
  document.getElementById("export-menu").classList.remove("open");
  try {
    const resp = await fetchAdmin("/events/export?format=" + fmt + filter);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(JSON.stringify(err.detail ?? err));
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fmt === "geojson" ? "events.geojson" : "events.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast("Exported catalog as " + fmt.toUpperCase(), "success");
  } catch (err) {
    toast("Export failed: " + err.message, "error");
  }
});

// --- Dashboard ---
let _dashCharts = [];

function destroyCharts() {
  _dashCharts.forEach(c => c.destroy());
  _dashCharts = [];
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

// Chart palette — mirrors the "Situation Room" tokens in styles.css.
// Steel and sand carry the interface; warm hues carry magnitude and hazard.
// No blues or purples: the console has no colour that isn't earned.
// Keys are kept for call-site compatibility.
const C_ = {
  blue: "#8A94A0",   // steel  — primary series
  orange: "#DD5730", // ember
  teal: "#6E7B85",   // deep steel
  red: "#C42A2E",
  purple: "#8C5A3C", // umber
  amber: "#D8B22C",
  green: "#2E9E5B",
  gray: "#5A6570",
};

const _analyticsState = { window: "1y", minMag: "mc", zoneId: null, bbox: null };

function _analyticsQuery() {
  const p = new URLSearchParams({ window: _analyticsState.window, min_mag: _analyticsState.minMag });
  if (_analyticsState.zoneId != null) p.set("zone_id", _analyticsState.zoneId);
  if (_analyticsState.bbox) p.set("bbox", _analyticsState.bbox.join(","));
  return p.toString();
}

function renderProvenance(p) {
  const sub = document.getElementById("dash-title-sub");
  const span = `${p.from.slice(0, 10)} → ${p.to.slice(0, 10)}`;
  if (sub) sub.textContent = `USGS + PMD · ${span} · ${p.n_used.toLocaleString()} events used`;
  const foot = document.getElementById("dash-provenance-foot");
  if (foot) {
    const types = Object.entries(p.mag_types).map(([k, v]) => `${k}:${v}`).join(" · ");
    foot.textContent = `${p.n_excluded.toLocaleString()} events below the magnitude floor excluded · magnitude types — ${types} `
      + `(reported magnitudes, no scale conversion) · declustered (Gardner–Knopoff)`;
  }
}
function renderKpis(k) {
  const grid = document.getElementById("dash-kpis");
  const box = (val, lbl) => `<div class="dash-stat-box"><div class="dash-stat-val">${val}</div><div class="dash-stat-lbl">${lbl}</div></div>`;
  const b = k.b != null ? `${k.b}±${k.b_sigma}` : "—";
  const largest = k.largest ? `M${k.largest.magnitude.toFixed(1)}` : "—";
  grid.innerHTML =
    box(b, k.b_n != null ? `b-value (N ${k.b_n})` : "b-value") +
    box(k.mc ?? "—", "Completeness Mc") +
    box(k.background_rate ?? "—", "Background rate /yr") +
    box(k.pct_aftershocks != null ? Math.round(k.pct_aftershocks * 100) + "%" : "—", "Aftershocks") +
    box(largest, "Largest event") +
    box(k.active_sequences ?? 0, "Active sequences");
}
function renderFmd(f) {
  if (!f.bins.length) return;
  mk("ch-fmd", {
    type: "bar",
    data: { labels: f.bins.map(m => m.toFixed(1)), datasets: [
      { label: "Cumulative (≥ M)", data: f.cumulative, type: "line", borderColor: C_.orange,
        backgroundColor: "rgba(221,87,48,0.08)", fill: true, tension: 0, pointRadius: 0, order: 1 },
      { label: "Incremental", data: f.incremental, backgroundColor: "rgba(138,148,160,0.32)",
        borderColor: C_.blue, borderWidth: 1, order: 2, borderRadius: 2 },
    ]},
    options: {
      plugins: {
        legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
        title: { display: true, text: `Gutenberg–Richter${f.mc != null ? " · Mc " + f.mc : ""}`, font: { size: 12, weight: "600" } },
      },
      scales: { y: { type: "logarithmic", title: { display: true, text: "Count", font: { size: 10 } } },
                x: { title: { display: true, text: "Magnitude", font: { size: 10 } }, ticks: { font: { size: 9 }, maxTicksLimit: 20 } } },
    },
  });
}
function renderDepth(d) {
  const r = d.regimes;
  mk("ch-depth", {
    type: "bar",
    data: { labels: ["Crustal <35", "Intermediate 35–70", "Deep >70"],
      datasets: [{ label: "Events", data: [r.crustal, r.intermediate, r.deep],
        backgroundColor: [C_.teal, C_.blue, C_.purple], borderRadius: 3 }] },
    options: { plugins: { legend: { display: false },
      title: { display: true, text: "Depth regime (km)", font: { size: 12, weight: "600" } } },
      scales: { x: { ticks: { font: { size: 9 } } }, y: { title: { display: true, text: "Events", font: { size: 10 } } } } },
  });
}
function renderRate(series) {
  mk("ch-rate", {
    type: "line",
    data: { labels: series.map(s => s.month), datasets: [
      { label: "Total", data: series.map(s => s.total), borderColor: C_.gray,
        backgroundColor: "rgba(90,101,112,0.18)", fill: true, tension: .2, pointRadius: 0 },
      { label: "Background (declustered)", data: series.map(s => s.background),
        borderColor: C_.blue, backgroundColor: "rgba(138,148,160,0.12)", fill: true, tension: .2, pointRadius: 0 },
    ]},
    options: { plugins: { legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
      title: { display: true, text: "Monthly seismicity rate — total vs background", font: { size: 12, weight: "600" } } },
      scales: { x: { ticks: { font: { size: 8 }, maxTicksLimit: 12 } },
        y: { title: { display: true, text: "Events / month", font: { size: 10 } } } } },
  });
}
let _hotspotMap = null, _zonesLayer = null;

async function renderHotspotMap(grid) {
  const host = document.getElementById("hotspot-map");
  if (!host) return;
  if (_hotspotMap) { _hotspotMap.remove(); _hotspotMap = null; }
  _hotspotMap = L.map(host, { attributionControl: false }).setView([30.4, 69.3], 4);
  const style = currentTheme() === "dark" ? "dark_all" : "light_all";
  L.tileLayer(`https://{s}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}{r}.png`,
    { subdomains: "abcd" }).addTo(_hotspotMap);

  const cell = 0.25; // GRID_CELL_DEG server-side
  const max = grid.reduce((m, c) => Math.max(m, c.count), 1);
  grid.forEach(c => {
    const t = c.count / max;
    L.rectangle([[c.lat_low, c.lon_low], [c.lat_low + cell, c.lon_low + cell]], {
      stroke: false, fillColor: "#D8B22C", fillOpacity: 0.15 + 0.6 * t,
    }).addTo(_hotspotMap)
      .bindPopup(`${c.count} events · max M${c.max_mag} · mean depth ${c.mean_depth} km`)
      .on("click", () => {
        _analyticsState.bbox = [c.lon_low, c.lat_low, c.lon_low + cell, c.lat_low + cell];
        _analyticsState.zoneId = null; renderDashboard();
      });
  });

  // tectonic-zone overlay (click → drill into zone)
  try {
    const fc = await (await fetch("/zones")).json();
    _zonesLayer = L.geoJSON(fc, {
      style: { color: "#8A94A0", weight: 1, fill: false },
      onEachFeature: (feat, lyr) => lyr.on("click", () => {
        _analyticsState.zoneId = feat.properties.zone_id;
        _analyticsState.bbox = null; renderDashboard();
      }),
    }).addTo(_hotspotMap);
  } catch (e) { /* zones optional */ }
}

function renderZoneTable(zones) {
  const host = document.getElementById("zone-table");
  if (!host) return;
  if (!zones || !zones.length) { host.innerHTML = `<div style="color:var(--text-muted);padding:8px">No zone data in this view.</div>`; return; }
  const rows = zones.map(z => `<tr data-zone="${z.zone_id}">
    <td>${escapeHtml(z.name)}</td><td align=right>${z.n}</td>
    <td align=right>${z.b != null ? z.b + "±" + z.sigma : "—"}</td>
    <td align=right>${z.mc ?? "—"}</td><td align=right>${z.median_depth}</td>
    <td align=right>M${z.max_mag.toFixed(1)}</td><td align=right>${Math.round(z.pct_aftershocks * 100)}%</td></tr>`).join("");
  host.innerHTML = `<table class="zone-table"><thead><tr>
    <th align=left>Zone</th><th>N</th><th>b±σ</th><th>Mc</th><th>med.z</th><th>maxM</th><th>aft%</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  host.querySelectorAll("tr[data-zone]").forEach(tr => tr.addEventListener("click", () => {
    _analyticsState.zoneId = parseInt(tr.dataset.zone); _analyticsState.bbox = null; renderDashboard();
  }));
}

async function renderDashboard() {
  const main = document.getElementById("dash-main");
  main.innerHTML = `<div style="padding:48px;text-align:center;color:var(--text-muted)">${spinnerHTML()} Loading analytics…</div>`;
  let resp;
  try { resp = await fetch("/analytics?" + _analyticsQuery()); }
  catch (e) { main.innerHTML = `<div style="padding:20px;color:var(--text-muted)">Network error: ${escapeHtml(e.message)}</div>`; return; }
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    main.innerHTML = `<div style="padding:20px;color:var(--text-muted)">Failed to load analytics (HTTP ${resp.status}: ${escapeHtml(t.slice(0, 160))})</div>`;
    return;
  }
  const data = await resp.json();
  destroyCharts();
  syncChartTheme();
  if (data.provenance.n_used === 0) {
    main.innerHTML = _dashScaffoldHTML();
    _wireFilterBar();
    renderProvenance(data.provenance);
    document.getElementById("dash-kpis").innerHTML =
      `<div style="padding:20px;color:var(--text-muted)">No events match this filter. Widen the time window or lower the minimum magnitude.</div>`;
    return;
  }
  main.innerHTML = _dashScaffoldHTML();
  _wireFilterBar();
  renderProvenance(data.provenance);
  renderKpis(data.kpis);
  renderFmd(data.fmd);
  renderDepth(data.depth);
  renderRate(data.rate);
  renderHotspotMap(data.grid);
  renderZoneTable(data.zones);
}

function _dashScaffoldHTML() {
  return `
  <div class="dash-filterbar">
    <label>Time <select id="f-window">
      <option value="30d">30 days</option><option value="1y" selected>1 year</option>
      <option value="5y">5 years</option><option value="all">All</option></select></label>
    <label>Min mag <select id="f-minmag">
      <option value="mc" selected>≥ Mc</option><option value="2">2.0</option>
      <option value="3">3.0</option><option value="4">4.0</option><option value="5">5.0</option></select></label>
    <span id="f-breadcrumb" class="dash-breadcrumb"></span>
    <button id="f-reset" class="btn-secondary" style="width:auto;margin:0">⟲ Reset</button>
  </div>
  <div id="dash-kpis" class="dash-stat-grid"></div>
  <div class="dash-row"><div class="dash-card auto" style="flex:1.4"><div id="hotspot-map" style="height:340px"></div></div>
    <div class="dash-card auto" style="flex:1"><div id="zone-table"></div></div></div>
  <div class="dash-row"><div class="dash-card" style="flex:1.3"><canvas id="ch-fmd"></canvas></div>
    <div class="dash-card" style="flex:1"><canvas id="ch-depth"></canvas></div></div>
  <div class="dash-row"><div class="dash-card"><canvas id="ch-rate"></canvas></div></div>
  <div class="dash-foot" id="dash-provenance-foot"></div>`;
}

function _wireFilterBar() {
  const win = document.getElementById("f-window");
  const mm = document.getElementById("f-minmag");
  win.value = _analyticsState.window; mm.value = _analyticsState.minMag;
  win.addEventListener("change", () => { _analyticsState.window = win.value; renderDashboard(); });
  mm.addEventListener("change", () => { _analyticsState.minMag = mm.value; renderDashboard(); });
  document.getElementById("f-reset").addEventListener("click", () => {
    _analyticsState.zoneId = null; _analyticsState.bbox = null; renderDashboard();
  });
  const bc = document.getElementById("f-breadcrumb");
  bc.textContent = _analyticsState.zoneId != null ? "▸ zone focus"
    : _analyticsState.bbox ? "▸ cell focus" : "";
}

document.querySelectorAll(".rail-ic[data-section]").forEach((b) =>
  b.addEventListener("click", () => showSection(b.dataset.section)));
document.getElementById("rail-collapse")
  .addEventListener("click", () => setCollapsed(!sidebarCollapsed));

// Rail is a vertical toolbar; arrow keys (and Home/End) move focus between buttons.
const railEl = document.querySelector("#sidebar .rail");
railEl.setAttribute("role", "toolbar");
railEl.setAttribute("aria-orientation", "vertical");
railEl.setAttribute("aria-label", "Panel sections");
railEl.addEventListener("keydown", (e) => {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  const btns = Array.from(railEl.querySelectorAll("button"));
  const i = btns.indexOf(document.activeElement);
  if (i < 0) return;
  e.preventDefault();
  let n;
  if (e.key === "Home") n = 0;
  else if (e.key === "End") n = btns.length - 1;
  else n = (i + (e.key === "ArrowDown" ? 1 : -1) + btns.length) % btns.length;
  btns[n].focus();
});

// --- Theme (light/dark) ---
// Tokens live in styles.css; JS only flips data-theme and re-paints the
// canvas-drawn views (Chart.js + timeline) that can't read CSS variables.
function currentTheme() { return document.documentElement.dataset.theme === "dark" ? "dark" : "light"; }

function syncChartTheme() {
  if (!window.Chart) return;
  const cs = getComputedStyle(document.documentElement);
  Chart.defaults.color = cs.getPropertyValue("--text-muted").trim();
  Chart.defaults.borderColor = cs.getPropertyValue("--border").trim();
  Chart.defaults.font.family = cs.getPropertyValue("--font-sans").trim() || "system-ui, sans-serif";
}

function applyTheme(mode) {
  document.documentElement.dataset.theme = mode;
  try { localStorage.setItem("eqmon-theme", mode); } catch (e) { /* private mode */ }
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.innerHTML = svgIcon(mode === "dark" ? "sun" : "moon", 18);
    btn.setAttribute("aria-label", mode === "dark" ? "Switch to light mode" : "Switch to dark mode");
  }
  syncChartTheme();
  syncBasemapToTheme(mode);
  // Re-paint canvas views that derive colors from the theme.
  if (activeSection === "dashboard" &&
      document.getElementById("dashboard-view").classList.contains("open")) renderDashboard();
  if (eventsEl._allEvents) drawTimeline(eventsEl._allEvents);
}

// Match the basemap to the theme (Dark Matter for dark, OSM for light) — but only
// until the user picks a basemap themselves, then we never override their choice.
function syncBasemapToTheme(mode) {
  if (_userPickedBasemap) return;
  const want = mode === "dark" ? "Dark (Dark Matter)" : "OpenStreetMap";
  setBasemap(want);
  if (_basemapRadios[want]) _basemapRadios[want].checked = true;
}

  document.getElementById("theme-toggle").addEventListener("click", () =>
  applyTheme(currentTheme() === "dark" ? "light" : "dark"));

(function initTheme() {
  let mode = null;
  try { mode = localStorage.getItem("eqmon-theme"); } catch (e) { /* ignore */ }
  if (!mode) mode = "dark";
  applyTheme(mode);
})();

// --- Aftershock probability section ---
let _asChart = null;
let _asExpandedChart = null;
let _asData = null;
const _AS_DAYS = [1, 3, 5, 7, 14, 30];
const _AS_TARGETS = [3, 4, 5, 6, 7];
// Target magnitudes are ordered, so the series read as a warm ramp.
const _AS_COLORS = ["#9AA4AF", "#D8B22C", "#E08A34", "#DD5730", "#A32226"];

function _asDestroyChart() {
  if (_asChart) { _asChart.destroy(); _asChart = null; }
}

function _asDestroyExpandedChart() {
  if (_asExpandedChart) { _asExpandedChart.destroy(); _asExpandedChart = null; }
}

async function _asLoadEvents() {
  const sel = document.getElementById("as-event-id");
  if (!sel) return;
  sel.innerHTML = '<option value="">Loading…</option>';
  try {
    const resp = await fetch("/events?min_magnitude=4&limit=50&orderby=time");
    const data = await resp.json();
    const events = data.events || [];
    sel.innerHTML = events.map(e =>
      `<option value="${e.id}" data-lat="${e.lat}" data-lon="${e.lon}" data-mag="${e.magnitude}">`
      + `M${e.magnitude.toFixed(1)} · ${e.place || "—"} · ${new Date(e.occurred_at).toLocaleDateString()}`
      + `</option>`
    ).join("");
    if (events.length) _asOnEventSelect();
  } catch (e) {
    sel.innerHTML = '<option value="">Could not load catalog</option>';
  }
}

function _asOnEventSelect() {
  const sel = document.getElementById("as-event-id");
  const opt = sel.options[sel.selectedIndex];
  if (opt && opt.value) {
    document.getElementById("as-mag").value = opt.dataset.mag;
    document.getElementById("as-lat").value = opt.dataset.lat;
    document.getElementById("as-lon").value = opt.dataset.lon;
  }
  _asDetectRegion();
}

function _asDetectRegion() {
  const lat = parseFloat(document.getElementById("as-lat").value);
  const lon = parseFloat(document.getElementById("as-lon").value);
  const badge = document.getElementById("as-region-badge");
  if (isNaN(lat) || isNaN(lon)) { badge.textContent = ""; return; }
  let region;
  if (lat >= 33.5) region = "northern";
  else if (lat >= 28) region = "central";
  else region = "southern";
  const names = {
    northern: "Northern Pakistan (Kashmir / Himalayan Thrust)",
    central: "Central Pakistan (Indus Basin / Punjab)",
    southern: "Southern Pakistan (Chaman Fault / Quetta)",
  };
  badge.innerHTML = `<span class="as-badge-inner as-${region}">${names[region]}</span>`
    + `<span style="font-size:14.5px;color:var(--text-muted);margin-left:6px">(${lat.toFixed(1)}°N, ${lon.toFixed(1)}°E)</span>`;
}

async function _asCalculate() {
  const calcBtn = document.getElementById("as-calc");
  const resultsEl = document.getElementById("as-results");
  calcBtn.disabled = true;
  calcBtn.innerHTML = spinnerHTML() + " Computing…";

  const source = document.getElementById("as-source").value;
  let body;
  if (source === "catalog") {
    const eventId = parseInt(document.getElementById("as-event-id").value);
    if (!eventId) { toast("Select an event from the catalog", "warn"); calcBtn.disabled = false; calcBtn.textContent = "Calculate aftershock probability"; return; }
    body = { event_id: eventId };
  } else {
    const mag = parseFloat(document.getElementById("as-mag").value);
    const lat = parseFloat(document.getElementById("as-lat").value);
    const lon = parseFloat(document.getElementById("as-lon").value);
    if (isNaN(mag) || isNaN(lat) || isNaN(lon)) { toast("Fill in magnitude, latitude, and longitude", "warn"); calcBtn.disabled = false; calcBtn.textContent = "Calculate aftershock probability"; return; }
    body = { magnitude: mag, lat, lon };
  }

  try {
    const resp = await fetch("/aftershock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.text().catch(() => "Unknown error");
      toast("Aftershock calculation failed: " + err.slice(0, 120), "error");
      calcBtn.disabled = false; calcBtn.textContent = "Calculate aftershock probability";
      return;
    }
    const data = await resp.json();
    _asRenderResults(data);
    resultsEl.style.display = "block";
  } catch (e) {
    toast("Network error: " + e.message, "error");
  }
  calcBtn.disabled = false;
  calcBtn.textContent = "Calculate aftershock probability";
}

function _asRenderResults(data) {
  _asData = data;
  const resultsEl = document.getElementById("as-results");
  if (!data.probabilities || data.probabilities.length === 0) {
    document.getElementById("as-summary").innerHTML =
      `<div class="as-summary-inner" style="color:var(--text-muted)">No supported target magnitudes: forecasts are only shown for M≥3 and below the current M${data.main_mag} event.</div>`;
    document.getElementById("as-chart-wrap").style.display = "none";
    document.getElementById("as-table-wrap").innerHTML = "";
    document.getElementById("as-export").style.display = "none";
    return;
  }
  document.getElementById("as-chart-wrap").style.display = "";
  document.getElementById("as-export").style.display = "";
  const _asMags = data.target_mags;
  const allTargets = _AS_TARGETS;
  const excluded = allTargets.filter(m => !_asMags.includes(m));
  const magsStr = _asMags.map(m => "M≥" + m).join(", ");
  const excludedStr = excluded.length
    ? `<span style="color:var(--text-muted);font-size:14.5px"> (${excluded.map(m => "M " + m).join(", ")} excluded: above mainshock)</span>`
    : "";
  const extrapolated = _asMags.filter(m => m < data.params.Mmin);
  const caveat = extrapolated.length
    ? `<div style="font-size:14.5px;color:var(--copper);margin-top:1px">M≥${extrapolated.join(", M≥")} is extrapolated below catalog completeness Mmin=${data.params.Mmin}.</div>`
    : "";
  const summaryEl = document.getElementById("as-summary");
  const ev = data.event;
  let eventStr = "";
  if (ev) {
    eventStr = `M${ev.magnitude} · ${ev.place || "—"} · ${ev.occurred_at ? new Date(ev.occurred_at).toLocaleDateString() : ""}`;
  } else {
    eventStr = `M${data.main_mag} (manual entry)`;
  }
  const zoneStr = data.zone_name ? ` · Zone: ${escapeHtml(data.zone_name)}` : "";

  summaryEl.innerHTML = `
    <div class="as-summary-inner">
      <strong>${eventStr}</strong>
      <span class="as-badge-inner as-${data.region}">${escapeHtml(data.region_name)}</span>${zoneStr}
      <div style="font-size:15px;color:var(--slate);margin-top:2px">
        ${magsStr}${excludedStr}
      </div>
      ${caveat}
      <div style="font-size:15px;color:var(--text-muted);margin-top:1px">
        k=${Number(data.params.k).toPrecision(3)} · c=${escapeHtml(data.params.c)} · p=${escapeHtml(data.params.p)} · b=${escapeHtml(data.params.b)} · Mmin=${escapeHtml(data.params.Mmin)}
      </div>
    </div>
  `;

  _asDestroyChart();
  const probsByMag = {};
  data.probabilities.forEach(r => {
    if (!probsByMag[r.Mtarget]) probsByMag[r.Mtarget] = [];
    probsByMag[r.Mtarget].push(r);
  });

  const chartWrap = document.getElementById("as-chart-wrap");
  const expandBtn = document.createElement("button");
  expandBtn.className = "as-expand-btn";
  expandBtn.innerHTML = svgIcon("maximize", 14) + " Expand";
  expandBtn.setAttribute("aria-label", "Expand chart to full screen");
  expandBtn.addEventListener("click", () => _asShowExpanded());
  chartWrap.prepend(expandBtn);

  const canvas = document.getElementById("as-chart");
  syncChartTheme();
  _asChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: _AS_DAYS,
      datasets: _asMags.map((mt, i) => ({
        label: `M ${mt}`,
        data: probsByMag[mt] ? probsByMag[mt].map(r => r.AftershockProb) : [],
        borderColor: _AS_COLORS[i],
        backgroundColor: _AS_COLORS[i] + "18",
        fill: true,
        tension: 0.3,
        borderWidth: 3,
        borderDash: [[], [8, 4], [4, 4], [2, 3], [6, 2]][i] || [],
        pointRadius: 4,
        pointHoverRadius: 7,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top", labels: { font: { size: 10 }, boxWidth: 14 } },
        title: { display: true, text: "Aftershock probability vs. days since mainshock", font: { size: 12, weight: "600" } },
      },
      scales: {
        y: {
          title: { display: true, text: "Probability (%)", font: { size: 10 } },
          min: 0, max: 100,
          ticks: { font: { size: 9 }, callback: v => v + "%" },
        },
        x: {
          title: { display: true, text: "Days since mainshock", font: { size: 10 } },
          ticks: { font: { size: 9 } },
        },
      },
    },
  });

  const tableWrap = document.getElementById("as-table-wrap");
  tableWrap.innerHTML = `
    <table class="as-table">
      <thead><tr><th>Days since</th>${_asMags.map(mt => `<th>M≥${mt}</th>`).join("")}</tr></thead>
      <tbody>${_AS_DAYS.map(d => {
        const row = data.probabilities.filter(r => r.DaysSince === d);
        return `<tr><td>${d}</td>${
          row.map(r => `<td>${r.AftershockProb > 99.9 ? ">99.9" : r.AftershockProb}%</td>`).join("")
        }</tr>`;
      }).join("")}</tbody>
    </table>
  `;

  document.getElementById("as-export").onclick = () => _asExportCsv(data);
}

function _asShowExpanded() {
  if (!_asData) return;
  const expandedView = document.getElementById("as-expanded-view");
  const mapEl = document.getElementById("map");
  mapEl.style.display = "none";
  expandedView.classList.add("open");

  const _asMags = _asData.target_mags;
  const ev = _asData.event;
  const summary = document.getElementById("as-expanded-summary");
  const eventStr = ev
    ? `M${ev.magnitude} · ${ev.place || "—"} · ${ev.occurred_at ? new Date(ev.occurred_at).toLocaleDateString() : ""}`
    : `M${_asData.main_mag} (manual entry)`;

  const allTargets = _AS_TARGETS;
  const excluded = allTargets.filter(m => !_asMags.includes(m));
  const magsStr = _asMags.map(m => "M≥" + m).join(", ");
  const excludedStr = excluded.length
    ? `<span style="color:var(--text-muted);font-size:14.5px"> (${excluded.map(m => "M " + m).join(", ")} excluded: above mainshock)</span>`
    : "";
  const extrapolated = _asMags.filter(m => m < _asData.params.Mmin);
  const caveat = extrapolated.length
    ? `<div style="font-size:14.5px;color:var(--copper);margin-top:1px">M≥${extrapolated.join(", M≥")} is extrapolated below catalog completeness Mmin=${_asData.params.Mmin}.</div>`
    : "";

  summary.innerHTML = `
    <div class="as-summary-inner" style="background:var(--surface);border:1px solid var(--border)">
      <strong>${escapeHtml(eventStr)}</strong>
      <span class="as-badge-inner as-${_asData.region}">${escapeHtml(_asData.region_name)}</span>
      <div style="font-size:15px;color:var(--slate);margin-top:2px">
        ${magsStr}${excludedStr}
      </div>
      ${caveat}
      <div style="font-size:15px;color:var(--text-muted);margin-top:1px">
        k=${Number(_asData.params.k).toPrecision(3)} · c=${_asData.params.c} · p=${_asData.params.p} · b=${_asData.params.b} · Mmin=${_asData.params.Mmin}
      </div>
    </div>
  `;

  _asDestroyExpandedChart();
  const probsByMag = {};
  _asData.probabilities.forEach(r => {
    if (!probsByMag[r.Mtarget]) probsByMag[r.Mtarget] = [];
    probsByMag[r.Mtarget].push(r);
  });

  syncChartTheme();
  const expandedCanvas = document.getElementById("as-expanded-chart");
  _asExpandedChart = new Chart(expandedCanvas, {
    type: "line",
    data: {
      labels: _AS_DAYS,
      datasets: _asMags.map((mt, i) => ({
        label: `M ${mt}`,
        data: probsByMag[mt] ? probsByMag[mt].map(r => r.AftershockProb) : [],
        borderColor: _AS_COLORS[i],
        backgroundColor: _AS_COLORS[i] + "15",
        fill: true,
        tension: 0.3,
        borderWidth: 3,
        borderDash: [[], [8, 4], [4, 4], [2, 3], [6, 2]][i] || [],
        pointRadius: 5,
        pointHoverRadius: 8,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top", labels: { font: { size: 13 }, boxWidth: 18 } },
        title: { display: true, text: "Aftershock probability vs. days since mainshock", font: { size: 16, weight: "600" } },
      },
      scales: {
        y: {
          title: { display: true, text: "Probability (%)", font: { size: 13 } },
          min: 0, max: 100,
          ticks: { font: { size: 12 }, callback: v => v + "%" },
        },
        x: {
          title: { display: true, text: "Days since mainshock", font: { size: 13 } },
          ticks: { font: { size: 12 } },
        },
      },
    },
  });

  const table = document.getElementById("as-expanded-table");
  table.innerHTML = `
    <table class="as-table">
      <thead><tr><th>Days since</th>${_asMags.map(mt => `<th>M≥${mt}</th>`).join("")}</tr></thead>
      <tbody>${_AS_DAYS.map(d => {
        const row = _asData.probabilities.filter(r => r.DaysSince === d);
        return `<tr><td>${d}</td>${
          row.map(r => `<td>${r.AftershockProb > 99.9 ? ">99.9" : r.AftershockProb}%</td>`).join("")
        }</tr>`;
      }).join("")}</tbody>
    </table>
  `;
}

function _asCloseExpanded() {
  const expandedView = document.getElementById("as-expanded-view");
  const mapEl = document.getElementById("map");
  expandedView.classList.remove("open");
  mapEl.style.display = "";
  _asDestroyExpandedChart();
  setTimeout(() => map.invalidateSize(), 100);
}

function _asExportCsv(data) {
  const header = "DaysSince,Mtarget,AftershockProb(%),OmoriRate";
  const rows = data.probabilities.map(r =>
    `${r.DaysSince},${r.Mtarget},${r.AftershockProb},${r.OmoriRate}`
  ).join("\n");
  const blob = new Blob([header + "\n" + rows], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const region = data.region || "pakistan";
  a.download = `aftershock_probs_${region}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
  toast("CSV downloaded", "success");
}

// Wire up aftershock UI events
document.addEventListener("DOMContentLoaded", () => {
  const srcSel = document.getElementById("as-source");
  const catRow = document.getElementById("as-catalog-row");
  const manRow = document.getElementById("as-manual-row");
  if (srcSel) {
    srcSel.addEventListener("change", () => {
      const isCat = srcSel.value === "catalog";
      catRow.style.display = isCat ? "" : "none";
      manRow.style.display = isCat ? "none" : "";
      if (isCat) _asOnEventSelect();
    });
  }
  const eventSel = document.getElementById("as-event-id");
  if (eventSel) eventSel.addEventListener("change", _asOnEventSelect);

  ["as-mag", "as-lat", "as-lon"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", _asDetectRegion);
  });

  const calcBtn = document.getElementById("as-calc");
  if (calcBtn) calcBtn.addEventListener("click", _asCalculate);

  const closeBtn = document.getElementById("as-expanded-close");
  if (closeBtn) closeBtn.addEventListener("click", _asCloseExpanded);
});

// Load catalog events when aftershock section is shown
const _origShowSection = showSection;
showSection = function(key) {
  // Close first: _arcClose restores the map, and showSection itself decides
  // whether the map should be visible for the section being opened.
  if (document.getElementById("arc-view").classList.contains("open")) _arcClose();
  _origShowSection(key);
  if (key !== "mapEvents" && _mapEventsLayer) {
    map.removeLayer(_mapEventsLayer);
    _mapEventsLayer = null;
  }
  if (key === "mapEvents" && (!_mapEventsLoaded || !_mapEventsLayer)) loadMapEvents();
  if (key === "aftershock") _asLoadEvents();
};

// --- Elements at risk (ARC) ---------------------------------------------
// The exposure strip answers "how many districts shake". This answers "what is
// inside the shaking" — people and infrastructure, from the ARC service.

// Order is the reading order, not ARC's. Population leads because it is the
// number the room asks for first.
const ARC_LAYERS = [
  ["population",  "People",      "total"],
  ["hospitals",   "Hospitals",   "count"],
  ["schools",     "Schools",     "count"],
  ["settlements", "Settlements", "count"],
  ["roads",       "Roads",       "count"],
  ["bridges",     "Bridges",     "count"],
  ["airports",    "Airports",    "count"],
];

let _arcData = null;

// Compact for the tiles; the exact figure sits underneath. Six-figure counts
// read as noise at a glance, which is what the tiles are for.
function _arcCompact(n) {
  if (!isFinite(n)) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 1 : 2) + "M";
  if (n >= 1e4) return Math.round(n / 1e3) + "k";
  return Math.round(n).toLocaleString();
}
const _arcExact = n => Math.round(n || 0).toLocaleString();

function _arcValue(elements, layer, field) {
  const v = (elements || {})[layer];
  return v ? (v[field] ?? 0) : 0;
}

function _arcOpen() {
  document.getElementById("map").style.display = "none";
  document.getElementById("arc-view").classList.add("open");
}

function _arcClose() {
  document.getElementById("arc-view").classList.remove("open");
  document.getElementById("map").style.display = "";
  setTimeout(() => map.invalidateSize(), 100);
}

function _arcRender(data) {
  const min = data.min_mmi;
  const head = data.at_min_mmi || { elements: {}, area_km2: 0 };
  const roman = (MMI_CLASSES[min] || [String(min)])[0];
  const empty = !Object.keys(head.elements || {}).length;

  document.getElementById("arc-summary").innerHTML =
    `<div class="arc-lead">At MMI ${roman} and above` +
    (head.area_km2 ? ` · ${_arcExact(head.area_km2)} km²` : "") + `</div>` +
    (empty
      ? `<div class="arc-tile"><span class="arc-k">No exposure</span>` +
        `<b>—</b><span class="arc-exact">Shaking does not reach MMI ${roman}.</span></div>`
      : `<div class="arc-tiles">` + ARC_LAYERS.map(([layer, label, field]) => {
          const v = _arcValue(head.elements, layer, field);
          const compact = _arcCompact(v), exact = _arcExact(v);
          return `<div class="arc-tile"><span class="arc-k">${escapeHtml(label)}</span>` +
            `<b>${compact}</b>` +
            // Only when abbreviating actually lost something — "216 / 216"
            // is noise.
            (compact === exact ? "" : `<span class="arc-exact">${exact}</span>`) +
            `</div>`;
        }).join("") + `</div>`);

  const colorOf = Object.fromEntries(MMI_PALETTE);
  const rows = (data.bands || []).map(b => {
    const lo = b.mmi_low;
    const [rm, name] = MMI_CLASSES[lo] || [String(lo), ""];
    return `<tr class="${lo >= min ? "" : "arc-below"}">` +
      `<td><span class="arc-band-key"><i style="background:${colorOf[lo] || "#888"}"></i>` +
      `MMI ${rm}${name ? " · " + name : ""}</span></td>` +
      `<td>${_arcExact(b.area_km2)}</td>` +
      ARC_LAYERS.map(([layer, , field]) =>
        `<td>${_arcExact(_arcValue(b.elements, layer, field))}</td>`).join("") +
      `</tr>`;
  }).join("");

  document.getElementById("arc-table").innerHTML =
    `<div class="arc-table-wrap"><table class="arc-table">` +
    `<thead><tr><th>Band</th><th>Area km²</th>` +
    ARC_LAYERS.map(([, label]) => `<th>${escapeHtml(label)}</th>`).join("") +
    `</tr></thead><tbody>${rows}</tbody></table></div>`;

  // The footprint runs down to MMI 2, which for a large event is most of the
  // country. Show that total, but say plainly why it is not the headline.
  const wholePop = _arcValue(data.totals, "population", "total");
  document.getElementById("arc-foot").innerHTML =
    `<p>Each element is counted once, in the strongest band it falls in, so bands ` +
    `never double-count and they sum to the whole-footprint total.</p>` +
    `<p>Across the whole footprint (down to MMI II): ` +
    `<b>${_arcExact(wholePop)}</b> people. That reaches far beyond damaging ` +
    `shaking, which is why the figures above are cut at MMI ${roman}.</p>`;
}

async function _arcRun() {
  const btn = document.getElementById("ladder-arc");
  if (!btn || !_lastFc || !(_lastFc.features || []).length) return;
  const label = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = spinnerHTML() + " Counting…";
  try {
    const resp = await fetch("/exposure/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bands: _lastFc }),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`);
    _arcData = body;
    _arcRender(body);
    _arcOpen();
  } catch (err) {
    // A full scan is slow and the service is external: say which one failed
    // rather than leaving an operator to guess the platform is broken.
    toast("Elements at risk unavailable: " + err.message, "error", 6000);
  } finally {
    btn.disabled = false;
    btn.innerHTML = label;
  }
}

document.getElementById("arc-close").addEventListener("click", _arcClose);

showSection("event"); // default panel on load
