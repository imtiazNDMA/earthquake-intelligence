"""Analysis adapters: analytics, aftershock, and place resolution.

Each domain service returns a payload sized for a dashboard — a 1000-point
depth scatter, a full frequency-magnitude histogram, a probability row per
day-magnitude pair. The adapters exist to cut those down to the figures a model
can actually reason about, and to keep the fitted model parameters out of reach
so it cannot present `k`, `c`, and `p` as findings.
"""
import os
from datetime import datetime, timezone

import pytest

from eqmon.ai.contracts import MAX_ZONES_IN_CONTEXT, ToolFailure
from eqmon.ai.tools.analysis import (get_aftershock_summary,
                                     get_catalog_analytics)
from eqmon.ai.tools.places import resolve_place

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def _seed(conn, count: int = 120):
    for i in range(count):
        mag = 3.0 + (i % 20) * 0.1
        conn.execute(
            "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude,"
            " depth_km, geom, is_canonical, is_mainshock) VALUES ('USGS', %s, %s, %s, 20,"
            " ST_SetSRID(ST_MakePoint(72,34),4326), TRUE, TRUE)",
            (f"a{i}", datetime(2026, 1, 1, tzinfo=timezone.utc), mag))


# --- catalog analytics -----------------------------------------------------

def test_analytics_projection_drops_the_plotting_arrays(db_conn):
    """`grid`, `fmd`, `rate`, and the depth scatter exist to be drawn, not
    reasoned about. Sending them spends the context window on noise."""
    _seed(db_conn)
    payload = get_catalog_analytics(db_conn, window="all").model_dump_json()
    for plotting_only in ("scatter", "incremental", "cumulative", "grid"):
        assert plotting_only not in payload


def test_analytics_keeps_the_headline_figures(db_conn):
    _seed(db_conn)
    result = get_catalog_analytics(db_conn, window="all")
    assert result.mc is not None
    assert result.n_used > 0
    assert result.total_rate_per_year >= 0


def test_analytics_caps_the_zone_rollup(db_conn):
    _seed(db_conn)
    result = get_catalog_analytics(db_conn, window="all")
    assert len(result.top_zones) <= MAX_ZONES_IN_CONTEXT


def test_analytics_empty_catalog_is_a_typed_failure(db_conn):
    with pytest.raises(ToolFailure) as failure:
        get_catalog_analytics(db_conn, window="all")
    assert failure.value.code == "not_found"


def test_analytics_bad_window_is_a_typed_failure(db_conn):
    _seed(db_conn)
    with pytest.raises(ToolFailure) as failure:
        get_catalog_analytics(db_conn, window="nope")
    assert failure.value.code == "invalid_request"


# --- aftershock ------------------------------------------------------------

def test_aftershock_summary_returns_probabilities(db_conn):
    result = get_aftershock_summary(db_conn, magnitude=6.5, lat=34.0, lon=72.0)
    assert result.region
    assert result.forecast
    assert all(0.0 <= row.probability_pct <= 100.0 for row in result.forecast)


def test_aftershock_summary_hides_the_fitted_parameters(db_conn):
    """`k`, `c`, `p`, `alpha` are calibration internals. A model that can see
    them can present them as findings, and they are not claims."""
    payload = get_aftershock_summary(db_conn, magnitude=6.5, lat=34.0,
                                     lon=72.0).model_dump_json()
    for internal in ("productivity_scale", "Mref", "alpha"):
        assert internal not in payload


def test_aftershock_summary_without_event_or_coordinates_is_rejected(db_conn):
    with pytest.raises(ToolFailure) as failure:
        get_aftershock_summary(db_conn)
    assert failure.value.code == "invalid_request"


def test_aftershock_summary_for_a_missing_event_is_typed(db_conn):
    with pytest.raises(ToolFailure) as failure:
        get_aftershock_summary(db_conn, event_id=999_999)
    assert failure.value.code == "not_found"


# --- place resolution ------------------------------------------------------

def test_resolve_place_reports_not_found_without_guessing(db_conn):
    result = resolve_place(db_conn, "Nowhereistan")
    assert result.status == "not_found"
    assert result.match is None


def test_resolve_place_keys_candidates_by_boundary_id(db_conn):
    """Duplicate administrative names are real. A candidate identified only by
    name cannot be disambiguated later."""
    db_conn.execute(
        "INSERT INTO admin_boundary (name, level, parent, geom) VALUES"
        " ('Zhob', 'district', 'Balochistan',"
        " ST_Multi(ST_GeomFromText('POLYGON((69 31, 70 31, 70 32, 69 32, 69 31))', 4326)))")
    result = resolve_place(db_conn, "Zhob")
    assert result.status == "resolved"
    assert result.match.unit_id > 0
