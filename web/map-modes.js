/* Mode coordinator: owns the normalized camera and the shared analysis state,
   and activates exactly one renderer. Feature modules publish plain data here;
   they never reach across into the other renderer. */
(function () {
  "use strict";

  const STORAGE_KEY = "eqmon-map-mode";
  const leafletContainer = document.getElementById("map");
  const map3dContainer = document.getElementById("map-3d");
  const control = document.getElementById("map-mode-control");
  const loading = document.getElementById("map-mode-loading");
  const buttons = Object.fromEntries(
    Array.from(control.querySelectorAll("[data-map-mode]"), button => [button.dataset.mapMode, button])
  );
  let activeMode = "2d";
  let requestVersion = 0;
  let initializing = false;

  // --- Normalized camera ---------------------------------------------------
  // One shape for both renderers: lon/lat order, Leaflet zoom levels, and the
  // bearing/pitch that only the 3D renderer can honour. The [lat, lon] order
  // exists nowhere outside readLeafletCamera/applyLeafletCamera.
  const DEFAULT_CAMERA = { center: [69.3, 30.4], zoom: 5, bearing: 0, pitch: 0 };
  const DEFAULT_3D_PITCH = 55;   // DG-3
  const MAX_PITCH = 70;          // DG-3
  // Zoom is measured against 256px tiles in 2D and 512px tiles in 3D, so the
  // same ground scale sits exactly one level apart. This is the only place that
  // offset is applied.
  const LEAFLET_TO_MAPLIBRE_ZOOM_OFFSET = -1;

  let camera = { ...DEFAULT_CAMERA };
  let synchronizingCamera = false;

  function leafletZoomToMapLibre(zoom) {
    return zoom + LEAFLET_TO_MAPLIBRE_ZOOM_OFFSET;
  }

  function mapLibreZoomToLeaflet(zoom) {
    return zoom - LEAFLET_TO_MAPLIBRE_ZOOM_OFFSET;
  }

  function finite(value, fallback) {
    return Number.isFinite(value) ? value : fallback;
  }

  function normalizeCamera(input) {
    const source = input || {};
    const center = Array.isArray(source.center) ? source.center : [];
    const lon = finite(Number(center[0]), DEFAULT_CAMERA.center[0]);
    const lat = finite(Number(center[1]), DEFAULT_CAMERA.center[1]);
    const bearing = ((finite(Number(source.bearing), 0) % 360) + 360) % 360;
    const pitch = Math.min(MAX_PITCH, Math.max(0, finite(Number(source.pitch), 0)));
    return {
      center: [lon, Math.min(85, Math.max(-85, lat))],
      zoom: finite(Number(source.zoom), DEFAULT_CAMERA.zoom),
      bearing,
      pitch,
    };
  }

  function toMapLibreCamera(normalized) {
    return {
      center: [normalized.center[0], normalized.center[1]],
      zoom: leafletZoomToMapLibre(normalized.zoom),
      bearing: normalized.bearing,
      pitch: normalized.pitch,
    };
  }

  function readLeafletCamera() {
    const center = map.getCenter();
    // Bearing and pitch survive a 2D visit untouched: the 2D renderer cannot
    // express them, so it must not be allowed to reset them either.
    return { center: [center.lng, center.lat], zoom: map.getZoom(), bearing: camera.bearing, pitch: camera.pitch };
  }

  function applyLeafletCamera(next) {
    map.setView([next.center[1], next.center[0]], next.zoom, { animate: false });
  }

  function captureLeafletCamera() {
    if (synchronizingCamera) return;
    camera = normalizeCamera(readLeafletCamera());
  }

  function captureMapLibreCamera(next) {
    if (synchronizingCamera) return;
    camera = normalizeCamera({ ...next, zoom: mapLibreZoomToLeaflet(next?.zoom) });
  }

  function cameraFor3d() {
    // A 2D session carries pitch 0; entering 3D flat would waste the mode.
    return normalizeCamera({ ...camera, pitch: camera.pitch || DEFAULT_3D_PITCH });
  }

  // The guard covers the whole synchronization: both renderers emit "moveend"
  // synchronously for non-animated moves, so a move applied here can never be
  // recaptured as though the operator had made it.
  function synchronizeCameraTo(mode) {
    synchronizingCamera = true;
    try {
      if (mode === "3d") {
        camera = cameraFor3d();
        window.eqmonMapLibre3d.setCamera(toMapLibreCamera(camera));
      } else {
        applyLeafletCamera(camera);
      }
    } finally {
      synchronizingCamera = false;
    }
  }

  function setCamera(next) {
    camera = normalizeCamera(next);
    synchronizeCameraTo(activeMode);
  }

  // --- Shared analysis state -----------------------------------------------
  // Plain JSON only: no renderer layers, source handles, DOM nodes, or class
  // instances. Switching modes republishes this; it never refetches analysis.
  const sharedState = {
    activeEvent: null,
    currentMmi: null,
    mapEvents: null,
    basemap: null,
    overlays: null,
    landslides: null,
    pga: null,
    buildings: null,
    theme: null,
    alertLevel: null,
  };

  function clone(value) {
    return value == null ? null : JSON.parse(JSON.stringify(value));
  }

  function getState() {
    return clone(sharedState);
  }

  function publishState(patch) {
    if (!patch || typeof patch !== "object") return;
    let changed = false;
    Object.entries(patch).forEach(([key, value]) => {
      if (!Object.prototype.hasOwnProperty.call(sharedState, key)) return;
      sharedState[key] = clone(value);
      changed = true;
    });
    if (changed) {
      const snapshot = getState();
      // The 3D renderer only ever sees this snapshot, never a feature module.
      if (window.eqmonMapLibre3d?.hasInstance()) window.eqmonMapLibre3d.applyState(snapshot);
      window.dispatchEvent(new CustomEvent("eqmon:map-state", { detail: snapshot }));
    }
  }

  // Feature modules load before this file, so their early publications land on
  // a buffering shim they create; drain it once the real store exists.
  const buffered = window.eqmonMapState;
  window.eqmonMapState = { queue: [], publish: publishState };
  if (Array.isArray(buffered?.queue)) buffered.queue.forEach(publishState);

  // --- Layout --------------------------------------------------------------
  function resize() {
    if (typeof map !== "undefined") map.invalidateSize();
    if (window.eqmonMapLibre3d?.hasInstance()) window.eqmonMapLibre3d.resize();
  }

  function webgl2Available() {
    try {
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2");
      context?.getExtension("WEBGL_lose_context")?.loseContext();
      return Boolean(context);
    } catch (error) {
      return false;
    }
  }

  const canUse3d = webgl2Available();

  function persistedMode() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (error) {
      return null;
    }
  }

  function persistMode(mode) {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch (error) {
      // Private browsing can deny storage without affecting renderer selection.
    }
  }

  function clearUnavailable3dPreference() {
    if (persistedMode() !== "3d") return;
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      // Storage is optional.
    }
  }

  function setPressed(mode) {
    Object.entries(buttons).forEach(([key, button]) => {
      button.setAttribute("aria-pressed", String(key === mode));
    });
  }

  function publishMode(mode) {
    window.dispatchEvent(new CustomEvent("eqmon:map-mode", {
      detail: { mode, camera: { ...camera, center: [...camera.center] }, state: getState() },
    }));
  }

  function show2d({ persist = true } = {}) {
    requestVersion += 1;
    initializing = false;
    const wasThreeD = activeMode === "3d";
    activeMode = "2d";
    document.body.classList.remove("map-mode-3d");
    map3dContainer.setAttribute("aria-hidden", "true");
    loading.hidden = true;
    buttons["3d"].disabled = !canUse3d;
    buttons["3d"].removeAttribute("aria-busy");
    setPressed("2d");
    if (persist) persistMode("2d");
    if (typeof map !== "undefined") {
      if (wasThreeD) synchronizeCameraTo("2d");
      window.setTimeout(resize, 0);
    }
    publishMode("2d");
  }

  async function show3d({ persist = true } = {}) {
    if (!canUse3d) {
      clearUnavailable3dPreference();
      show2d({ persist: false });
      if (typeof toast === "function") toast("3D map unavailable; returned to 2D.", "warn", 6000);
      return;
    }

    const requestedVersion = ++requestVersion;
    initializing = true;
    loading.hidden = leafletContainer.style.display === "none";
    buttons["3d"].disabled = true;
    buttons["3d"].setAttribute("aria-busy", "true");

    try {
      await window.eqmonMapLibre3d.ensureMapLibre3d(toMapLibreCamera(cameraFor3d()));
      if (requestedVersion !== requestVersion) return;
      initializing = false;
      map3dContainer.hidden = false;
      map3dContainer.setAttribute("aria-hidden", "false");
      document.body.classList.add("map-mode-3d");
      activeMode = "3d";
      loading.hidden = true;
      buttons["3d"].disabled = false;
      buttons["3d"].removeAttribute("aria-busy");
      setPressed("3d");
      window.eqmonMapLibre3d.onCameraChange(captureMapLibreCamera);
      // A 2D session may have changed basemap or theme while 3D was idle.
      window.eqmonMapLibre3d.applyState(getState());
      synchronizeCameraTo("3d");
      window.eqmonMapLibre3d.resize();
      if (persist) persistMode("3d");
      publishMode("3d");
    } catch (error) {
      if (requestedVersion !== requestVersion) return;
      clearUnavailable3dPreference();
      show2d({ persist: false });
      console.error("3D map initialization failed", error);
      if (typeof toast === "function") toast("3D map unavailable; returned to 2D.", "warn", 6000);
    }
  }

  function setMode(mode, options) {
    return mode === "3d" ? show3d(options) : show2d(options);
  }

  function syncAlternateView() {
    const suspended = leafletContainer.style.display === "none";
    map3dContainer.style.display = suspended ? "none" : "";
    control.hidden = suspended;
    loading.hidden = suspended || !initializing;
    if (!suspended) window.setTimeout(resize, 0);
  }

  buttons["2d"].addEventListener("click", () => setMode("2d"));
  buttons["3d"].addEventListener("click", () => setMode("3d"));
  new MutationObserver(syncAlternateView).observe(leafletContainer, {
    attributes: true,
    attributeFilter: ["style"],
  });

  if (typeof map !== "undefined") {
    map.on("moveend", captureLeafletCamera);
    captureLeafletCamera();
  }

  if (!canUse3d) {
    buttons["3d"].disabled = true;
    buttons["3d"].title = "3D requires WebGL 2";
    clearUnavailable3dPreference();
  } else if (persistedMode() === "3d") {
    setMode("3d", { persist: false });
  }

  window.eqmonMapModes = {
    setMode,
    getMode: () => activeMode,
    setCamera,
    getCamera: () => ({ ...camera, center: [...camera.center] }),
    publish: publishState,
    getState,
    resize,
  };
})();
