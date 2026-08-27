from pathlib import Path


INDEX = Path("web/index.html").read_text(encoding="utf-8")
APP = Path("web/app.js").read_text(encoding="utf-8")
STYLES = Path("web/styles.css").read_text(encoding="utf-8")


def test_aftershock_panel_does_not_duplicate_start_inputs():
    for old_control in (
        "as-source",
        "as-manual-row",
        "as-mag",
        "as-depth",
        "as-lat",
        "as-lon",
    ):
        assert f'id="{old_control}"' not in INDEX


def test_aftershock_panel_exposes_current_event_and_catalog_fallback():
    for control in (
        "as-event-card",
        "as-event-mag",
        "as-event-place",
        "as-event-meta",
        "as-catalog-picker",
        "as-event-id",
        "as-use-current",
    ):
        assert f'id="{control}"' in INDEX


def test_aftershock_forecast_reads_start_values_as_its_default():
    assert "function _asStartEvent()" in APP
    for start_input in ("magnitude", "depth_km", "lat", "lon"):
        assert f'document.getElementById("{start_input}")?.valueAsNumber' in APP
    assert 'return _currentEvent && !_currentEvent._fromStart ? _currentEvent : _asStartEvent();' in APP


def test_aftershock_request_uses_coordinates_until_an_event_has_an_id():
    assert "? { event_id: eventId }" in APP
    assert ": { magnitude: mag, lat, lon };" in APP


def test_expanded_forecast_is_decision_first_and_theme_aware():
    assert 'id="as-expanded-content"' in INDEX
    assert 'id="as-expanded-chart"' not in INDEX
    for view in ("Summary", "Commentary", "Forecast table", "Model parameters"):
        assert f'>{view}</button>' in APP
    assert "function _asRenderExpandedGauge()" in APP
    assert "On day <b>" in APP
    assert ".as-gauge-value" in STYLES
    assert "stroke: var(--alert)" in STYLES


def test_expanded_forecast_keeps_the_model_per_day_semantics():
    assert "on that specific day after the mainshock" in APP
    assert "over the next month" not in APP.lower()


def test_sidebar_forecast_is_a_compact_readout_not_a_squeezed_chart():
    for control in ("as-result-card", "as-open-forecast", "as-export"):
        assert f'id="{control}"' in INDEX
    for removed in ("as-chart", "as-chart-wrap", "as-table-wrap", "as-summary"):
        assert f'id="{removed}"' not in INDEX
    assert "as-result-primary" in APP
    assert "as-result-checkpoints" in APP
    assert "document.getElementById(\"as-open-forecast\").onclick = _asShowExpanded" in APP


def test_expanded_gauge_animates_without_the_redundant_readiness_banner():
    assert "Be ready for more earthquakes" not in APP
    assert 'id="as-gauge-marker"' not in APP
    assert "anime.animate(state" in APP
    assert ".as-gauge-track, .as-gauge-value { fill: none; stroke-width: 24; stroke-linecap: butt; }" in STYLES
    assert "const settle" not in APP
    assert "requestAnimationFrame(tick)" in APP
    assert "output.dataset.value" in APP
    assert 'prefers-reduced-motion: reduce' in APP
    assert "if (reduceMotion)" in APP
