import os
from datetime import datetime, timezone

import pytest

from eqmon.events.repo import (catalog_coverage, create_manual_event, delete_event,
                               get_event, list_events, update_event,
                               update_usgs_detail)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_update_usgs_detail_stores_and_returns(db_conn):
    ev = create_manual_event(db_conn, magnitude=5.5, depth_km=10,
                             lon=72.5, lat=34.0, occurred_at=T0)
    detail = {"type": "Feature", "id": "test",
              "properties": {"mag": 5.5, "products": {}}}
    updated = update_usgs_detail(db_conn, ev["id"], detail)
    assert updated is not None
    assert updated["usgs_detail"] == detail


def test_get_event_includes_usgs_detail(db_conn):
    ev = create_manual_event(db_conn, magnitude=5.5, depth_km=10,
                             lon=72.5, lat=34.0, occurred_at=T0)
    detail = {"foo": "bar"}
    update_usgs_detail(db_conn, ev["id"], detail)
    fetched = get_event(db_conn, ev["id"])
    assert fetched is not None
    assert fetched["usgs_detail"] == detail


def test_delete_event_removes_and_returns_true(db_conn):
    ev = create_manual_event(db_conn, magnitude=5.0, depth_km=10,
                             lon=72.5, lat=34.0, occurred_at=T0)
    assert delete_event(db_conn, ev["id"]) is True
    assert get_event(db_conn, ev["id"]) is None


def test_delete_event_returns_false_for_missing(db_conn):
    assert delete_event(db_conn, 99999) is False


def test_update_event_updates_magnitude_and_place(db_conn):
    ev = create_manual_event(db_conn, magnitude=5.0, depth_km=10,
                             lon=72.5, lat=34.0, occurred_at=T0)
    updated = update_event(db_conn, ev["id"], magnitude=6.0,
                           place="near test")
    assert updated["magnitude"] == 6.0
    assert updated["place"] == "near test"
    assert updated["id"] == ev["id"]


def test_update_event_no_changes_returns_event(db_conn):
    ev = create_manual_event(db_conn, magnitude=5.0, depth_km=10,
                             lon=72.5, lat=34.0, occurred_at=T0)
    updated = update_event(db_conn, ev["id"])
    assert updated is not None
    assert updated["id"] == ev["id"]


def _insert(conn, sid, mag, lon, lat, when):
    conn.execute(
        "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude, "
        "depth_km, geom, is_canonical, is_mainshock) VALUES "
        "('USGS', %s, %s, %s, 10, ST_SetSRID(ST_MakePoint(%s,%s),4326), TRUE, TRUE)",
        (sid, when, mag, lon, lat))


def test_analytics_rows_filters_mag_and_gate(db_conn):
    from eqmon.events.repo import analytics_rows
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _insert(db_conn, "a", 5.0, 72.0, 34.0, t)
    _insert(db_conn, "b", 2.0, 72.0, 34.0, t)   # below min_mag
    _insert(db_conn, "c", 317.0, 72.0, 34.0, t)  # quality-gated out
    rows = analytics_rows(db_conn, datetime(2025, 1, 1, tzinfo=timezone.utc),
                          datetime(2027, 1, 1, tzinfo=timezone.utc), min_mag=3.0)
    mags = {r["magnitude"] for r in rows}
    assert 5.0 in mags and 2.0 not in mags and 317.0 not in mags


def test_list_events_filters_by_radius_and_event_kind(db_conn):
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _insert(db_conn, "near-main", 5.0, 66.90, 30.20, t)
    _insert(db_conn, "far-main", 5.0, 74.35, 31.52, t)
    _insert(db_conn, "near-after", 4.0, 66.95, 30.25, t)
    db_conn.execute(
        "UPDATE seismic_event SET is_mainshock = FALSE "
        "WHERE source_event_id = 'near-after'"
    )

    rows = list_events(
        db_conn, center_lon=66.9, center_lat=30.2, radius_km=100,
        event_kind="mainshocks",
    )
    assert [row["source_event_id"] for row in rows] == ["near-main"]


def test_catalog_coverage_reports_canonical_time_extent(db_conn):
    first = datetime(2025, 1, 1, tzinfo=timezone.utc)
    last = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _insert(db_conn, "first", 4.0, 66.9, 30.2, first)
    _insert(db_conn, "last", 5.0, 66.9, 30.2, last)

    assert catalog_coverage(db_conn) == {
        "earliest_occurred_at": first,
        "latest_occurred_at": last,
    }
