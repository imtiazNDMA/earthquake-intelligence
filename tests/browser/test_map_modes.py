"""Browser checks for the things only a real renderer can answer.

Everything here is a judgement the Node harnesses cannot make: whether terrain
actually has relief at the scales an operator works at, whether the chrome stays
readable in both themes, and whether camera and analysis state really survive a
round trip through two live renderers.
"""

from __future__ import annotations

import pytest

# Muzaffarabad: mountainous, and the district the building tiles were sampled
# from during the Phase 0 spike.
DISTRICT_VIEW = {"center": [73.47, 34.37], "zoom": 11}
REGIONAL_VIEW = {"center": [69.3, 30.4], "zoom": 5}

MMI_FEATURES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"mmi_lower": 5, "color": "#7aff93"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[73.2, 34.1], [73.8, 34.1], [73.8, 34.7], [73.2, 34.7], [73.2, 34.1]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"mmi_lower": 7, "color": "#ffc800"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[73.35, 34.25], [73.6, 34.25], [73.6, 34.5], [73.35, 34.5], [73.35, 34.25]]],
            },
        },
    ],
}

ACTIVATE_3D = """
async () => {
  await window.eqmonMapModes.setMode("3d");
  return window.eqmonMapModes.getMode();
}
"""

# maplibregl is loaded lazily, so the handle is reachable only through the page.
WAIT_FOR_IDLE = """
() => new Promise(resolve => {
  const map = window.__map3d;
  if (map.loaded() && !map.isMoving()) { resolve(true); return; }
  map.once("idle", () => resolve(true));
})
"""


def _open(page, app_server, console_errors):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(app_server, wait_until="load")
    page.wait_for_function("() => window.eqmonMapModes && window.eqmonMapLibre3d")
    return console_errors


def _activate_3d(page):
    mode = page.evaluate(ACTIVATE_3D)
    if mode != "3d":
        pytest.skip("3D renderer unavailable in this browser session")
    # Expose the live map so later evaluations can query the real renderer.
    page.evaluate("() => { window.__map3d = null; }")
    page.evaluate(
        """async () => { window.__map3d = await window.eqmonMapLibre3d.ensureMapLibre3d(); }"""
    )
    page.evaluate(WAIT_FOR_IDLE)


def _set_view(page, view):
    page.evaluate(
        "view => window.eqmonMapModes.setCamera({ ...view, bearing: 0, pitch: 55 })",
        view,
    )
    page.evaluate(WAIT_FOR_IDLE)


def test_terrain_has_real_relief_at_regional_and_district_scale(page, app_server, console_errors):
    """Phase 3: terrain visible at both scales, at true elevation."""
    _open(page, app_server, console_errors)
    _activate_3d(page)

    assert page.evaluate("() => window.eqmonMapLibre3d.hasTerrain()") is True
    assert page.evaluate("() => window.__map3d.getTerrain().exaggeration") == 1

    samples = {}
    for name, view in (("regional", REGIONAL_VIEW), ("district", DISTRICT_VIEW)):
        _set_view(page, view)
        # queryTerrainElevation returns metres above sea level for a lng/lat.
        samples[name] = page.evaluate(
            """center => {
                 const points = [
                   center,
                   [center[0] + 0.05, center[1] + 0.05],
                   [center[0] - 0.05, center[1] - 0.05],
                 ];
                 return points.map(p => window.__map3d.queryTerrainElevation(p));
               }""",
            view["center"],
        )

    for name, elevations in samples.items():
        readings = [e for e in elevations if e is not None]
        assert readings, f"{name}: terrain returned no elevation, so the DEM never loaded"
        # Real ground, not a flat plane and not a fantasy mountain range.
        assert max(readings) > 100, f"{name}: terrain is flat ({readings})"
        assert max(readings) < 9000, f"{name}: implausible relief ({readings})"

    district_peak = max(e for e in samples["district"] if e is not None)
    assert district_peak > 500, f"Muzaffarabad should be mountainous, got {district_peak} m"
    assert not console_errors, console_errors


