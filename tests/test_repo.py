import os
from datetime import datetime, timezone

import pytest

from eqmon.events.repo import create_manual_event, get_event, update_usgs_detail

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
