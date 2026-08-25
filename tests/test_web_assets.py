from pathlib import Path
import re


INDEX = Path("web/index.html").read_text(encoding="utf-8")
LANDSLIDES = Path("web/landslides.js").read_text(encoding="utf-8")


def test_mutable_frontend_assets_are_revisioned():
    """HTML and local assets must not drift across browser cache versions."""
    for asset in (
        "styles.css",
        "app.js",
        "landslides.js",
        "buildings.js",
        "maplibre-3d.js",
        "map-modes.js",
    ):
        assert re.search(rf'["\']{re.escape(asset)}\?v=[^"\']+["\']', INDEX), (
            f"{asset} needs a cache-busting revision in web/index.html"
        )
    assert re.search(r'src="/chatbot\.lottie\?v=[^"]+"', INDEX)


def test_landslide_layers_have_a_dedicated_rail_destination():
    forecast = INDEX.index('data-section="aftershock"')
    landslide = INDEX.index('data-section="landslide"')
    infra = INDEX.index('data-section="infra"')
    assert forecast < landslide < infra
    assert 'id="sec-landslide"' in INDEX
    assert 'id="landslide-layer-list"' in INDEX
    assert 'id="cfg-landslide-group"' not in INDEX


def test_landslide_regions_are_independently_toggleable_and_lazy():
    assert "state.manifest.regions.forEach" in LANDSLIDES
    assert 'input.dataset.region = region.key' in LANDSLIDES
    assert "ensureRegionLayer(region).addTo(map)" in LANDSLIDES
    assert "state.layers.set(region.key, layer)" in LANDSLIDES
    assert "L.layerGroup" not in LANDSLIDES


def test_building_legend_is_compact_and_height_specific():
    buildings = Path("web/buildings.js").read_text(encoding="utf-8")
    assert "Building height bands" in buildings
    assert "bld-zoom-badge" in buildings
    assert "Banded by building height" not in buildings
    assert "currently ${map.getZoom()}" not in buildings


def test_map_mode_control_has_stable_containers_and_native_buttons():
    assert INDEX.count('id="map"') == 1
    assert INDEX.count('id="map-3d"') == 1
    assert 'id="map-mode-control"' in INDEX
    assert 'role="group" aria-label="Map view"' in INDEX
    assert re.search(
        r'<button[^>]+data-map-mode="2d"[^>]+aria-pressed="true"', INDEX
    )
    assert re.search(
        r'<button[^>]+data-map-mode="3d"[^>]+aria-pressed="false"', INDEX
    )


def test_maplibre_renderer_is_exactly_pinned_and_lazy():
    renderer = Path("web/maplibre-3d.js").read_text(encoding="utf-8")
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    assert "maplibre-gl@5.7.1" in renderer
    assert (
        "sha384-gLKaKK6bcaV7wXNta/DHnECgiF2+mF15OXviE93B/+Q4CI68+ivYMRY4utfeUOTN"
        in renderer
    )
    assert (
        "sha384-gNYNsUmuZqDYiT3gbirWTV5K7rt71RoveS/yXAaU09d4ZUmeDVTD3XoqB6uJAIFR"
        in renderer
    )
    assert 'pmtiles.Protocol' in renderer
    assert 'maplibregl.addProtocol("pmtiles"' in renderer
    assert "let mapInstance = null" in renderer
    assert "let initializationPromise = null" in renderer
    assert "if (initializationPromise) return initializationPromise" in renderer
    assert "if (mapInstance)" in renderer
    assert "new maplibregl.Map" in renderer
    # Phase 3 moved the basemap definitions out of the renderer; it now builds
    # its raster source from the same catalogue the 2D map reads.
    assert 'type: "raster"' in renderer
    assert "config.maplibreSource(basemapName)" in renderer
    config = Path("web/map-style-config.js").read_text(encoding="utf-8")
    assert "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" in config
    assert "maxZoom: 19" in config
    assert "© OpenStreetMap contributors" in config
    assert "ensureMapLibre3d" in coordinator
    assert "maplibre-gl@" not in INDEX


def test_map_mode_coordinator_persists_success_and_falls_back_to_2d():
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    assert 'STORAGE_KEY = "eqmon-map-mode"' in coordinator
    assert "localStorage.getItem(STORAGE_KEY)" in coordinator
    assert "localStorage.setItem(STORAGE_KEY, mode)" in coordinator
    assert "localStorage.removeItem(STORAGE_KEY)" in coordinator
    assert 'getContext("webgl2")' in coordinator
    assert 'setMode("2d"' in coordinator
    assert 'toast("3D map unavailable' in coordinator
    assert "MutationObserver" in coordinator