CONTRAST = """
() => {
  // Chromium resolves color-mix() to `color(srgb r g b / a)` with 0-1 channels,
  // while rgb()/rgba() stay 0-255. Reading one as the other turns white into
  // near-black, so the notation decides the scale.
  const parse = value => {
    const parts = (value.match(/[\\d.]+/g) || []).map(Number);
    const scale = value.startsWith("color(") ? 255 : 1;
    return parts.slice(0, 3).map(c => c * scale);
  };
  const alphaOf = value => {
    const parts = (value.match(/[\\d.]+/g) || []).map(Number);
    return parts.length > 3 ? parts[3] : 1;
  };
  const channel = c => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  const luminance = rgb =>
    0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  // Walk up for the first painted background: buttons inherit a transparent one.
  const backgroundOf = node => {
    for (let el = node; el; el = el.parentElement) {
      const bg = getComputedStyle(el).backgroundColor;
      if (bg && bg !== "transparent" && alphaOf(bg) > 0.5) return parse(bg);
    }
    return [255, 255, 255];
  };
  const ratio = node => {
    const fg = parse(getComputedStyle(node).color);
    const bg = backgroundOf(node);
    const [light, dark] = [luminance(fg), luminance(bg)].sort((a, b) => b - a);
    return (light + 0.05) / (dark + 0.05);
  };
  const control = document.getElementById("map-mode-control");
  return {
    inactive: ratio(control.querySelector('[data-map-mode="3d"]')),
    active: ratio(control.querySelector('[data-map-mode="2d"]')),
  };
}
"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_map_chrome_stays_readable_in_both_themes(page, app_server, console_errors, theme):
    """Phase 3: light and dark themes preserve text and control contrast."""
    _open(page, app_server, console_errors)
    page.evaluate("mode => applyTheme(mode)", theme)
    page.wait_for_function("mode => document.documentElement.dataset.theme === mode", arg=theme)

    ratios = page.evaluate(CONTRAST)
    # WCAG AA for normal text. The toggle is the control an operator has to read
    # to know which renderer they are looking at.
    for state, ratio in ratios.items():
        assert ratio >= 4.5, f"{theme}/{state} contrast is {ratio:.2f}:1, below WCAG AA"
    assert not console_errors, console_errors


def test_mmi_bands_render_over_terrain_in_severity_order(page, app_server, console_errors):
    """Phase 4: published bands really draw in 3D, stronger over weaker."""
    _open(page, app_server, console_errors)
    _activate_3d(page)
    _set_view(page, DISTRICT_VIEW)

    page.evaluate(
        """features => window.eqmonMapModes.publish({
             currentMmi: { featureCollection: features, visible: true, opacity: 0.45,
                           selectedLevel: null, hoveredLevel: null },
           })""",
        MMI_FEATURES,
    )
    page.evaluate(WAIT_FOR_IDLE)

    rendered = page.evaluate(
        """() => window.__map3d
             .queryRenderedFeatures({ layers: ["current-mmi-fill"] })
             .map(f => f.properties.mmi_lower)"""
    )
    assert rendered, "MMI bands did not render in 3D"
    assert {5, 7} <= set(rendered), f"expected both bands, saw {sorted(set(rendered))}"

    # The stronger band must survive on top where the two overlap.
    centre = page.evaluate(
        """() => {
             const point = window.__map3d.project([73.47, 34.37]);
             return window.__map3d
               .queryRenderedFeatures(point, { layers: ["current-mmi-fill"] })
               .map(f => f.properties.mmi_lower);
           }"""
    )
    assert centre and centre[0] == 7, f"stronger band is not on top: {centre}"
    assert not console_errors, console_errors


def test_two_d_to_three_d_to_two_d_preserves_camera_and_analysis_state(page, app_server, console_errors):
    """Phase 9's round trip, run against two live renderers."""
    _open(page, app_server, console_errors)

    page.evaluate("view => window.eqmonMapModes.setCamera(view)", DISTRICT_VIEW)
    page.evaluate(
        """features => window.eqmonMapModes.publish({
             currentMmi: { featureCollection: features, visible: true, opacity: 0.45 },
             activeEvent: { lat: 34.37, lon: 73.47, magnitude: 6.2, epicenterLabel: "Epicenter — M6.2" },
           })""",
        MMI_FEATURES,
    )
    before = page.evaluate("() => ({ camera: window.eqmonMapModes.getCamera(), state: window.eqmonMapModes.getState() })")

    _activate_3d(page)
    # The 3D camera must describe the same ground, one zoom level apart.
    three_d = page.evaluate("() => window.eqmonMapLibre3d.getCamera()")
    assert three_d["zoom"] == pytest.approx(before["camera"]["zoom"] - 1, abs=0.01)
    assert three_d["center"][0] == pytest.approx(before["camera"]["center"][0], abs=1e-4)
    assert three_d["pitch"] == pytest.approx(55, abs=0.01)

    page.evaluate("async () => { await window.eqmonMapModes.setMode('2d'); }")
    after = page.evaluate("() => ({ camera: window.eqmonMapModes.getCamera(), state: window.eqmonMapModes.getState() })")

    assert after["camera"]["center"][0] == pytest.approx(before["camera"]["center"][0], abs=1e-4)
    assert after["camera"]["center"][1] == pytest.approx(before["camera"]["center"][1], abs=1e-4)
    assert after["camera"]["zoom"] == pytest.approx(before["camera"]["zoom"], abs=0.01)
    # Analysis state is republished, never refetched, so it comes back identical.
    assert after["state"]["currentMmi"]["featureCollection"] == before["state"]["currentMmi"]["featureCollection"]
    assert after["state"]["activeEvent"] == before["state"]["activeEvent"]
    assert not console_errors, console_errors


