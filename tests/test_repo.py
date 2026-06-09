import os
from datetime import datetime, timezone

import pytest

from eqmon.events.repo import create_manual_event, get_event, list_events

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def test_create_manual_event_persists_and_reads_back(db_conn):
    ev = create_manual_event(
        db_conn, magnitude=6.2, depth_km=12.0, lon=72.5, lat=34.0,
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert ev["id"] > 0
    assert ev["source"] == "MANUAL"
    assert ev["is_canonical"] is True
    assert ev["cluster_id"] == ev["id"]

    got = get_event(db_conn, ev["id"])
    assert got["magnitude"] == 6.2
    assert abs(got["lon"] - 72.5) < 1e-9 and abs(got["lat"] - 34.0) < 1e-9


def test_list_events_filters_by_min_magnitude(db_conn):
    create_manual_event(db_conn, magnitude=4.0, depth_km=5, lon=70, lat=30,
                        occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    create_manual_event(db_conn, magnitude=6.5, depth_km=5, lon=71, lat=31,
                        occurred_at=datetime(2026, 1, 3, tzinfo=timezone.utc))
    big = list_events(db_conn, min_magnitude=6.0)
    assert len(big) == 1 and big[0]["magnitude"] == 6.5


def test_get_event_missing_returns_none(db_conn):
    assert get_event(db_conn, 999999) is None
