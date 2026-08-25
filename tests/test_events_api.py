import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PMD_FIXTURE = Path(__file__).parent / "fixtures" / "pmd_sample.json"

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
        conn.execute(
            "TRUNCATE seismic_event, admin_boundary, ingest_reject RESTART IDENTITY"
        )
        conn.commit()
    yield TestClient(api.app)
    with db.get_conn() as conn:
        conn.execute(
            "TRUNCATE seismic_event, admin_boundary, ingest_reject RESTART IDENTITY"
        )
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


def test_event_search_returns_interpretation_and_catalog_coverage(client):
    created = client.post("/events", json={"magnitude": 6.1, "depth_km": 10,
                                           "lat": 30.2, "lon": 66.9}).json()
    from eqmon import db
    with db.get_conn() as conn:
        conn.execute("UPDATE seismic_event SET is_mainshock = TRUE WHERE id = %s",
                     (created["id"],))
        conn.commit()
    response = client.post("/events/search", json={
        "min_magnitude": 5,
        "center_lon": 66.9,
        "center_lat": 30.2,
        "radius_km": 100,
        "event_kind": "mainshocks",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.0"
    assert body["query"]["radius_km"] == 100
    assert body["distance_semantics"].startswith("geodesic distance")
    assert "unclassified" in body["event_kind_semantics"]
    assert "canonical" in body["source_semantics"]
    assert body["catalog_coverage"]["completeness"] == "not_asserted"
    assert body["total"] == 1
    assert body["events"][0]["is_mainshock"] is True


def test_catalog_coverage_reports_stored_source_extents_without_completeness_claim(client):
    client.post("/events", json={"magnitude": 5.1, "depth_km": 12,
                                 "lat": 30.2, "lon": 66.9})

    response = client.get("/events/catalog/coverage")

    assert response.status_code == 200
    body = response.json()
    assert body["historical_request_start"] == "1900-01-01"
    assert body["completeness"] == "not_asserted"
    assert body["coverage_bbox"] == [44.0, 8.0, 105.0, 56.0]
    assert body["sources"][0]["source"] == "MANUAL"
    assert body["sources"][0]["records"] == 1


def test_event_search_rejects_partial_radius(client):
    response = client.post("/events/search", json={
        "center_lon": 66.9,
        "center_lat": 30.2,
    })
    assert response.status_code == 422


def test_event_search_rejects_unknown_fields(client):
    response = client.post("/events/search", json={"min_magnitdue": 5})
    assert response.status_code == 422


def test_ingest_pmd_endpoint_ingests_and_records_sync(client, monkeypatch):
    payload = json.loads(PMD_FIXTURE.read_text())

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr("eqmon.events.sources.httpx.get",
                        lambda url, headers=None, timeout=None: _Resp())

    r = client.post("/events/ingest/pmd")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "PMD"
    # 6 in-region, parseable, plausible rows from the fixture
    assert body["fetched"] == 6
    assert body["inserted"] == 6
    assert body["rejected"] == 5

    from eqmon import db
    with db.get_conn() as conn:
        reject_count = conn.execute("SELECT COUNT(*) FROM ingest_reject").fetchone()[0]
    assert reject_count == 5

    # the ingested PMD events are now listable by source
    g = client.get("/events?source=PMD&limit=50")
    assert g.status_code == 200
    listed = g.json()
    events = listed["events"] if isinstance(listed, dict) else listed
    assert {e["source"] for e in events} == {"PMD"}
    assert len(events) == 6

    # the PMD sync timestamp is now exposed by the status endpoint
    s = client.get("/events/ingest/status").json()
    assert s["pmd_last_sync"] is not None