def test_map_mode_coordinator_owns_normalized_camera_and_shared_state():
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    renderer = Path("web/maplibre-3d.js").read_text(encoding="utf-8")
    assert "center: [69.3, 30.4]" in coordinator
    assert "bearing: 0" in coordinator
    assert "pitch: 0" in coordinator
    assert "function readLeafletCamera" in coordinator
    assert "function applyLeafletCamera" in coordinator
    assert "function leafletZoomToMapLibre" in coordinator
    assert "function mapLibreZoomToLeaflet" in coordinator
    assert 'map.on("moveend", captureLeafletCamera)' in coordinator
    assert 'onCameraChange' in renderer
    assert "setCamera" in renderer
    assert "synchronizingCamera" in coordinator
    assert "JSON.parse(JSON.stringify" in coordinator


def test_shared_analysis_state_covers_phase_two_contract_without_renderer_objects():
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    for key in (
        "activeEvent",
        "currentMmi",
        "mapEvents",
        "basemap",
        "overlays",
        "landslides",
        "pga",
        "buildings",
        "theme",
        "alertLevel",
    ):
        assert f"{key}:" in coordinator
    assert "publishState" in coordinator
    assert "getState" in coordinator
    assert "Leaflet" not in coordinator.split("const sharedState", 1)[1].split("};", 1)[0]


def test_mode_switching_does_not_refetch_analysis_and_resize_is_centralized():
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    for endpoint in ("/intensity", "/events", "/impact", "/aftershock"):
        assert endpoint not in coordinator
    assert "function resize" in coordinator
    assert "map.invalidateSize()" in coordinator
    assert "eqmonMapLibre3d.resize()" in coordinator


def test_basemap_catalogue_is_shared_and_loads_before_the_2d_map():
    config = Path("web/map-style-config.js").read_text(encoding="utf-8")
    app = Path("web/app.js").read_text(encoding="utf-8")
    # One catalogue, read by both renderers.
    assert "window.eqmonMapStyleConfig" in config
    assert "MAP_STYLE_CONFIG.BASEMAP_DEFS.map" in app
    assert "MAP_STYLE_CONFIG.leafletOptions(def)" in app
    assert "MAP_STYLE_CONFIG.themeBasemap(mode)" in app
    # No catalogue URL may be written twice. (The Insights hotspot mini-map has
    # its own basemap and is explicitly out of scope for the dual renderer.)
    assert "server.arcgisonline.com" not in app
    assert "tile.openstreetmap.org" not in app
    assert "tile.opentopomap.org" not in app
    # The catalogue has to exist before app.js builds Leaflet layers from it.
    assert INDEX.index("map-style-config.js") < INDEX.index('src="app.js')


def test_three_d_style_adds_terrain_hillshade_and_keeps_gestures_scrollable():
    renderer = Path("web/maplibre-3d.js").read_text(encoding="utf-8")
    config = Path("web/map-style-config.js").read_text(encoding="utf-8")
    # DG-1 terrain at true scale, with a bounded wait and a flat fallback.
    assert 'encoding: "terrarium"' in config
    assert "exaggeration: 1.0" in config
    assert "timeoutMs" in config
    assert "registry.opendata.aws/terrain-tiles" in config
    assert 'type: "raster-dem"' in renderer
    assert "mapInstance.setTerrain({ source: DEM_SOURCE" in renderer
    assert "function dropTerrain" in renderer
    assert 'toast("Terrain unavailable' in renderer
    assert "terrainAnnounced" in renderer
    # Subtle relief, plus a horizon that does not touch the hazard palette.
    assert '"hillshade-exaggeration": 0.25' in renderer
    assert "function skyFor" in renderer
    assert "sky: skyFor(" in renderer
    assert "mapInstance.setSky(skyFor(state.theme))" in renderer
    # Touch drag stays a pan; compass and pitch reset stay available.
    assert "touchPitch: false" in renderer
    assert "touchZoomRotate?.disableRotation()" in renderer
    assert "NavigationControl({ visualizePitch: true, showCompass: true })" in renderer
    # The DEM is declared once and feeds both terrain and hillshade, so its
    # credit is printed once next to the basemap's.
    assert renderer.count("type: \"raster-dem\"") == 1
    assert renderer.count("attribution: terrain.attribution") == 1


def test_three_d_reapplies_basemap_and_theme_on_mode_change():
    renderer = Path("web/maplibre-3d.js").read_text(encoding="utf-8")
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    styles = Path("web/styles.css").read_text(encoding="utf-8")
    assert "function applyState" in renderer
    assert "function initialBasemapName" in renderer
    assert "styleConfig().themeBasemap(state.theme)" in renderer
    assert "eqmonMapLibre3d.applyState(snapshot)" in coordinator
    assert "eqmonMapLibre3d.applyState(getState())" in coordinator
    # The 3D controls need the same chrome offsets Leaflet's already get.
    assert "body.has-ladder .maplibregl-ctrl-top-right" in styles
    assert "body.has-strip .maplibregl-ctrl-bottom-right" in styles
