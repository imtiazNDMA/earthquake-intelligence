from pathlib import Path
import re


INDEX = Path("web/index.html").read_text(encoding="utf-8")
LANDSLIDES = Path("web/landslides.js").read_text(encoding="utf-8")


def test_mutable_frontend_assets_are_revisioned():
    """HTML and local assets must not drift across browser cache versions."""
    for asset in ("styles.css", "app.js", "landslides.js", "buildings.js"):
        assert re.search(rf'["\']{re.escape(asset)}\?v=[^"\']+["\']', INDEX), (
            f"{asset} needs a cache-busting revision in web/index.html"
        )


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
