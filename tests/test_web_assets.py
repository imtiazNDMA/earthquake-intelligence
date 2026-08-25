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
    assert 'type: "raster"' in renderer
    assert 'tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"]' in renderer
    assert "maxzoom: 19" in renderer
    assert "https://www.openstreetmap.org/copyright" in renderer
    assert "ensureMapLibre3d" in coordinator
    assert "maplibre-gl@" not in INDEX


def test_map_mode_coordinator_persists_success_and_falls_back_to_2d():
    coordinator = Path("web/map-modes.js").read_text(encoding="utf-8")
    assert 'localStorage.getItem("eqmon-map-mode")' in coordinator
    assert 'localStorage.setItem("eqmon-map-mode", mode)' in coordinator
    assert 'getContext("webgl2")' in coordinator
    assert 'setMode("2d"' in coordinator
    assert 'toast("3D map unavailable' in coordinator
    assert "MutationObserver" in coordinator
