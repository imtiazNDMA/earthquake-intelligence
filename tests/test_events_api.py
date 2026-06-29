import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MET_FIXTURE = Path(__file__).parent / "fixtures" / "met_sample.json"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


@pytest.fixture()
def client(monkeypatch):
    # point the app pool at the test DB
    monkeypatch.setenv("DATABASE_URL", os.environ["DATABASE_URL_TEST"])
    from eqmon import api, db
    db._pool = None  # force pool recreation against the test DB
    db.init_schema()
    # clean slate so committed rows from these tests don't leak to other tests
    with db.get_conn() as conn:
        conn.execute("TRUNCATE seismic_event, admin_boundary RESTART IDENTITY")
        conn.commit()
    yield TestClient(api.app)
    with db.get_conn() as conn:
        conn.execute("TRUNCATE seismic_event, admin_boundary RESTART IDENTITY")
        conn.commit()
    db._pool = None


def test_manual_event_create_and_get(client):
    r = client.post("/events", json={"magnitude": 6.1, "depth_km": 10,
                                     "lat": 34.0, "lon": 72.5})
    assert r.status_code == 200
    eid = r.json()["id"]
    g = client.get(f"/events/{eid}")
    assert g.status_code == 200 and g.json()["source"] == "MANUAL"


def test_manual_event_out_of_region_rejected(client):
    r = client.post("/events", json={"magnitude": 6.1, "depth_km": 10,
                                     "lat": 0.0, "lon": 0.0})
    assert r.status_code == 422


def test_event_detail_404_for_missing(client):
    r = client.get("/events/99999999")
    assert r.status_code == 404


def test_ingest_met_endpoint_ingests_and_records_sync(client, monkeypatch):
    payload = json.loads(MET_FIXTURE.read_text())

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr("eqmon.events.sources.httpx.get",
                        lambda url, headers=None, timeout=None: _Resp())

    r = client.post("/events/ingest/met")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "MET"
    # 6 in-region, parseable, plausible rows from the fixture
    assert body["fetched"] == 6
    assert body["inserted"] == 6

    # the ingested MET events are now listable by source
    g = client.get("/events?source=MET&limit=50")
    assert g.status_code == 200
    listed = g.json()
    events = listed["events"] if isinstance(listed, dict) else listed
    assert {e["source"] for e in events} == {"MET"}
    assert len(events) == 6

    # the MET sync timestamp is now exposed by the status endpoint
    s = client.get("/events/ingest/status").json()
    assert s["met_last_sync"] is not None