def test_reference_overlays_render_from_the_real_archives(page, app_server, console_errors):
    """Phase 5: every overlay in Layers reaches the 3D map, from real PMTiles."""
    _open(page, app_server, console_errors)
    _activate_3d(page)
    _set_view(page, REGIONAL_VIEW)

    configured = page.evaluate("() => Object.keys(window.eqmonMapModes.getState().overlays)")
    assert configured, "no overlays were published"

    registered = page.evaluate("() => window.eqmonMapLibre3d.overlayLayerIds()")
    for name in configured:
        overlay_id = page.evaluate("name => window.eqmonMapModes.getState().overlays[name].id", name)
        assert f"overlay-{overlay_id}-line" in registered, f"{name} has no 3D layer"

    # The three defaults must be the ones actually switched on.
    visible = page.evaluate(
        """() => window.__map3d.getStyle().layers
             .filter(l => l.id.startsWith("overlay-") && l.id.endsWith("-line"))
             .filter(l => (l.layout?.visibility ?? "visible") === "visible")
             .map(l => l.id)"""
    )
    assert set(visible) == {"overlay-national-line", "overlay-provinces-line", "overlay-pak_faults_major-line"}, visible

    # National boundaries really draw: the archive loaded and produced features.
    page.wait_for_function(
        """() => window.__map3d
             .queryRenderedFeatures({ layers: ["overlay-national-line"] }).length > 0""",
        timeout=20000,
    )
    assert not console_errors, console_errors


def test_toggling_an_overlay_edits_layers_without_accumulating_them(page, app_server, console_errors):
    """Phase 5: toggles flip visibility; they never rebuild sources or layers."""
    _open(page, app_server, console_errors)
    _activate_3d(page)

    def counts():
        return page.evaluate(
            """() => {
                 const style = window.__map3d.getStyle();
                 return {
                   layers: style.layers.filter(l => l.id.startsWith("overlay-")).length,
                   sources: Object.keys(style.sources).filter(id => id.startsWith("overlay-")).length,
                 };
               }"""
        )

    before = counts()
    # The real checkbox, clicked in the page: this exercises the whole
    # 2D -> published state -> 3D path. It is driven through the DOM rather than
    # the pointer because the Layers panel is collapsed, and what is under test
    # is the state path, not the sidebar.
    for _ in range(6):
        page.evaluate(
            """() => document
                 .querySelector('#overlay-list input[type="checkbox"][aria-label="Districts"]')
                 .click()"""
        )
        page.wait_for_timeout(60)

    assert counts() == before, "toggling changed the layer or source count"
    assert page.evaluate(
        """() => window.__map3d.getLayoutProperty("overlay-districts-line", "visibility")"""
    ) == "none"
    assert not console_errors, console_errors


