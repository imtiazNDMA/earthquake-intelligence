(function () {
  "use strict";

  const MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@5.7.1/dist/maplibre-gl.js";
  const MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@5.7.1/dist/maplibre-gl.css";
  const MAPLIBRE_JS_INTEGRITY = "sha384-gLKaKK6bcaV7wXNta/DHnECgiF2+mF15OXviE93B/+Q4CI68+ivYMRY4utfeUOTN";
  const MAPLIBRE_CSS_INTEGRITY = "sha384-gNYNsUmuZqDYiT3gbirWTV5K7rt71RoveS/yXAaU09d4ZUmeDVTD3XoqB6uJAIFR";
  const DEFAULT_CAMERA = { center: [69.3, 30.4], zoom: 4, bearing: 0, pitch: 55 };
  const BASEMAP_SOURCE = "basemap";
  const BASEMAP_LAYER = "basemap";
  const DEM_SOURCE = "terrain-dem";
  const HILLSHADE_LAYER = "terrain-hillshade";
  const MMI_SOURCE = "current-mmi";
  const MMI_FILL = "current-mmi-fill";
  const MMI_LINE = "current-mmi-line";
  const EVENTS_SOURCE = "map-events";
  const EVENTS_CIRCLE = "map-events-circle";
  const EMPTY_FC = { type: "FeatureCollection", features: [] };
  // Mirrors the 2D defaults in web/app.js; a publication overrides them.
  const MMI_BASE_OPACITY = 0.45;
  const MMI_BASE_WEIGHT = 1;
  const MMI_EMPHASIS = {
    selected: { weight: 3, fillOpacity: 0.8 },
    hovered: { weight: 2.5, fillOpacity: 0.7 },
  };
  let epicenterMarker = null;
  let dependencyPromise = null;
  let mapInstance = null;
  let initializationPromise = null;
  let protocolRegistered = false;
  let cameraListener = null;
  let currentBasemap = null;
  let terrainEnabled = false;
  let terrainAnnounced = false;

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

  function readCamera() {
    if (!mapInstance) return null;
    const center = mapInstance.getCenter();
    return {
      center: [center.lng, center.lat],
      zoom: mapInstance.getZoom(),
      bearing: mapInstance.getBearing(),
      pitch: mapInstance.getPitch(),
    };
  }

  // The coordinator owns the camera; this adapter only reports settled moves and
  // applies what it is given, in MapLibre's own zoom scale.
  function setCamera(camera) {
    if (!mapInstance || !camera) return;
    mapInstance.jumpTo({
      center: camera.center,
      zoom: camera.zoom,
      bearing: camera.bearing ?? 0,
      pitch: camera.pitch ?? 0,
    });
  }

  function onCameraChange(handler) {
    cameraListener = typeof handler === "function" ? handler : null;
  }

  function emitCameraChange() {
    const camera = readCamera();
    if (cameraListener && camera) cameraListener(camera);
  }

  function styleConfig() {
    return window.eqmonMapStyleConfig;
  }

  // A plain horizon gradient above the skyline. It gives the pitched view depth
  // without tinting the ground, so the MMI and hazard palettes keep the exact
  // contrast they are read at in 2D.
  const SKY = {
    light: { "sky-color": "#8fb3d9", "horizon-color": "#dfe8f2", "fog-color": "#e8eef5" },
    dark:  { "sky-color": "#0d141c", "horizon-color": "#26333f", "fog-color": "#161e26" },
  };

  function skyFor(theme) {
    return {
      ...(theme === "dark" ? SKY.dark : SKY.light),
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.6,
      // Barely any ground haze: distance cue only, never a wash over the data.
      "fog-ground-blend": 0.1,
    };
  }

  function initialBasemapName() {
    const config = styleConfig();
    // Start on whatever 2D is showing, falling back to the theme's basemap.
    const published = window.eqmonMapModes?.getState?.().basemap;
    return published || config.themeBasemap(document.documentElement.dataset.theme);
  }

  function buildStyle(basemapName) {
    const config = styleConfig();
    const terrain = config.TERRAIN;
    currentBasemap = basemapName;
    return {
      version: 8,
      sources: {
        [BASEMAP_SOURCE]: config.maplibreSource(basemapName),
        // The DEM feeds both the terrain mesh and the hillshade, so its credit
        // is attached once and MapLibre prints it once.
        [MMI_SOURCE]: { type: "geojson", data: EMPTY_FC },
        [EVENTS_SOURCE]: { type: "geojson", data: EMPTY_FC },
        [DEM_SOURCE]: {
          type: "raster-dem",
          tiles: terrain.tiles,
          encoding: terrain.encoding,
          tileSize: terrain.tileSize,
          maxzoom: terrain.maxzoom,
          attribution: terrain.attribution,
        },
      },
      layers: [
        { id: BASEMAP_LAYER, type: "raster", source: BASEMAP_SOURCE },
        // Shading only, at low strength: relief should read as depth cue, not
        // as another data layer competing with the hazard palette above it.
        {
          id: HILLSHADE_LAYER,
          type: "hillshade",
          source: DEM_SOURCE,
          paint: {
            "hillshade-exaggeration": 0.25,
            "hillshade-shadow-color": "#1c232b",
            "hillshade-highlight-color": "#ffffff",
          },
        },
        {
          id: MMI_FILL,
          type: "fill",
          source: MMI_SOURCE,
          // Severity ordering: a stronger band is drawn last and so is never
          // buried under the weaker band that surrounds it.
          layout: { "fill-sort-key": ["get", "mmi_lower"] },
          paint: { "fill-color": ["get", "color"], "fill-opacity": MMI_BASE_OPACITY },
        },
        {
          id: MMI_LINE,
          type: "line",
          source: MMI_SOURCE,
          // Band colour, exactly as in 2D. The MMI palette is theme-independent,
          // so the border reads the same against a light or a dark basemap.
          paint: {
            "line-color": ["get", "color"],
            "line-width": MMI_BASE_WEIGHT,
            "line-opacity": 0.9,
          },
        },
        {
          id: EVENTS_CIRCLE,
          type: "circle",
          source: EVENTS_SOURCE,
          // Radius and colour ride on the feature: they come from the same
          // magnitude and depth rules the 2D bubbles are drawn with.
          paint: {
            "circle-radius": ["get", "radius"],
            "circle-color": ["get", "color"],
            "circle-opacity": 0.85,
            "circle-stroke-width": ["get", "strokeWidth"],
            "circle-stroke-color": "#F4F6F8",
            "circle-stroke-opacity": 0.95,
          },
        },
      ],
      sky: skyFor(document.documentElement.dataset.theme),
    };
  }

  // Rebuilt rather than retiled: every basemap carries its own zoom ceiling and
  // credit, and a raster source can change neither in place. Only the bottom
  // layer is touched, so terrain, hillshade, and analysis layers above survive.
  function setBasemap(name) {
    const config = styleConfig();
    if (!mapInstance || !name || name === currentBasemap || !config) return;
    if (!mapInstance.getSource(BASEMAP_SOURCE)) return;
    const above = mapInstance.getStyle().layers[1]?.id;
    if (mapInstance.getLayer(BASEMAP_LAYER)) mapInstance.removeLayer(BASEMAP_LAYER);
    mapInstance.removeSource(BASEMAP_SOURCE);
    mapInstance.addSource(BASEMAP_SOURCE, config.maplibreSource(name));
    mapInstance.addLayer({ id: BASEMAP_LAYER, type: "raster", source: BASEMAP_SOURCE }, above);
    currentBasemap = name;
  }

  // Terrain is an enhancement, never a precondition: if the DEM does not arrive
  // the map stays pitched and usable, flat, and says so once.
  function enableTerrain() {
    const terrain = styleConfig().TERRAIN;
    return new Promise(resolve => {
      let settled = false;
      const finish = ok => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timer);
        resolve(ok);
      };
      const timer = window.setTimeout(() => {
        // Drop the mesh rather than leave a half-loaded one: pitched and flat is
        // a usable map, pitched over holes is not.
        dropTerrain();
        announceTerrainUnavailable();
        finish(false);
      }, terrain.timeoutMs);

      try {
        mapInstance.setTerrain({ source: DEM_SOURCE, exaggeration: terrain.exaggeration });
        terrainEnabled = true;
        // A DEM tile has to land before the mesh means anything; idle is the
        // first point at which we know it did.
        mapInstance.once("idle", () => finish(true));
      } catch (error) {
        console.warn("3D terrain unavailable", error);
        dropTerrain();
        announceTerrainUnavailable();
        finish(false);
      }
    });
  }

  function dropTerrain() {
    terrainEnabled = false;
    try { mapInstance?.setTerrain(null); } catch (error) { /* already gone */ }
  }

  function announceTerrainUnavailable() {
    if (terrainAnnounced) return;
    terrainAnnounced = true;
    if (typeof toast === "function") toast("Terrain unavailable; 3D view is flat.", "warn", 6000);
  }

  // Selected and hovered bands take the same emphasis the 2D ladder applies;
  // every other band keeps the published base value.
  function bandExpression(mmi, base, key, emphasis) {
    const parts = [];
    const selected = mmi?.selectedLevel;
    const hovered = mmi?.hoveredLevel;
    if (selected != null) parts.push(["==", ["get", "mmi_lower"], selected], emphasis.selected[key]);
    if (hovered != null && hovered !== selected) {
      parts.push(["==", ["get", "mmi_lower"], hovered], emphasis.hovered[key]);
    }
    return parts.length ? ["case", ...parts, base] : base;
  }

  function applyMmi(mmi) {
    const source = mapInstance.getSource(MMI_SOURCE);
    if (!source) return;
    // Hidden means no geometry, not a transparent layer: hit testing must not
    // find a band the operator cannot see.
    source.setData((mmi?.visible && mmi.featureCollection) || EMPTY_FC);
    const emphasis = mmi?.emphasis || MMI_EMPHASIS;
    const base = Number.isFinite(mmi?.opacity) ? mmi.opacity : MMI_BASE_OPACITY;
    mapInstance.setPaintProperty(MMI_FILL, "fill-opacity",
      bandExpression(mmi, base, "fillOpacity", emphasis));
    mapInstance.setPaintProperty(MMI_LINE, "line-width",
      bandExpression(mmi, MMI_BASE_WEIGHT, "weight", emphasis));
  }

  function applyMapEvents(mapEvents) {
    const source = mapInstance.getSource(EVENTS_SOURCE);
    if (!source) return;
    const events = mapEvents?.events || [];
    source.setData({
      type: "FeatureCollection",
      features: events.reduce((features, event) => {
        // Number(null) is 0, which would place a coordinate-less event off the
        // coast of Africa rather than dropping it.
        const lon = event.lon == null ? NaN : Number(event.lon);
        const lat = event.lat == null ? NaN : Number(event.lat);
        if (!Number.isFinite(lon) || !Number.isFinite(lat)) return features;
        features.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: [lon, lat] },
          properties: {
            radius: event.symbol?.radius ?? 3,
            color: event.symbol?.color ?? "#6E7B85",
            strokeWidth: event.symbol?.strokeWidth ?? 1.4,
            popupHtml: event.popupHtml || "",
            ariaLabel: event.ariaLabel || "",
          },
        });
        return features;
      }, []),
    });
    mapInstance.setPaintProperty(EVENTS_CIRCLE, "circle-opacity", mapEvents?.opacity ?? 0.85);
    if (mapEvents?.strokeColor) {
      mapInstance.setPaintProperty(EVENTS_CIRCLE, "circle-stroke-color", mapEvents.strokeColor);
    }
  }

  // The same star the 2D map draws, wrapped in a ring that breathes. The ring is
  // decoration, so CSS drops it under prefers-reduced-motion.
  function epicenterElement() {
    const wrap = document.createElement("div");
    wrap.className = "epicenter-3d";
    wrap.innerHTML =
      '<span class="epicenter-3d-pulse" aria-hidden="true"></span>' +
      '<svg class="epicenter-star" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">' +
      '<path d="M12 2.6l2.78 5.63 6.22.91-4.5 4.38 1.06 6.19L12 16.79 6.44 19.71l1.06-6.19L3 9.14l6.22-.91L12 2.6z" ' +
      'fill="#ffffff" stroke="#000000" stroke-width="2" stroke-linejoin="round"/></svg>';
    return wrap;
  }

  function applyEpicenter(event) {
    const lat = event?.lat == null ? NaN : Number(event.lat);
    const lon = event?.lon == null ? NaN : Number(event.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      epicenterMarker?.remove();
      epicenterMarker = null;
      return;
    }
    if (!epicenterMarker) {
      epicenterMarker = new maplibregl.Marker({ element: epicenterElement(), anchor: "center" })
        .setPopup(new maplibregl.Popup({ offset: 16 }))
        // Positioned before attaching: MapLibre reads the coordinate on add.
        .setLngLat([lon, lat])
        .addTo(mapInstance);
    } else {
      epicenterMarker.setLngLat([lon, lat]);
    }
    epicenterMarker.getPopup().setText(event.epicenterLabel || "Epicenter");
  }

  // Published analysis state the 3D renderer draws. Every value arrives as plain
  // data the 2D map already rendered; nothing is recomputed here.
  function applyState(state) {
    if (!mapInstance || !state) return;
    setBasemap(state.basemap || styleConfig().themeBasemap(state.theme));
    if (state.theme) mapInstance.setSky(skyFor(state.theme));
    applyMmi(state.currentMmi);
    applyMapEvents(state.mapEvents);
    applyEpicenter(state.activeEvent);
  }

  function createMap(camera) {
    const initial = camera || DEFAULT_CAMERA;
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
        center: initial.center,
        zoom: initial.zoom,
        bearing: initial.bearing ?? 0,
        pitch: initial.pitch ?? 55,
        maxPitch: 70,
        attributionControl: true,
        // Touch drag must stay a map pan: two-finger rotate and pitch would
        // fight the page scroll on a phone. Mouse and keyboard keep both.
        dragRotate: true,
        touchPitch: false,
        style: buildStyle(initialBasemapName()),
      });
      mapInstance.touchZoomRotate?.disableRotation();
      mapInstance.addControl(
        // Compass doubles as the reset-north control MapLibre gives for free.
        new maplibregl.NavigationControl({ visualizePitch: true, showCompass: true }),
        "top-right"
      );
      mapInstance.once("load", ready);
      mapInstance.on("error", fail);
      mapInstance.on("moveend", emitCameraChange);
      bindInteractions();
    });
  }

  // Clicks report intent to the coordinator rather than acting locally, so the
  // selected band stays one piece of state shared by both renderers.
  function bindInteractions() {
    const pointer = layer => {
      mapInstance.on("mouseenter", layer, () => { mapInstance.getCanvas().style.cursor = "pointer"; });
      mapInstance.on("mouseleave", layer, () => { mapInstance.getCanvas().style.cursor = ""; });
    };
    pointer(MMI_FILL);
    pointer(EVENTS_CIRCLE);

    mapInstance.on("click", EVENTS_CIRCLE, event => {
      const feature = event.features?.[0];
      if (!feature?.properties?.popupHtml) return;
      new maplibregl.Popup({ className: "quake-event-popup", offset: 8 })
        .setLngLat(feature.geometry.coordinates.slice())
        .setHTML(feature.properties.popupHtml)
        .addTo(mapInstance);
    });

    mapInstance.on("click", MMI_FILL, event => {
      const level = event.features?.[0]?.properties?.mmi_lower;
      if (level != null) window.eqmonMapModes?.emit("selectMmiBand", Number(level));
    });

    mapInstance.on("mousemove", MMI_FILL, event => {
      const level = event.features?.[0]?.properties?.mmi_lower;
      if (level != null) window.eqmonMapModes?.emit("hoverMmiBand", Number(level));
    });
    mapInstance.on("mouseleave", MMI_FILL, () => {
      window.eqmonMapModes?.emit("hoverMmiBand", null);
    });

    // Clicking bare map clears the selected band, as it does in 2D.
    mapInstance.on("click", event => {
      const hits = mapInstance.queryRenderedFeatures(event.point, { layers: [MMI_FILL] });
      if (!hits.length) window.eqmonMapModes?.emit("clearMmiSelection");
    });
  }

  async function initializeMapLibre3d(camera) {
    await loadDependencies();
    registerPmtilesProtocol();
    const instance = await createMap(camera);
    await enableTerrain();
    return instance;
  }

  function ensureMapLibre3d(camera) {
    if (initializationPromise) return initializationPromise;
    if (mapInstance) {
      mapInstance.resize();
      return Promise.resolve(mapInstance);
    }
    initializationPromise = initializeMapLibre3d(camera).finally(() => {
      initializationPromise = null;
    });
    return initializationPromise;
  }

  window.eqmonMapLibre3d = {
    ensureMapLibre3d,
    hasInstance: () => Boolean(mapInstance),
    resize: () => mapInstance?.resize(),
    setCamera,
    getCamera: readCamera,
    onCameraChange,
    applyState,
    setBasemap,
    getBasemap: () => currentBasemap,
    hasTerrain: () => terrainEnabled,
  };
})();
