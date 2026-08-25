(function () {
  "use strict";

  const MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@5.7.1/dist/maplibre-gl.js";
  const MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@5.7.1/dist/maplibre-gl.css";
  const MAPLIBRE_JS_INTEGRITY = "sha384-gLKaKK6bcaV7wXNta/DHnECgiF2+mF15OXviE93B/+Q4CI68+ivYMRY4utfeUOTN";
  const MAPLIBRE_CSS_INTEGRITY = "sha384-gNYNsUmuZqDYiT3gbirWTV5K7rt71RoveS/yXAaU09d4ZUmeDVTD3XoqB6uJAIFR";
  let dependencyPromise = null;
  let mapInstance = null;
  let initializationPromise = null;
  let protocolRegistered = false;

  function loadStylesheet() {
    return new Promise((resolve, reject) => {
      const existing = document.getElementById("maplibre-gl-css");
      if (existing?.dataset.loaded === "true") {
        resolve();
        return;
      }
      if (existing) {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }
      const link = document.createElement("link");
      link.id = "maplibre-gl-css";
      link.rel = "stylesheet";
      link.href = MAPLIBRE_CSS;
      link.integrity = MAPLIBRE_CSS_INTEGRITY;
      link.crossOrigin = "anonymous";
      link.onload = () => {
        link.dataset.loaded = "true";
        resolve();
      };
      link.onerror = () => {
        link.remove();
        reject(new Error("MapLibre stylesheet failed to load"));
      };
      document.head.appendChild(link);
    });
  }

  function loadScript() {
    return new Promise((resolve, reject) => {
      if (window.maplibregl) {
        resolve();
        return;
      }
      const existing = document.getElementById("maplibre-gl-js");
      if (existing) {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }
      const script = document.createElement("script");
      script.id = "maplibre-gl-js";
      script.src = MAPLIBRE_JS;
      script.integrity = MAPLIBRE_JS_INTEGRITY;
      script.crossOrigin = "anonymous";
      script.onload = resolve;
      script.onerror = () => {
        script.remove();
        reject(new Error("MapLibre script failed to load"));
      };
      document.head.appendChild(script);
    });
  }

  async function loadDependencies() {
    if (!dependencyPromise) {
      dependencyPromise = Promise.all([loadStylesheet(), loadScript()]).catch(error => {
        dependencyPromise = null;
        throw error;
      });
    }
    await dependencyPromise;
    if (!window.maplibregl) throw new Error("MapLibre did not initialize");
  }

  function registerPmtilesProtocol() {
    if (protocolRegistered) return;
    if (!window.pmtiles?.Protocol) throw new Error("PMTiles protocol is unavailable");
    const protocol = new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);
    protocolRegistered = true;
  }

  function createMap() {
    return new Promise((resolve, reject) => {
      let settled = false;
      const timeout = window.setTimeout(() => fail(new Error("3D map initialization timed out")), 15000);

      function cleanListeners() {
        window.clearTimeout(timeout);
        mapInstance?.off("load", ready);
        mapInstance?.off("error", fail);
      }

      function ready() {
        if (settled) return;
        settled = true;
        cleanListeners();
        resolve(mapInstance);
      }

      function fail(event) {
        if (settled) return;
        if (event?.sourceId || event?.tile) return;
        settled = true;
        const error = event?.error || event || new Error("3D map initialization failed");
        cleanListeners();
        const failedMap = mapInstance;
        mapInstance = null;
        failedMap?.remove();
        reject(error);
      }

      mapInstance = new maplibregl.Map({
        container: "map-3d",
        center: [69.3, 30.4],
        zoom: 5,
        bearing: 0,
        pitch: 55,
        maxPitch: 70,
        attributionControl: true,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              maxzoom: 19,
              attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
            },
          },
          layers: [{ id: "osm", type: "raster", source: "osm" }],
        },
      });
      mapInstance.once("load", ready);
      mapInstance.on("error", fail);
    });
  }

  async function initializeMapLibre3d() {
    await loadDependencies();
    registerPmtilesProtocol();
    return createMap();
  }

  function ensureMapLibre3d() {
    if (initializationPromise) return initializationPromise;
    if (mapInstance) {
      mapInstance.resize();
      return Promise.resolve(mapInstance);
    }
    initializationPromise = initializeMapLibre3d().finally(() => {
      initializationPromise = null;
    });
    return initializationPromise;
  }

  window.eqmonMapLibre3d = {
    ensureMapLibre3d,
    hasInstance: () => Boolean(mapInstance),
    resize: () => mapInstance?.resize(),
  };
})();
