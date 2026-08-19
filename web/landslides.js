/* Lazy regional raster PMTiles layer for filtered Very High susceptibility. */
(function () {
  "use strict";

  const PANE = "landslidePane";
  const state = {
    enabled: false,
    opacity: 0.62,
    manifest: null,
    group: null,
    archives: [],
    els: {},
  };

  function ensurePane() {
    if (!map.getPane(PANE)) map.createPane(PANE);
    map.getPane(PANE).style.zIndex = 320;
    map.getPane(PANE).style.pointerEvents = "none";
  }

  function buildPanel() {
    const section = document.getElementById("cfg-hazard-layers") || document.getElementById("sec-config");
    if (!section) return;
    const group = document.createElement("div");
    group.className = "cfg-group landslide-controls";
    group.innerHTML = `
      <div class="field-label">Landslide susceptibility</div>
      <label class="cfg-row">
        <input id="landslide-toggle" type="checkbox" />
        <span class="landslide-swatch" aria-hidden="true"></span>
        <span class="ov-name">Very High areas</span>
      </label>
      <div id="landslide-options" hidden>
        <label class="cfg-row"><span class="ov-name">Opacity</span>
          <span class="ov-controls">
            <input id="landslide-opacity" class="ov-opacity" type="range"
                   min="0" max="1" step="0.05" value="0.62" />
            <span id="landslide-opacity-value" class="cfg-value">62%</span>
          </span>
        </label>
      </div>
      <div id="landslide-status" class="cfg-note" aria-live="polite">
        Filtered Very High class only. Transparent areas may be unassessed.
      </div>`;
    section.appendChild(group);
    state.els = {
      toggle: group.querySelector("#landslide-toggle"),
      options: group.querySelector("#landslide-options"),
      opacity: group.querySelector("#landslide-opacity"),
      opacityValue: group.querySelector("#landslide-opacity-value"),
      status: group.querySelector("#landslide-status"),
    };
    state.els.toggle.addEventListener("change", toggle);
    state.els.toggle.addEventListener("change", () => window.updateConfigSummary?.());
    state.els.opacity.addEventListener("input", () => {
      state.opacity = Number(state.els.opacity.value);
      state.els.opacityValue.textContent = `${Math.round(state.opacity * 100)}%`;
      if (state.group) state.group.eachLayer(layer => layer.setOpacity(state.opacity));
    });
    window.updateConfigSummary?.();
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
    if (!state.enabled || !state.manifest) {
      legend.hidden = true;
      return;
    }
    legend.hidden = false;
    legend.innerHTML = `
      <div class="lsl-kicker">Landslide susceptibility</div>
      <div class="lsl-class"><i style="background:${state.manifest.class.color}"></i>
        <strong>${state.manifest.class.label}</strong></div>
      <div class="lsl-note">Filtered class only</div>`;
  }

  async function loadLayer() {
    if (state.group) return;
    if (!window.pmtiles?.PMTiles || !window.pmtiles?.leafletRasterLayer) {
      throw new Error("PMTiles raster client did not load");
    }
    const response = await fetch("landslides/manifest.json");
    if (!response.ok) throw new Error(`manifest HTTP ${response.status}`);
    state.manifest = await response.json();
    state.opacity = state.manifest.default_opacity ?? state.opacity;
    state.els.opacity.value = String(state.opacity);
    state.els.opacityValue.textContent = `${Math.round(state.opacity * 100)}%`;
    const layers = state.manifest.regions.map(region => {
      const archive = new window.pmtiles.PMTiles(region.url);
      state.archives.push(archive);
      return window.pmtiles.leafletRasterLayer(archive, {
        pane: PANE,
        opacity: state.opacity,
        minZoom: region.min_zoom,
        maxNativeZoom: region.max_zoom,
        maxZoom: 18,
        attribution: "Landslide susceptibility source: supplied regional masks",
      });
    });
    state.group = L.layerGroup(layers);
  }

  async function toggle() {
    state.enabled = state.els.toggle.checked;
    state.els.options.hidden = !state.enabled;
    if (!state.enabled) {
      if (state.group) map.removeLayer(state.group);
      renderLegend();
      return;
    }
    state.els.toggle.disabled = true;
    state.els.status.textContent = "Loading regional hazard tiles...";
    try {
      await loadLayer();
      if (state.enabled) state.group.addTo(map);
      state.els.status.textContent = state.manifest.description;
      renderLegend();
    } catch (error) {
      console.warn("Landslide susceptibility unavailable", error);
      state.enabled = false;
      state.els.toggle.checked = false;
      state.els.options.hidden = true;
      state.els.status.textContent = "Layer unavailable. Generate it with scripts/build_landslide_tiles.py.";
    } finally {
      state.els.toggle.disabled = false;
    }
  }

  ensurePane();
  buildPanel();
})();
