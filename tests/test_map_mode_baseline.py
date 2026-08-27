import json
from pathlib import Path


BASELINE = json.loads(
    Path("tests/fixtures/map_mode_baseline.json").read_text(encoding="utf-8")
)


def test_map_mode_baseline_uses_normalized_camera_order():
    assert BASELINE["camera"] == {
        "center": [69.3, 30.4],
        "zoom": 5,
        "bearing": 0,
        "pitch": 0,
    }


def test_map_mode_baseline_preserves_operational_layer_order():
    panes = {pane["name"]: pane["z_index"] for pane in BASELINE["pane_order"]}
    assert list(panes.values()) == sorted(panes.values())
    assert panes["buildingsPane"] < panes["overlayPane"] < panes["eventPane"]
    assert BASELINE["visible_reference_overlays"] == [
        "National",
        "Provinces",
        "National Faults",
    ]


def test_map_mode_baseline_records_initial_event_and_layer_defaults():
    assert BASELINE["active_event"]["initial"] is None
    assert BASELINE["active_event"]["event_name"] == "eqmon:current-event"
    assert BASELINE["current_mmi_visible"] is True
    assert BASELINE["buildings"]["enabled"] is True
    assert BASELINE["landslide_regions"] == []
    assert BASELINE["pga_enabled"] is False