BUILDINGS_CATALOG = [
    {"id": "Muzaffarabad_buildings", "label": "Muzaffarabad", "bounds": [73.2, 34.1, 73.8, 34.7]},
    {"id": "Karachi_buildings", "label": "Karachi", "bounds": [66.8, 24.7, 67.4, 25.1]},
]

PUBLISH_BUILDINGS = """
catalog => window.eqmonMapModes.publish({
  buildings: { enabled: true, selected: "", minZoom: 12, catalog,
               districts: [], opacity: 0.75, maxSources: 6 },
})
"""


def test_building_extrusions_follow_the_viewport_and_stay_under_the_hazard(page, app_server, console_errors):
    """Phase 6: extrusions live only where the camera is, and below the MMI fill.

    The district tiles themselves come from the TileServerGL proxy, which the
    suite does not run; the conftest fixture filters that one external failure,
    so the layer bookkeeping is still asserted exactly.
    """
    _open(page, app_server, console_errors)
    _activate_3d(page)
    _set_view(page, {"center": [73.47, 34.37], "zoom": 13})
    page.evaluate(PUBLISH_BUILDINGS, BUILDINGS_CATALOG)

    assert page.evaluate("() => window.eqmonMapLibre3d.liveBuildingDistricts()") == [
        "Muzaffarabad_buildings"
    ]

    layer = page.evaluate(
        """() => window.__map3d.getStyle().layers
             .find(l => l.id === "buildings-Muzaffarabad_buildings-extrusion")"""
    )
    assert layer["type"] == "fill-extrusion"
    order = page.evaluate("() => window.__map3d.getStyle().layers.map(l => l.id)")
    assert order.index("buildings-Muzaffarabad_buildings-extrusion") < order.index("current-mmi-fill")

    # Panning to the other end of the country evicts the district left behind.
    _set_view(page, {"center": [67.0, 24.9], "zoom": 13})
    page.wait_for_function(
        """() => window.eqmonMapLibre3d.liveBuildingDistricts()
             .join() === "Karachi_buildings\"""",
        timeout=10000,
    )
    assert page.evaluate(
        """() => window.__map3d.getStyle().layers
             .some(l => l.id === "buildings-Muzaffarabad_buildings-extrusion")"""
    ) is False

    # Zooming out past the catalog minimum takes every source down with it.
    _set_view(page, REGIONAL_VIEW)
    page.wait_for_function(
        "() => window.eqmonMapLibre3d.liveBuildingDistricts().length === 0",
        timeout=10000,
    )
    assert not console_errors, console_errors


def test_open_basemaps_switch_between_raster_vector_and_labelled_satellite(page, app_server, console_errors):
    """Every basemap is keyless: raster tiles, a vector style, and imagery+labels."""
    _open(page, app_server, console_errors)
    _activate_3d(page)
    _set_view(page, DISTRICT_VIEW)

    def switch(name):
        page.evaluate("name => window.eqmonMapModes.publish({ basemap: name })", name)
        page.wait_for_function("name => window.eqmonMapLibre3d.getBasemap() === name", arg=name)
        page.evaluate(WAIT_FOR_IDLE)
        return page.evaluate("() => window.__map3d.getStyle().layers.map(l => l.id)")

    raster = switch("OpenStreetMap")
    assert raster[0] == "basemap"

    vector = switch("Dark")
    # A vector style brings its own layers; ours are registered again on top.
    assert "basemap" not in vector
    assert "current-mmi-fill" in vector and "terrain-hillshade" in vector

    hybrid = switch("Satellite + labels")
    assert hybrid[0] == "basemap"
    labels = page.evaluate(
        """() => window.__map3d.getStyle().layers
             .filter(l => l.type === "symbol" && !l.id.startsWith("overlay-")).length"""
    )
    assert labels > 0, "labelled satellite drew no labels"
    # Imagery is the map: no fill from the label style may cover it.
    assert page.evaluate(
        """() => window.__map3d.getStyle().layers
             .some(l => l.type === "background" || (l.type === "fill" && !l.id.startsWith("overlay-")
                        && !l.id.startsWith("current-mmi")))"""
    ) is False
    assert not console_errors, console_errors


