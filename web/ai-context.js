/* A bounded, renderer-neutral projection of the current analyst workspace. */
(function () {
  "use strict";

  const VERSION = "1.0";
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : null;
  const value = id => document.getElementById(id)?.value?.trim() || null;
  const utcDate = input => input && /^\d{4}-\d{2}-\d{2}$/.test(input)
    ? `${input}T00:00:00Z` : input;

  function layer(id, visible, opacity) {
    const result = { id: String(id), visible: Boolean(visible) };
    const normalizedOpacity = finite(opacity);
    if (normalizedOpacity != null) result.opacity = normalizedOpacity;
    return result;
  }

  function eventId(activeEvent) {
    const id = activeEvent?.id ?? activeEvent?.event_id;
    return id == null || String(id).trim() === "" ? null : String(id);
  }

  function sources() {
    const selected = document.querySelector(".cat-tab.active")?.dataset?.src;
    if (!selected || selected === "ALL") return [];
    return [selected];
  }

  function collect() {
    const modes = window.eqmonMapModes;
    if (!modes?.getState || !modes?.getCamera || !modes?.getMode) return null;
    const state = modes.getState() || {};
    const camera = modes.getCamera() || {};
    if (![camera.center?.[0], camera.center?.[1], camera.zoom].every(item => finite(item) != null)) return null;
    const reference = Object.values(state.overlays || {}).slice(0, 64)
      .filter(item => item?.id != null).map(item =>
        layer(item.id, item.visible, item.opacity));
    const landslides = (state.landslides?.regions || []).slice(0, 64)
      .filter(item => item?.key != null).map(item =>
        layer(item.key, item.enabled, state.landslides.opacity));
    const minimumMagnitude = finite(value("filter-minmag"));
    const maximumMagnitude = finite(value("filter-maxmag"));
    const timeWindow = state.mapEvents
      ? [state.mapEvents.startIndex, state.mapEvents.endIndex].map(finite) : null;
    const selectedSection = document.querySelector(".rail-ic.active[data-section]")?.dataset?.section || null;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches || false;
    return {
      schema_version: VERSION,
      captured_at: new Date().toISOString(),
      map: {
        mode: modes.getMode(),
        center: [finite(camera.center?.[0]), finite(camera.center?.[1])],
        zoom: finite(camera.zoom),
        bearing: finite(camera.bearing) ?? 0,
        pitch: finite(camera.pitch) ?? 0,
        basemap: state.basemap || null,
      },
      selection: {
        event_id: eventId(state.activeEvent),
        mmi_level: finite(state.currentMmi?.selectedLevel),
        sidebar_section: selectedSection,
      },
      layers: {
        reference,
        landslides,
        pga: state.pga ? {
          visible: Boolean(state.pga.enabled),
          return_period: finite(state.pga.returnPeriod),
          opacity: finite(state.pga.opacity),
        } : null,
        buildings: state.buildings ? {
          visible: Boolean(state.buildings.enabled),
          selected_district: state.buildings.selected || null,
          opacity: finite(state.buildings.opacity),
        } : null,
        mmi: state.currentMmi ? {
          visible: Boolean(state.currentMmi.visible),
          opacity: finite(state.currentMmi.opacity),
        } : null,
      },
      event_filters: {
        sources: sources(),
        minimum_magnitude: minimumMagnitude,
        maximum_magnitude: maximumMagnitude,
        date_from: utcDate(value("filter-after")),
        date_to: utcDate(value("filter-before")),
        search: value("filter-search"),
        time_window_indices: timeWindow?.every(item => item != null) ? timeWindow : null,
      },
      display: {
        theme: state.theme === "dark" ? "dark" : "light",
        reduced_motion: reduceMotion,
      },
    };
  }

  window.eqmonAiContext = { collect };
})();
