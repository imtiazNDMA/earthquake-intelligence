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
  const OVERLAY_PREFIX = "overlay-";
  const BUILDINGS_PREFIX = "buildings-";
  const BUILDINGS_SOURCE_LAYER = "buildings";
  const LANDSLIDE_PREFIX = "landslide-";
  const PGA_SOURCE = "pga-hazard";
  const PGA_LAYER = "pga-hazard-raster";
  // A line of a given pixel width covers less ground the further it is from the
  // camera, so at pitch the same nominal width reads thinner than it does flat.
  // A modest constant restores the visual weight without turning boundaries into
  // ribbons at the horizon.
  const PITCH_LINE_MULTIPLIER = 1.25;
  const registeredOverlays = new Map();
  // districtId -> nothing but its own liveness; insertion order is the eviction
  // order when the cap is reached.
  const liveDistricts = new Set();
  let buildingsState = null;
  let overlayTooltip = null;
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
  let styleReloadToken = 0;
  let lastState = null;
  let stateApplyPending = false;
  let terrainEnabled = false;
  let terrainAnnounced = false;
  const hazardErrors = new Set();
  let rendererFailureListener = null;
  let renderingPaused = false;

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
    const mobile = window.matchMedia?.("(max-width: 760px)").matches;
    mapInstance.jumpTo({
      center: camera.center,
      zoom: camera.zoom,
      bearing: mobile ? 0 : (camera.bearing ?? 0),
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

  function analysisSources() {
    const terrain = styleConfig().TERRAIN;
    return {
      [MMI_SOURCE]: { type: "geojson", data: EMPTY_FC },
      [EVENTS_SOURCE]: { type: "geojson", data: EMPTY_FC },
      // The DEM feeds both the terrain mesh and the hillshade, so its credit is
      // attached once and MapLibre prints it once.
      [DEM_SOURCE]: {
        type: "raster-dem",
        tiles: terrain.tiles,
        encoding: terrain.encoding,
        tileSize: terrain.tileSize,
        maxzoom: terrain.maxzoom,
        attribution: terrain.attribution,
      },
    };
  }

  // Shading only, at low strength: relief should read as depth cue, not as
  // another data layer competing with the hazard palette above it.
  const hillshadeLayer = () => ({
    id: HILLSHADE_LAYER,
    type: "hillshade",
    source: DEM_SOURCE,
    paint: {
      "hillshade-exaggeration": 0.25,
      "hillshade-shadow-color": "#1c232b",
      "hillshade-highlight-color": "#ffffff",
    },
  });

  const analysisLayers = () => [
    {
      id: MMI_FILL,
      type: "fill",
      source: MMI_SOURCE,
      // Severity ordering: a stronger band is drawn last and so is never buried
      // under the weaker band that surrounds it.
      layout: { "fill-sort-key": ["get", "mmi_lower"] },
      paint: { "fill-color": ["get", "color"], "fill-opacity": MMI_BASE_OPACITY },
    },
    {
      id: MMI_LINE,
      type: "line",
      source: MMI_SOURCE,
      // Band colour, exactly as in 2D. The MMI palette is theme-independent, so
      // the border reads the same against a light or a dark basemap.
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
      // Radius and colour ride on the feature: they come from the same magnitude
      // and depth rules the 2D bubbles are drawn with.
      paint: {
        "circle-radius": ["get", "radius"],
        "circle-color": ["get", "color"],
        "circle-opacity": 0.85,
        "circle-stroke-width": ["get", "strokeWidth"],
        "circle-stroke-color": "#F4F6F8",
        "circle-stroke-opacity": 0.95,
      },
    },
  ];

  // Any basemap style, raster or vector, plus everything this renderer draws on
  // top of it. Relief slips under the basemap's own labels; analysis goes above.
  function composeStyle(base) {
    const layers = [...base.layers];
    const labels = layers.findIndex(layer => layer.type === "symbol");
    layers.splice(labels < 0 ? layers.length : labels, 0, hillshadeLayer());
    return {
      ...base,
      sources: { ...base.sources, ...analysisSources() },
      layers: [...layers, ...analysisLayers()],
      sky: skyFor(document.documentElement.dataset.theme),
    };
  }

  function rasterBase(name) {
    return {
      version: 8,
      sources: { [BASEMAP_SOURCE]: styleConfig().maplibreSource(name) },
      layers: [{ id: BASEMAP_LAYER, type: "raster", source: BASEMAP_SOURCE }],
    };
  }

  // Imagery with the labels of a vector style on top. composeStyle then slips
  // the hillshade in above the imagery and below those labels.
  async function hybridBase(name) {
    const config = styleConfig();
    const labels = await config.labelStyle(name);
    const base = rasterBase(name);
    return {
      ...labels,
      sources: { ...base.sources, ...labels.sources },
      layers: [...base.layers, ...labels.layers],
    };
  }

  async function styleFor(name) {
    const config = styleConfig();
    currentBasemap = name;
    if (config.isRaster(name)) return composeStyle(rasterBase(name));
    if (!config.isVector(name)) return composeStyle(await hybridBase(name));
    const response = await fetch(config.styleUrl(name));
    if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
    return composeStyle(await response.json());
  }

  function setBasemap(name) {
    const config = styleConfig();
    if (!mapInstance || !name || name === currentBasemap || !config) return;
    // Only a plain raster swap can be done in place; anything else brings its
    // own layers and needs the style rebuilt.
    if (!config.isRaster(name) || !config.isRaster(currentBasemap)) return reloadStyle(name);
    swapRasterBasemap(name);
  }

  // Rebuilt rather than retiled: every basemap carries its own zoom ceiling and
  // credit, and a raster source can change neither in place. Only the bottom
  // layer is touched, so terrain, hillshade, and analysis layers above survive.
  function swapRasterBasemap(name) {
    const config = styleConfig();
    if (!mapInstance.getSource(BASEMAP_SOURCE)) return;
    const above = mapInstance.getStyle().layers[1]?.id;
    if (mapInstance.getLayer(BASEMAP_LAYER)) mapInstance.removeLayer(BASEMAP_LAYER);
    mapInstance.removeSource(BASEMAP_SOURCE);
    mapInstance.addSource(BASEMAP_SOURCE, config.maplibreSource(name));
    mapInstance.addLayer({ id: BASEMAP_LAYER, type: "raster", source: BASEMAP_SOURCE }, above);
    currentBasemap = name;
  }

  // `styledata` fires several times while a style is being installed, and the
  // first of them lands before MapLibre will accept paint or sky calls. Waiting
  // for isStyleLoaded is the difference between a switch and a rollback.
  function styleLoaded(timeoutMs = 15000) {
    return new Promise(resolve => {
      if (mapInstance.isStyleLoaded()) return resolve(true);
      const finish = ok => {
        mapInstance.off("styledata", check);
        window.clearTimeout(timer);
        resolve(ok);
      };
      const check = () => { if (mapInstance.isStyleLoaded()) finish(true); };
      const timer = window.setTimeout(() => finish(false), timeoutMs);
      mapInstance.on("styledata", check);
    });
  }

  // A vector basemap brings its own layers, so the style is replaced wholesale.
  // Everything this renderer draws is registered again from the published state,
  // which is why switching never refetches analysis.
  function reloadStyle(name) {
    const previous = currentBasemap;
    const token = ++styleReloadToken;
    return styleFor(name)
      .then(style => {
        mapInstance.setStyle(style);
        // The old layers are gone as of this call, so nothing may claim they
        // still exist while the new style installs.
        registeredOverlays.clear();
        liveDistricts.clear();
        overlayTooltip = null;
        return styleLoaded();
      })
      .then(() => {
        if (token !== styleReloadToken) return null;
        // Terrain only after the style is installed: attaching a mesh to a
        // half-built style takes MapLibre's renderer down with it.
        return enableTerrain();
      })
      .then(() => {
        if (token === styleReloadToken && lastState) applyState(lastState);
      })
      .catch(error => {
        currentBasemap = previous;
        console.error("basemap unavailable", name, error);
        if (typeof toast === "function") toast(`${name} could not be loaded.`, "warn", 6000);
      });
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

  function overlaySourceId(id) { return `${OVERLAY_PREFIX}${id}`; }
  function overlayFillId(id) { return `${OVERLAY_PREFIX}${id}-fill`; }
  function overlayLineId(id) { return `${OVERLAY_PREFIX}${id}-line`; }

  // Fill paint for one overlay, or null when it draws no fill at all. Three
  // published schemes, in the same precedence the 2D symbolizer uses.
  function overlayFillColor(overlay) {
    if (overlay.categorical) {
      const pairs = Object.entries(overlay.categorical.colors).flat();
      // An unlisted class stays transparent rather than borrowing a colour it
      // was never assigned: this palette is published, not decorative.
      return ["match", ["get", overlay.categorical.prop], ...pairs, "rgba(0,0,0,0)"];
    }
    if (overlay.namedFill) return "rgba(0,0,0,0)";   // replaced once names are known
    return overlay.fillColor;
  }

  function overlayHasFill(overlay) {
    return Boolean(overlay.categorical || overlay.namedFill || overlay.fillColor);
  }

  // Registered once and then only toggled. Rebuilding a vector source on every
  // checkbox would refetch the archive and strip any handler bound to its layer.
  function registerOverlay(name, overlay) {
    const sourceId = overlaySourceId(overlay.id);
    if (mapInstance.getLayer(overlayLineId(overlay.id))) return;
    if (!mapInstance.getSource(sourceId)) {
      mapInstance.addSource(sourceId, {
        type: "vector",
        url: `pmtiles://${new URL(`/tiles/${overlay.id}.pmtiles`, location.href).href}`,
      });
    }
    const visibility = overlay.visible ? "visible" : "none";
    if (overlayHasFill(overlay)) {
      mapInstance.addLayer({
        id: overlayFillId(overlay.id),
        type: "fill",
        source: sourceId,
        "source-layer": overlay.id,
        layout: { visibility },
        paint: {
          "fill-color": overlayFillColor(overlay),
          "fill-opacity": overlay.fillOpacity ?? overlay.opacity ?? 1,
        },
      }, EVENTS_CIRCLE);
    }
    mapInstance.addLayer({
      id: overlayLineId(overlay.id),
      type: "line",
      source: sourceId,
      "source-layer": overlay.id,
      layout: { visibility, "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": overlay.color,
        "line-width": overlay.width * PITCH_LINE_MULTIPLIER,
        "line-opacity": overlay.opacity ?? 1,
      },
    }, EVENTS_CIRCLE);
    registeredOverlays.set(name, { ...overlay });
  }

  function updateOverlay(name, overlay) {
    const previous = registeredOverlays.get(name);
    if (!previous) return;
    const visibility = overlay.visible ? "visible" : "none";
    const lineId = overlayLineId(overlay.id);
    mapInstance.setLayoutProperty(lineId, "visibility", visibility);
    mapInstance.setPaintProperty(lineId, "line-color", overlay.color);
    mapInstance.setPaintProperty(lineId, "line-width", overlay.width * PITCH_LINE_MULTIPLIER);
    mapInstance.setPaintProperty(lineId, "line-opacity", overlay.opacity ?? 1);
    if (overlayHasFill(overlay)) {
      const fillId = overlayFillId(overlay.id);
      mapInstance.setLayoutProperty(fillId, "visibility", visibility);
      if (!overlay.namedFill) mapInstance.setPaintProperty(fillId, "fill-color", overlayFillColor(overlay));
      mapInstance.setPaintProperty(fillId, "fill-opacity", overlay.fillOpacity ?? overlay.opacity ?? 1);
    }
    registeredOverlays.set(name, { ...overlay });
    if (overlay.namedFill && overlay.visible) applyNamedFill(overlay);
  }

  // A pastel per distinct name, matching 2D. The names only exist once tiles have
  // arrived, so the expression is built from what the source has actually loaded
  // and refreshed as more comes in.
  function applyNamedFill(overlay) {
    const format = window.eqmonOverlayFormat;
    const fillId = overlayFillId(overlay.id);
    if (!format || !mapInstance.getLayer(fillId)) return;
    let features = [];
    try {
      features = mapInstance.querySourceFeatures(overlaySourceId(overlay.id), { sourceLayer: overlay.id });
    } catch (error) {
      return;   // source not ready yet; a later sourcedata event retries
    }
    const names = [...new Set(features.map(f => f.properties?.[overlay.namedFill]).filter(Boolean))];
    if (!names.length) return;
    const pairs = names.flatMap(value => [value, format.pastelFromName(value)]);
    mapInstance.setPaintProperty(fillId, "fill-color",
      ["match", ["get", overlay.namedFill], ...pairs, "rgba(0,0,0,0)"]);
  }

  function applyOverlays(overlays) {
    if (!overlays) return;
    Object.entries(overlays).forEach(([name, overlay]) => {
      if (!overlay?.id) return;
      // A style swap can outlive the registry, so liveness is read off the map.
      const live = registeredOverlays.has(name) && mapInstance.getLayer(overlayLineId(overlay.id));
      if (live) updateOverlay(name, overlay);
      else registerOverlay(name, overlay);
    });
  }

  // Hover reads whichever visible overlay is under the cursor and formats it
  // with the shared rules, so the tooltip is the one the 2D map would show.
  function overlayHoverHtml(point) {
    const format = window.eqmonOverlayFormat;
    if (!format) return null;
    for (const [name, overlay] of registeredOverlays) {
      if (!overlay.visible || !overlay.hover) continue;
      const layers = [overlayLineId(overlay.id)];
      if (overlayHasFill(overlay)) layers.unshift(overlayFillId(overlay.id));
      const live = layers.filter(id => mapInstance.getLayer(id));
      if (!live.length) continue;
      const pad = overlay.hover.tolerancePx;
      const box = pad
        ? [[point.x - pad, point.y - pad], [point.x + pad, point.y + pad]]
        : point;
      const hits = mapInstance.queryRenderedFeatures(box, { layers: live });
      if (hits.length) return format.tooltipHtml(name, overlayConfigFor(overlay), hits[0].properties);
    }
    return null;
  }

  // The shared formatter takes an overlay config; the published shape names the
  // same things slightly differently.
  function overlayConfigFor(overlay) {
    return {
      hoverFields: overlay.hover.fields,
      hoverLabels: overlay.hover.labels || undefined,
      hoverUnits: overlay.hover.units || undefined,
      hoverTolerancePx: overlay.hover.tolerancePx,
    };
  }

  function showOverlayTooltip(event) {
    const html = overlayHoverHtml(event.point);
    if (!html) {
      overlayTooltip?.remove();
      overlayTooltip = null;
      return;
    }
    if (!overlayTooltip) {
      overlayTooltip = new maplibregl.Popup({
        className: "fault-tooltip",
        closeButton: false,
        closeOnClick: false,
        offset: 8,
      });
    }
    overlayTooltip.setLngLat(event.lngLat).setHTML(html).addTo(mapInstance);
  }


  /* ---- building extrusions ---- */

  function buildingsConfig() { return window.eqmonBuildingsConfig; }
  function buildingsSourceId(district) { return `${BUILDINGS_PREFIX}${district}`; }
  function buildingsLayerId(district) { return `${BUILDINGS_PREFIX}${district}-extrusion`; }

  // The catalog is published in Leaflet zoom levels, the only scale the minimum
  // zoom is ever expressed in, so the camera is converted rather than the rule.
  function wantedDistricts() {
    const cfg = buildingsConfig();
    const modes = window.eqmonMapModes;
    if (!cfg || !modes?.toLeafletZoom || !buildingsState?.enabled) return [];
    return cfg.visibleDistricts(
      buildingsState.catalog,
      mapInstance.getBounds(),
      modes.toLeafletZoom(mapInstance.getZoom()),
      buildingsState.minZoom,
      buildingsState.selected,
      buildingsState.maxSources ?? cfg.MAX_LIVE_SOURCES
    );
  }

  function addDistrict(district) {
    const cfg = buildingsConfig();
    const sourceId = buildingsSourceId(district);
    if (!mapInstance.getSource(sourceId)) {
      mapInstance.addSource(sourceId, {
        type: "vector",
        tiles: [location.origin + cfg.tileUrl(district)],
        maxzoom: cfg.DATA_MAXZOOM,
      });
    }
    if (mapInstance.getLayer(buildingsLayerId(district))) {
      liveDistricts.add(district);
      return;
    }
    mapInstance.addLayer({
      id: buildingsLayerId(district),
      type: "fill-extrusion",
      source: sourceId,
      "source-layer": BUILDINGS_SOURCE_LAYER,
      minzoom: window.eqmonMapModes.toMapLibreZoom(buildingsState.minZoom),
      paint: {
        "fill-extrusion-color": cfg.colorExpression(),
        "fill-extrusion-height": cfg.heightExpression(),
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": buildingsState.opacity ?? cfg.OPACITY,
      },
    // Context, not analysis: extrusions stay under the shaking footprint and
    // the event bubbles.
    }, MMI_FILL);
    liveDistricts.add(district);
  }

  function removeDistrict(district) {
    if (mapInstance.getLayer(buildingsLayerId(district))) mapInstance.removeLayer(buildingsLayerId(district));
    if (mapInstance.getSource(buildingsSourceId(district))) mapInstance.removeSource(buildingsSourceId(district));
    liveDistricts.delete(district);
  }

  function onRendererFailure(handler) {
    rendererFailureListener = typeof handler === "function" ? handler : null;
  }

  function setPaused(paused) {
    renderingPaused = Boolean(paused);
    if (!mapInstance) return;
    if (renderingPaused) mapInstance.stop?.();
    else {
      mapInstance.resize();
      mapInstance.triggerRepaint?.();
    }
  }

  function hazardUrl(path) {
    return new URL(path, location.href).href;
  }

  function hazardError(key, label) {
    if (hazardErrors.has(key)) return;
    hazardErrors.add(key);
    console.warn(`${label} unavailable`);
    if (typeof toast === "function") toast(`${label} unavailable.`, "warn", 6000);
  }

  function landslideSourceId(key) { return `${LANDSLIDE_PREFIX}${key}`; }
  function landslideLayerId(key) { return `${LANDSLIDE_PREFIX}${key}-raster`; }

  function applyLandslides(landslides) {
    if (!landslides?.regions) return;
    landslides.regions.forEach(region => {
      const sourceId = landslideSourceId(region.key);
      const layerId = landslideLayerId(region.key);
      if (!region.url) {
        if (region.enabled) hazardError(sourceId, `${region.label} landslide layer`);
        return;
      }
      try {
        if (!mapInstance.getSource(sourceId)) {
          mapInstance.addSource(sourceId, {
            type: "raster",
            url: `pmtiles://${hazardUrl(region.url)}`,
            minzoom: region.minZoom ?? 0,
            maxzoom: region.maxZoom ?? 22,
            tileSize: 256,
            attribution: "Landslide susceptibility source: supplied regional masks",
          });
        }
        if (!mapInstance.getLayer(layerId)) {
          mapInstance.addLayer({
            id: layerId,
            type: "raster",
            source: sourceId,
            layout: { visibility: region.enabled ? "visible" : "none" },
            paint: {
              "raster-opacity": landslides.opacity ?? 0.62,
              "raster-resampling": "nearest",
              "raster-fade-duration": 0,
            },
          }, MMI_FILL);
        } else {
          mapInstance.setLayoutProperty(layerId, "visibility", region.enabled ? "visible" : "none");
          mapInstance.setPaintProperty(layerId, "raster-opacity", landslides.opacity ?? 0.62);
        }
      } catch (error) {
        hazardError(sourceId, `${region.label} landslide layer`);
      }
    });
  }

  function applyPga(pga) {
    if (!pga) return;
    const renderable = Boolean(pga.enabled && pga.image && Array.isArray(pga.bounds));
    try {
      if (mapInstance.getLayer(PGA_LAYER)) mapInstance.removeLayer(PGA_LAYER);
      if (mapInstance.getSource(PGA_SOURCE)) mapInstance.removeSource(PGA_SOURCE);
      if (!renderable) return;
      const [west, south, east, north] = pga.bounds;
      mapInstance.addSource(PGA_SOURCE, {
        type: "image",
        url: hazardUrl(pga.image),
        coordinates: [[west, north], [east, north], [east, south], [west, south]],
        attribution: pga.attribution || "",
      });
      mapInstance.addLayer({
        id: PGA_LAYER,
        type: "raster",
        source: PGA_SOURCE,
        paint: {
          "raster-opacity": pga.opacity ?? 0.55,
          "raster-resampling": "nearest",
          "raster-fade-duration": 0,
        },
      }, MMI_FILL);
    } catch (error) {
      hazardError(PGA_SOURCE, "PGA hazard layer");
    }
  }

  function reconcileBuildings() {
    if (!mapInstance || !buildingsConfig()) return;
    const wanted = new Set(wantedDistricts());
    for (const district of [...liveDistricts]) {
      if (!wanted.has(district)) removeDistrict(district);
    }
    for (const district of wanted) {
      if (!liveDistricts.has(district)) addDistrict(district);
    }
  }

  function applyBuildings(buildings) {
    if (!buildings) return;
    const opacityChanged = buildings.opacity !== buildingsState?.opacity;
    buildingsState = buildings;
    if (opacityChanged) {
      const opacity = buildings.opacity ?? buildingsConfig().OPACITY;
      liveDistricts.forEach(district => {
        mapInstance.setPaintProperty(buildingsLayerId(district), "fill-extrusion-opacity", opacity);
      });
    }
    reconcileBuildings();
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
    lastState = state;
    // Published state can arrive mid-swap; it is applied once the style will
    // accept it, from whatever the newest snapshot is by then.
    if (!mapInstance.isStyleLoaded()) {
      if (!stateApplyPending) {
        stateApplyPending = true;
        styleLoaded().then(() => {
          stateApplyPending = false;
          applyState(lastState);
        });
      }
      return;
    }
    setBasemap(state.basemap || styleConfig().themeBasemap(state.theme));
    if (state.theme) mapInstance.setSky(skyFor(state.theme));
    applyOverlays(state.overlays);
    applyLandslides(state.landslides);
    applyPga(state.pga);
    applyMmi(state.currentMmi);
    applyMapEvents(state.mapEvents);
    applyEpicenter(state.activeEvent);
    applyBuildings(state.buildings);
  }

  function createMap(camera, style) {
    const initial = camera || DEFAULT_CAMERA;
    return new Promise((resolve, reject) => {
      let settled = false;
      // Generous on purpose: a vector basemap fetches a style, its glyphs, and
      // its first tiles before MapLibre reports "load".
      const timeout = window.setTimeout(() => fail(new Error("3D map initialization timed out")), 25000);

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
        style,
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
      const canvas = mapInstance.getCanvas();
      canvas.addEventListener?.("webglcontextlost", event => {
        event.preventDefault?.();
        terrainEnabled = false;
        rendererFailureListener?.(new Error("WebGL context lost"));
      });
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

    // Overlay hover, throttled the same way the 2D handler is.
    let lastHover = 0;
    mapInstance.on("mousemove", event => {
      const now = Date.now();
      if (now - lastHover < 50) return;
      lastHover = now;
      showOverlayTooltip(event);
    });
    mapInstance.on("mouseout", () => {
      overlayTooltip?.remove();
      overlayTooltip = null;
    });

    // Tectonic Zones needs its pastels rebuilt as tiles arrive.
    mapInstance.on("sourcedata", event => {
      if (event.sourceId?.startsWith(OVERLAY_PREFIX) && event.isSourceLoaded) {
        for (const overlay of registeredOverlays.values()) {
          if (overlay.namedFill && overlay.visible && overlaySourceId(overlay.id) === event.sourceId) {
            applyNamedFill(overlay);
          }
        }
      }
    });

    mapInstance.on("error", event => {
      if (event.sourceId?.startsWith(LANDSLIDE_PREFIX)) hazardError(event.sourceId, "Landslide layer");
      if (event.sourceId === PGA_SOURCE) hazardError(PGA_SOURCE, "PGA hazard layer");
    });

    mapInstance.on("moveend", reconcileBuildings);

    // Clicking bare map clears the selected band, as it does in 2D.
    mapInstance.on("click", event => {
      const hits = mapInstance.queryRenderedFeatures(event.point, { layers: [MMI_FILL] });
      if (!hits.length) window.eqmonMapModes?.emit("clearMmiSelection");
    });
  }

  async function initializeMapLibre3d(camera) {
    await loadDependencies();
    registerPmtilesProtocol();
    const instance = await createMap(camera, await styleFor(initialBasemapName()));
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
    // The 2D renderer needs the same library to draw a vector basemap in Leaflet.
    ensureLibrary: loadDependencies,
    hasInstance: () => Boolean(mapInstance),
    resize: () => mapInstance?.resize(),
    setCamera,
    getCamera: readCamera,
    onCameraChange,
    applyState,
    onRendererFailure,
    setPaused,
    isPaused: () => renderingPaused,
    overlayLayerIds: () => [...registeredOverlays.values()].flatMap(overlay => {
      const ids = [overlayLineId(overlay.id)];
      if (overlayHasFill(overlay)) ids.unshift(overlayFillId(overlay.id));
      return ids;
    }),
    setBasemap,
    getBasemap: () => currentBasemap,
    liveBuildingDistricts: () => [...liveDistricts],
    hasTerrain: () => terrainEnabled,
  };
})();
