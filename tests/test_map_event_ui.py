from pathlib import Path
import re


INDEX = Path("web/index.html").read_text(encoding="utf-8")
APP = Path("web/app.js").read_text(encoding="utf-8")


def test_earthquake_map_exposes_time_and_display_controls():
    for control_id in (
        "map-time-start",
        "map-time-end",
        "map-time-reset",
        "map-date-from",
        "map-date-to",
        "map-bubble-opacity",
        "map-plates-toggle",
    ):
        assert f'id="{control_id}"' in INDEX


def test_bubble_popup_includes_requested_event_fields():
    for label in ("Date", "Time", "Latitude", "Longitude", "Magnitude", "Depth"):
        assert f"<dt>{label}</dt>" in APP
    assert "event.depth_km" in APP
    assert "event.occurred_at" in APP


def test_plate_annotations_use_baked_plate_assets():
    assert 'url: "/tiles/plates.pmtiles"' in APP
    assert 'dataLayer: "plates"' in APP
    assert 'buildOverlay("Plate boundaries")' in APP
    assert "CenteredTextSymbolizer" in APP


def test_time_slider_filters_loaded_events_without_refetching():
    assert "function _filteredMapEvents()" in APP
    assert "function _renderMapEvents" in APP
    assert "_mapEventState.startIndex" in APP
    assert "_mapEventState.endIndex" in APP


def test_calendar_range_is_sent_to_catalog_api():
    assert 'common.set("occurred_after", dateFrom + "T00:00:00Z")' in APP
    assert 'common.set("occurred_before", dateTo + "T23:59:59.999Z")' in APP
    assert 'params.set("source", source)' in APP


def test_assistant_trigger_mounts_the_lottie_asset():
    lottie = re.search(r'<dotlottie-wc src="/chatbot\.lottie\?v=[^"]+"[^>]*>', INDEX)
    assert lottie
    assert "autoplay" not in lottie.group(0)
    assert "@lottiefiles/dotlottie-wc@0.8.1" in INDEX
