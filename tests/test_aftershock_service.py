"""Aftershock forecasting as a service, callable without the API.

`aftershock.py` holds the seismology (Omori-Utsu, Gutenberg-Richter) and is
already well covered. What lived only in the HTTP handler was the *orchestration
around* it: resolve an event or inline coordinates, look up the tectonic zone,
fall back to latitude bands when there is no zone. A tool adapter needs exactly
that sequence, so it moves here.
"""
import os
from datetime import datetime, timezone

import pytest

from eqmon.aftershock_service import EventNotFoundError, compute_forecast

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)

# A square covering the point used throughout these tests.
_ZONE_WKT = "MULTIPOLYGON(((70 32, 74 32, 74 36, 70 36, 70 32)))"


def _seed_zone(conn, name: str = "Chaman Fault Zone"):
    conn.execute(
        "INSERT INTO tectonic_zone (name, geom) VALUES (%s, ST_GeomFromText(%s, 4326))",
        (name, _ZONE_WKT))


def _seed_event(conn, magnitude: float = 6.2) -> int:
    row = conn.execute(
        "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude,"
        " depth_km, geom, is_canonical, is_mainshock) VALUES ('USGS', 'as1', %s, %s, 15,"
        " ST_SetSRID(ST_MakePoint(72,34),4326), TRUE, TRUE) RETURNING id",
        (datetime(2026, 3, 1, tzinfo=timezone.utc), magnitude)).fetchone()
    return row[0]


def test_inline_coordinates_produce_a_forecast(db_conn):
    result = compute_forecast(db_conn, magnitude=6.5, lat=34.0, lon=72.0)
    assert result["event"] is None
    assert result["region"]


def test_event_id_resolves_magnitude_and_location_from_the_catalog(db_conn):
    event_id = _seed_event(db_conn, magnitude=6.2)
    result = compute_forecast(db_conn, event_id=event_id)
    assert result["event"]["id"] == event_id
    assert result["event"]["magnitude"] == 6.2


def test_missing_event_is_a_typed_failure(db_conn):
    with pytest.raises(EventNotFoundError):
        compute_forecast(db_conn, event_id=999_999)


def test_neither_event_nor_coordinates_is_rejected(db_conn):
    with pytest.raises(ValueError, match="event_id or magnitude"):
        compute_forecast(db_conn)


def test_zone_name_drives_region_when_the_point_falls_in_a_zone(db_conn):
    _seed_zone(db_conn)
    result = compute_forecast(db_conn, magnitude=6.0, lat=34.0, lon=72.0)
    assert result["zone_name"] == "Chaman Fault Zone"


def test_point_outside_every_zone_falls_back_to_latitude_bands(db_conn):
    _seed_zone(db_conn)
    result = compute_forecast(db_conn, magnitude=6.0, lat=24.0, lon=66.0)
    assert "zone_name" not in result
    assert result["region"]


def test_zone_lookup_failure_does_not_poison_the_caller_transaction(db_conn):
    """The lookup is best-effort — a missing or broken zone table must degrade
    to the latitude-band heuristic, and must not abort the surrounding
    transaction the caller is still using."""
    db_conn.execute("DROP TABLE tectonic_zone CASCADE")

    result = compute_forecast(db_conn, magnitude=6.0, lat=34.0, lon=72.0)
    assert result["region"]
    assert "zone_name" not in result

    # The connection is still usable: the failed lookup was contained.
    assert db_conn.execute("SELECT 1").fetchone()[0] == 1
