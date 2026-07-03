import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


class _CtxConn:
    """Wrap the test transaction so `with db.get_conn() as c` yields it without closing."""
    def __init__(self, conn):
        self._c = conn

    def __enter__(self):
        return self._c

    def __exit__(self, *a):
        return False


def _seed(conn):
    # 120 events at M3.0-5.0 in one zone/time so Mc + b-value are computable.
    for i in range(120):
        mag = 3.0 + (i % 20) * 0.1
        conn.execute(
            "INSERT INTO seismic_event (source, source_event_id, occurred_at, magnitude,"
            " depth_km, geom, is_canonical, is_mainshock) VALUES ('USGS', %s, %s, %s, 20,"
            " ST_SetSRID(ST_MakePoint(72,34),4326), TRUE, TRUE)",
            (f"e{i}", datetime(2026, 1, 1, tzinfo=timezone.utc), mag))


def test_analytics_endpoint_shape_and_filters(db_conn, monkeypatch):
    from eqmon import api, db
    _seed(db_conn)
    monkeypatch.setattr(db, "get_conn", lambda: _CtxConn(db_conn))
    client = TestClient(api.app)
    r = client.get("/analytics?window=all&min_mag=mc")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"provenance", "kpis", "grid", "fmd", "depth", "rate", "zones"}
    assert body["kpis"]["mc"] is not None
    # bad window -> 400
    assert client.get("/analytics?window=nope").status_code == 400


def test_zones_geojson_and_stats_gone(db_conn, monkeypatch):
    from eqmon import api, db
    db_conn.execute(
        "INSERT INTO tectonic_zone (name, geom) VALUES ('Z1', "
        "ST_SetSRID(ST_GeomFromText('MULTIPOLYGON(((71 33,73 33,73 35,71 35,71 33)))'),4326))")
    monkeypatch.setattr(db, "get_conn", lambda: _CtxConn(db_conn))
    client = TestClient(api.app)
    r = client.get("/zones")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["features"]
    assert fc["features"][0]["properties"]["name"] == "Z1"
    # retired: the path now falls through to /events/{event_id}, which
    # rejects the non-integer "stats" with 422 rather than 404
    assert client.get("/events/stats").status_code in (404, 422)
