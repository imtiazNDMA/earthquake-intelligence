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
      return localStorage.getItem("eqmon-map-mode");
    } catch (error) {
      return null;
    }
  }

  function persistMode(mode) {
    try {
      localStorage.setItem("eqmon-map-mode", mode);
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
    window.dispatchEvent(new CustomEvent("eqmon:map-mode", { detail: { mode } }));
  }

  function show2d({ persist = true } = {}) {
    requestVersion += 1;
    initializing = false;
    activeMode = "2d";
    document.body.classList.remove("map-mode-3d");
    map3dContainer.setAttribute("aria-hidden", "true");
    loading.hidden = true;
    buttons["3d"].disabled = !canUse3d;
    buttons["3d"].removeAttribute("aria-busy");
    setPressed("2d");
    if (persist) persistMode("2d");
    if (typeof map !== "undefined") window.setTimeout(() => map.invalidateSize(), 0);
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
      await window.eqmonMapLibre3d.ensureMapLibre3d();
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
    if (!suspended && activeMode === "3d") {
      window.setTimeout(() => window.eqmonMapLibre3d.resize(), 0);
    }
  }

  buttons["2d"].addEventListener("click", () => setMode("2d"));
  buttons["3d"].addEventListener("click", () => setMode("3d"));
  new MutationObserver(syncAlternateView).observe(leafletContainer, {
    attributes: true,
    attributeFilter: ["style"],
  });

  if (!canUse3d) {
    buttons["3d"].disabled = true;
    buttons["3d"].title = "3D requires WebGL 2";
    clearUnavailable3dPreference();
  } else if (persistedMode() === "3d") {
    setMode("3d", { persist: false });
  }

  window.eqmonMapModes = { setMode, getMode: () => activeMode };
})();
