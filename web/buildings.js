/* Infra Vulnerability layer — building footprints from the TileServerGL proxy.
 *
 * Upstream serves one vector dataset per district (161 of them), so this cannot
 * work like the overlays in app.js, which are a single pmtiles file each. The
 * job here is deciding which handful of those 161 sources should be live for
 * the current viewport, and tearing down the rest.
 *
 * Loads after app.js and reuses its globals: `map`, `L`, `protomapsL`.
 */
(function () {
  "use strict";

  const cfg = window.eqmonBuildingsConfig;
  const { BANDS, UNKNOWN, heightBand, visibleDistricts } = cfg;
  const PANE = "buildingsPane";

  /* ---- rendering ---- */

  // Same shape as NamedPolySymbolizer in app.js: draw(ctx, geom, z, feature).
  class HeightSymbolizer {
    constructor(opts) {
      this.alpha = opts.opacity ?? cfg.OPACITY;
      this.stroke = opts.stroke ?? "rgba(30,41,59,0.35)";
      this.width = opts.width ?? 0.4;
    }
    draw(ctx, geom, z, feature) {
      ctx.save();
      ctx.globalAlpha = this.alpha;
      ctx.fillStyle = heightBand(feature.props.height).color;
      ctx.strokeStyle = this.stroke;
      ctx.lineWidth = this.width;
      for (const poly of geom) {
        if (poly.length < 3) continue;
        ctx.beginPath();
        for (let p = 0; p < poly.length; p++) {
          const pt = poly[p];
          p === 0 ? ctx.moveTo(pt.x, pt.y) : ctx.lineTo(pt.x, pt.y);
        }
        ctx.closePath();
        ctx.fill();
        // Outlines only once buildings are big enough for them to read.
        if (z >= 15) ctx.stroke();
      }
      ctx.restore();
    }
  }

  /* ---- layer manager ---- */

  const state = {
    catalog: [],
    minZoom: 12,
    enabled: true,      // "load all data on map by default"
    selected: "",       // "" = all districts
    active: new Map(),  // datasetId -> protomaps leaflet layer
  };

  function ensurePane() {
    if (map.getPane(PANE)) return;
    map.createPane(PANE);
    // 350: above basemap tiles (200), below MMI polygons (400) and the
    // boundary overlays in referencePane (410) — buildings are context, they
    // must not bury the shaking footprint.
    map.getPane(PANE).style.zIndex = 350;
    map.getPane(PANE).style.pointerEvents = "none";
  }

  function makeLayer(id) {
    return protomapsL.leafletLayer({
      url: cfg.tileUrl(id),
      paintRules: [{
        dataLayer: "buildings",
        symbolizer: new HeightSymbolizer({ opacity: cfg.OPACITY }),
      }],
      backgroundColor: "rgba(0,0,0,0)",
      maxDataZoom: cfg.DATA_MAXZOOM,
      pane: PANE,
    });
  }

  function reconcile() {
    const want = state.enabled
      ? visibleDistricts(state.catalog, map.getBounds(), map.getZoom(),
                         state.minZoom, state.selected)
      : [];
    const wanted = new Set(want);

    for (const [id, layer] of state.active) {
      if (!wanted.has(id)) {
        map.removeLayer(layer);
        state.active.delete(id);
      }
    }
    for (const id of wanted) {
      if (!state.active.has(id)) {
        const layer = makeLayer(id);
        layer.addTo(map);
        state.active.set(id, layer);
      }
    }
    updateHint(want.length);
    publishBuildingState(want);
  }

  // Settings and the district catalog only — the live protomaps layers are this
  // renderer's business and never leave it. The 3D renderer re-runs the same
  // viewport decision against its own camera, which 2D cannot see.
  function publishBuildingState(districts) {
    publishMapState({
      buildings: {
        enabled: state.enabled,
        selected: state.selected,
        minZoom: state.minZoom,
        catalog: state.catalog,
        districts: [...(districts || state.active.keys())],
        opacity: cfg.OPACITY,
        maxSources: cfg.MAX_LIVE_SOURCES,
      },
    });
  }

  // Framing goes through the coordinator so the other renderer inherits the
  // move instead of being left behind at the previous district.
  function frameDistrict(center, zoom) {
    if (window.eqmonMapModes) {
      window.eqmonMapModes.setCamera({ center: [center.lng, center.lat], zoom });
    } else {
      map.setView(center, zoom);
    }
  }

  function setEnabled(enabled) {
    state.enabled = Boolean(enabled);
    if (els.toggle) {
      els.toggle.checked = state.enabled;
      els.controls.style.display = state.enabled ? "block" : "none";
    }
    reconcile();
  }

  /* ---- panel UI ---- */

  const els = {};

  function updateHint(activeCount) {
    if (!els.hint) return;
    if (!state.enabled || map.getZoom() < state.minZoom) {
      els.hint.textContent = "";
      return;
    }
    els.hint.textContent = activeCount
      ? `${activeCount} district${activeCount > 1 ? "s" : ""} rendering.`
      : "No building data in this view.";
  }

  function buildPanel() {
    const section = document.getElementById("sec-infra");
    if (!section) return;

    const group = document.createElement("div");
    group.className = "cfg-group";
    group.innerHTML = `
      <label class="cfg-row">
        <input id="bld-toggle" type="checkbox" checked />
        <span class="ov-name">Building height bands</span>
        <span id="bld-minzoom" class="bld-zoom-badge">Z${state.minZoom}+</span>
      </label>
      <div id="bld-controls">
        <span class="field-label">District</span>
        <select id="bld-district" class="as-select">
          <option value="">All districts</option>
        </select>
        <div class="bld-legend" id="bld-legend"></div>
        <div class="cfg-note" id="bld-hint"></div>
      </div>`;
    section.appendChild(group);

    els.toggle = group.querySelector("#bld-toggle");
    els.select = group.querySelector("#bld-district");
    els.controls = group.querySelector("#bld-controls");
    els.legend = group.querySelector("#bld-legend");
    els.hint = group.querySelector("#bld-hint");
    els.minZoom = group.querySelector("#bld-minzoom");

    const swatch = (c, label) =>
      `<div class="bld-legend-row"><span class="bld-swatch" style="background:${c}"></span>` +
      `<span>${label}</span></div>`;
    els.legend.innerHTML =
      BANDS.map(b => swatch(b.color, b.label)).join("") +
      swatch(UNKNOWN.color, UNKNOWN.label);

    els.toggle.addEventListener("change", () => setEnabled(els.toggle.checked));

    els.select.addEventListener("change", () => {
      state.selected = els.select.value;
      const d = state.catalog.find(x => x.id === state.selected);
      if (d) {
        // Jump to the district, otherwise selecting one off-screen looks broken.
        // Most districts only fit whole around z9-11, which is below MIN_ZOOM —
        // framing them exactly would answer the click with an empty map, so we
        // trade the full extent for a centre view that actually renders.
        const box = L.latLngBounds([d.bounds[1], d.bounds[0]], [d.bounds[3], d.bounds[2]]);
        if (map.getBoundsZoom(box) < state.minZoom) {
          frameDistrict(box.getCenter(), state.minZoom);
        } else {
          frameDistrict(box.getCenter(), map.getBoundsZoom(box));
        }
      }
      reconcile();
    });
  }

  function fillDistricts() {
    for (const d of state.catalog) {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = d.label;
      els.select.appendChild(opt);
    }
  }

  function disable(msg) {
    if (!els.toggle) return;
    els.toggle.checked = false;
    els.toggle.disabled = true;
    state.enabled = false;
    els.controls.style.display = "none";
    els.hint.textContent = msg;
    els.hint.style.display = "block";
  }

  async function init() {
    ensurePane();
    buildPanel();
    try {
      const resp = await fetch("/buildings/districts");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      state.catalog = data.districts || [];
      state.minZoom = data.min_zoom ?? 12;
      els.minZoom.textContent = `Z${state.minZoom}+`;
    } catch (err) {
      // Fail loudly in the panel: an empty map with a live-looking toggle is
      // worse than an honest "unavailable".
      console.error("buildings: catalog unavailable", err);
      disable("Building tile server unavailable.");
      return;
    }
    fillDistricts();
    map.on("moveend", reconcile);
    reconcile();
  }

  window.eqmonBuildings = {
    isEnabled: () => state.enabled,
    setEnabled,
    toggle: () => setEnabled(!state.enabled),
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
