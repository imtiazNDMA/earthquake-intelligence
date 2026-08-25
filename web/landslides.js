/* Lazy regional raster PMTiles layers for filtered Very High susceptibility. */
(function () {
  "use strict";

  const PANE = "landslidePane";
  const state = {
    opacity: 0.62,
    manifest: null,
    layers: new Map(),
    archives: new Map(),
    active: new Set(),
    els: {},
  };

  function ensurePane() {
    if (!map.getPane(PANE)) map.createPane(PANE);
    map.getPane(PANE).style.zIndex = 320;
    map.getPane(PANE).style.pointerEvents = "none";
  }

  function buildPanel() {
    const mount = document.getElementById("landslide-layer-list");
    if (!mount) return;
    mount.innerHTML = `
      <div class="landslide-controls-head"><span>Regional coverage</span><output id="landslide-active">0 active</output></div>
      <div id="landslide-region-list" class="landslide-region-list"></div>
      <div id="landslide-options" class="landslide-display-options" hidden>
        <label class="landslide-opacity-row" for="landslide-opacity">
          <span>Layer opacity</span>
          <input id="landslide-opacity" class="ov-opacity" type="range"
                 min="0" max="1" step="0.05" value="0.62" />
          <output id="landslide-opacity-value" for="landslide-opacity">62%</output>
        </label>
      </div>
      <div id="landslide-status" class="landslide-panel-status" aria-live="polite">
        Loading regional coverage...
      </div>`;
    state.els = {
      list: mount.querySelector("#landslide-region-list"),
      active: mount.querySelector("#landslide-active"),
      options: mount.querySelector("#landslide-options"),
      opacity: mount.querySelector("#landslide-opacity"),
      opacityValue: mount.querySelector("#landslide-opacity-value"),
      status: mount.querySelector("#landslide-status"),
    };
    state.els.opacity.addEventListener("input", () => {
      state.opacity = Number(state.els.opacity.value);
      state.els.opacityValue.textContent = `${Math.round(state.opacity * 100)}%`;
      state.layers.forEach(layer => layer.setOpacity(state.opacity));
    });
  }

  function renderRegionControls() {
    state.els.list.replaceChildren();
    state.manifest.regions.forEach(region => {
      const row = document.createElement("label");
      row.className = "landslide-region-row";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.region = region.key;
      input.setAttribute("aria-label", `Show ${region.label} landslide susceptibility`);
      const swatch = document.createElement("span");
      swatch.className = "landslide-swatch";
      swatch.setAttribute("aria-hidden", "true");
      const copy = document.createElement("span");
      copy.className = "landslide-region-copy";
      const name = document.createElement("strong");
      name.textContent = region.label;
      const detail = document.createElement("small");
      detail.textContent = `${state.manifest.class.label} susceptibility`;
      copy.append(name, detail);
      const status = document.createElement("b");
      status.className = "landslide-region-state";
      status.textContent = "Off";
      input.addEventListener("change", () => setRegion(region, input, status));
      row.append(input, swatch, copy, status);
      state.els.list.appendChild(row);
    });
  }

  function ensureLegend() {
    if (state.els.legend) return state.els.legend;
    const control = L.control({ position: "bottomleft" });
    control.onAdd = function () {
      const element = L.DomUtil.create("div", "landslide-map-legend");
      L.DomEvent.disableClickPropagation(element);
      L.DomEvent.disableScrollPropagation(element);
      return element;
    };
    control.addTo(map);
    state.els.legend = control.getContainer();
    return state.els.legend;
  }

  function renderLegend() {
    const legend = ensureLegend();
    if (!state.active.size || !state.manifest) {
      legend.hidden = true;
      return;
    }
    const labels = state.manifest.regions
      .filter(region => state.active.has(region.key))
      .map(region => region.label);
    legend.hidden = false;
    legend.innerHTML = `
      <div class="lsl-kicker">Landslide susceptibility</div>
      <div class="lsl-class"><i style="background:${state.manifest.class.color}"></i>
        <strong>${state.manifest.class.label}</strong></div>
      <div class="lsl-note">${labels.join(" / ")}</div>`;
  }

  function updatePanel(message) {
    state.els.active.textContent = `${state.active.size} active`;
    state.els.options.hidden = state.active.size === 0;
    if (message) state.els.status.textContent = message;
    renderLegend();
  }

  function ensureRegionLayer(region) {
    if (state.layers.has(region.key)) return state.layers.get(region.key);
    if (!window.pmtiles?.PMTiles || !window.pmtiles?.leafletRasterLayer) {
      throw new Error("PMTiles raster client did not load");
    }
    const archive = new window.pmtiles.PMTiles(region.url);
    const layer = window.pmtiles.leafletRasterLayer(archive, {
      pane: PANE,
      opacity: state.opacity,
      minZoom: region.min_zoom,
      maxNativeZoom: region.max_zoom,
      maxZoom: 18,
      attribution: "Landslide susceptibility source: supplied regional masks",
    });
    state.archives.set(region.key, archive);
    state.layers.set(region.key, layer);
    return layer;
  }

  async function setRegion(region, input, status) {
    input.disabled = true;
    if (!input.checked) {
      const layer = state.layers.get(region.key);
      if (layer) map.removeLayer(layer);
      state.active.delete(region.key);
      status.textContent = "Off";
      input.disabled = false;
      updatePanel(state.manifest.description);
      return;
    }

    status.textContent = "Loading";
    updatePanel(`Loading ${region.label} hazard tiles...`);
    try {
      ensureRegionLayer(region).addTo(map);
      state.active.add(region.key);
      status.textContent = "On";
      updatePanel(state.manifest.description);
    } catch (error) {
      console.warn(`Landslide susceptibility unavailable for ${region.key}`, error);
      input.checked = false;
      status.textContent = "Error";
      updatePanel(`${region.label} is unavailable. Rebuild it with scripts/build_landslide_tiles.py.`);
    } finally {
      input.disabled = false;
    }
  }

  async function loadManifest() {
    try {
      const response = await fetch("landslides/manifest.json");
      if (!response.ok) throw new Error(`manifest HTTP ${response.status}`);
      state.manifest = await response.json();
      if (!Array.isArray(state.manifest.regions) || !state.manifest.regions.length) {
        throw new Error("manifest has no regional layers");
      }
      state.opacity = state.manifest.default_opacity ?? state.opacity;
      state.els.opacity.value = String(state.opacity);
      state.els.opacityValue.textContent = `${Math.round(state.opacity * 100)}%`;
      renderRegionControls();
      state.els.status.textContent = state.manifest.description;
    } catch (error) {
      console.warn("Landslide susceptibility unavailable", error);
      state.els.list.innerHTML = '<div class="landslide-panel-loading">Regional layers unavailable.</div>';
      state.els.status.textContent = "Generate the display archives with scripts/build_landslide_tiles.py.";
    }
  }

  ensurePane();
  buildPanel();
  loadManifest();
})();