@pytest.mark.parametrize("viewport", [
    {"width": 1440, "height": 900},
    {"width": 1024, "height": 768},
    {"width": 430, "height": 800},
])
def test_mode_control_is_named_reachable_and_unobscured(page, app_server, console_errors, viewport):
    """Phase 8: the primary mode control remains operable across target layouts."""
    _open(page, app_server, console_errors)
    page.set_viewport_size(viewport)
    control = page.locator("#map-mode-control")
    box = control.bounding_box()
    assert box is not None
    assert box["x"] >= 0 and box["y"] >= 52
    assert box["x"] + box["width"] <= viewport["width"]
    assert box["y"] + box["height"] <= viewport["height"]
    assert control.get_attribute("aria-label") == "Map view mode"
    for mode in ("2d", "3d"):
        button = control.locator(f'[data-map-mode="{mode}"]')
        button_box = button.bounding_box()
        assert button_box["width"] >= 44 and button_box["height"] >= 44


def test_full_screen_suspension_restores_the_active_renderer(page, app_server, console_errors):
    """Phase 8: full-screen views suspend and restore whichever renderer is active."""
    _open(page, app_server, console_errors)
    _activate_3d(page)
    page.evaluate("() => window.eqmonMapModes.setSuspended(true)")
    assert page.locator("#map-3d").evaluate("el => getComputedStyle(el).display") == "none"
    assert page.locator("#map-mode-control").is_hidden()
    page.evaluate("() => window.eqmonMapModes.setSuspended(false)")
    assert page.locator("#map-mode-control").is_visible()
    assert page.evaluate("() => window.eqmonMapModes.getMode()") == "3d"
    assert page.locator("#map-3d").evaluate("el => getComputedStyle(el).display") != "none"


def test_mobile_three_d_resets_bearing_and_reduced_motion_disables_fades(page, app_server, console_errors):
    """Phase 8: phone entry is north-up and reduced-motion mode has no renderer fade."""
    page.emulate_media(reduced_motion="reduce")
    _open(page, app_server, console_errors)
    page.set_viewport_size({"width": 430, "height": 800})
    page.evaluate(
        "() => window.eqmonMapModes.setCamera({ center: [73.47, 34.37], zoom: 11, bearing: 80, pitch: 55 })"
    )
    _activate_3d(page)
    assert page.evaluate("() => window.__map3d.getBearing()") == pytest.approx(0, abs=0.01)
    durations = page.evaluate(
        """() => ["map", "map-3d"].map(id => getComputedStyle(document.getElementById(id)).transitionDuration)"""
    )
    assert all(max(float(part.removesuffix("s")) for part in value.split(", ")) <= 0.001 for value in durations)


def test_webgl_context_loss_returns_to_usable_two_d(page, app_server, console_errors):
    """Phase 9: context loss falls back without reloading the application."""
    _open(page, app_server, console_errors)
    _activate_3d(page)
    page.evaluate(
        """() => window.__map3d.getCanvas().dispatchEvent(new Event("webglcontextlost", { cancelable: true }))"""
    )
    page.wait_for_function("() => window.eqmonMapModes.getMode() === '2d'")
    assert page.locator('#map-mode-control [data-map-mode="2d"]').get_attribute("aria-pressed") == "true"
    assert page.locator("#map").evaluate("el => getComputedStyle(el).pointerEvents") != "none"


def test_hidden_three_d_renderer_is_paused_and_resumed(page, app_server, console_errors):
    """Phase 9: inactive WebGL does not keep a render loop alive."""
    _open(page, app_server, console_errors)
    _activate_3d(page)
    assert page.evaluate("() => window.eqmonMapLibre3d.isPaused()") is False
    page.evaluate("() => window.eqmonMapModes.setMode('2d')")
    assert page.evaluate("() => window.eqmonMapLibre3d.isPaused()") is True
    page.evaluate("() => window.eqmonMapModes.setMode('3d')")
    page.wait_for_function("() => window.eqmonMapModes.getMode() === '3d'")
    assert page.evaluate("() => window.eqmonMapLibre3d.isPaused()") is False
