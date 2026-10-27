"""Catalog analytics as a service, callable without the API.

The orchestration used to live inside the `/analytics` handler, which made it
reachable only over HTTP. A tool adapter needs the same computation with no
request in flight, so the sequencing — estimate Mc from the full slice, then
apply the magnitude floor — belongs in a service that takes a connection like
every other domain function here.
"""
import os
from datetime import datetime, timezone

import pytest

from eqmon.analytics_service import EmptyCatalogError, compute_analytics

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
            (f"e{i}", datetime(2026, 1, 1, tzinfo=timezone.utc), mag))


def test_compute_analytics_returns_the_documented_sections(db_conn):
    _seed(db_conn)
    result = compute_analytics(db_conn, window="all", min_mag="mc")
    assert set(result) >= {"provenance", "kpis", "grid", "fmd", "depth", "rate",
                           "zones"}
    assert result["kpis"]["mc"] is not None
    assert result["provenance"]["n_used"] > 0


def test_empty_catalog_is_a_typed_failure(db_conn):
    """No anchor time means no window to compute over. The API turns this into
    a 404; the service must not invent an anchor."""
    with pytest.raises(EmptyCatalogError):
        compute_analytics(db_conn, window="all")


def test_unparseable_window_is_rejected(db_conn):
    _seed(db_conn)
    with pytest.raises(ValueError):
        compute_analytics(db_conn, window="nope")


def test_unparseable_min_mag_is_rejected(db_conn):
    _seed(db_conn)
    with pytest.raises(ValueError):
        compute_analytics(db_conn, window="all", min_mag="loud")


def test_bad_bbox_is_rejected(db_conn):
    _seed(db_conn)
    with pytest.raises(ValueError):
        compute_analytics(db_conn, window="all", bbox="1,2,3")


def test_explicit_magnitude_floor_excludes_smaller_events(db_conn):
    """The floor is applied after Mc is estimated from the full slice, so the
    excluded count is observable in provenance."""
    _seed(db_conn)
    result = compute_analytics(db_conn, window="all", min_mag="4.5")
    assert result["provenance"]["n_excluded"] > 0
    assert result["kpis"]["largest"]["magnitude"] >= 4.5
