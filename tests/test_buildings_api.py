"""Buildings tile proxy. No DB and no live tile server: the upstream httpx
client is replaced with a fake, so these run anywhere."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eqmon import buildings

INDEX = [
    {"id": "Lahore_buildings", "bounds": [74.05, 31.25, 74.65, 31.71], "maxzoom": 17},
    {"id": "Dera_Ghazi_Khan_buildings", "bounds": [69.88, 29.61, 70.88, 31.33], "maxzoom": 17},
    # Non-building dataset and a bounds-less entry: both must be dropped.
    {"id": "roads", "bounds": [60.0, 20.0, 80.0, 40.0]},
    {"id": "Broken_buildings"},
]


class FakeResponse:
    def __init__(self, status_code=200, content=b"", json_data=None, headers=None):
        self.status_code = status_code
        self.content = content
        self._json = json_data
        self.headers = headers or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """Records every URL requested so tests can assert nothing leaked upstream."""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        return self._handler(url)


@pytest.fixture(autouse=True)
def _reset_module_state():
    """The catalog cache and the client are module-level, so leaking either
    between tests would make them order-dependent."""
    real_get_client = buildings._get_client
    buildings._catalog = None
    yield
    buildings._catalog = None
    buildings._get_client = real_get_client


def make_client(handler):
    """App + fake upstream. Returns (TestClient, FakeClient)."""
    fake = FakeClient(handler)
    buildings._get_client = lambda: fake
    app = FastAPI()
    app.include_router(buildings.router)
    return TestClient(app), fake


def ok_handler(url):
    if url.endswith("/index.json"):
        return FakeResponse(json_data=INDEX)
    return FakeResponse(content=b"\x1a\x2b tile bytes")


def test_catalog_keeps_only_building_datasets_with_bounds():
    client, _ = make_client(ok_handler)
    body = client.get("/buildings/districts").json()
    assert [d["id"] for d in body["districts"]] == [
        "Dera_Ghazi_Khan_buildings", "Lahore_buildings",  # sorted by label
    ]
    assert body["min_zoom"] == 12


def test_catalog_prettifies_labels():
    client, _ = make_client(ok_handler)
    labels = {d["id"]: d["label"] for d in client.get("/buildings/districts").json()["districts"]}
    assert labels["Dera_Ghazi_Khan_buildings"] == "Dera Ghazi Khan"


def test_catalog_exposes_bounds_for_viewport_gating():
    client, _ = make_client(ok_handler)
    lahore = client.get("/buildings/districts").json()["districts"][1]
    assert lahore["bounds"] == [74.05, 31.25, 74.65, 31.71]


def test_tile_passthrough_sets_mvt_content_type():
    client, _ = make_client(ok_handler)
    resp = client.get("/buildings/tiles/Lahore_buildings/14/11576/6679.pbf")
    assert resp.status_code == 200
    assert resp.content == b"\x1a\x2b tile bytes"
    assert resp.headers["content-type"] == buildings.MVT_MEDIA_TYPE


def test_empty_tile_passes_through_as_204():
    def handler(url):
        if url.endswith("/index.json"):
            return FakeResponse(json_data=INDEX)
        return FakeResponse(status_code=204)

    client, _ = make_client(handler)
    assert client.get("/buildings/tiles/Lahore_buildings/14/1/1.pbf").status_code == 204


def test_unknown_dataset_is_rejected_without_calling_upstream():
    client, fake = make_client(ok_handler)
    assert client.get("/buildings/tiles/Nonexistent_buildings/14/1/1.pbf").status_code == 404
    # Only the catalog fetch — the tile URL was never constructed.
    assert all(u.endswith("/index.json") for u in fake.calls)


def test_path_traversal_in_dataset_is_rejected():
    client, fake = make_client(ok_handler)
    resp = client.get("/buildings/tiles/..%2F..%2Fetc%2Fpasswd/14/1/1.pbf")
    assert resp.status_code == 404
    assert all(u.endswith("/index.json") for u in fake.calls)


def test_catalog_unavailable_returns_503():
    def handler(url):
        raise ConnectionError("tile server down")

    client, _ = make_client(handler)
    assert client.get("/buildings/districts").status_code == 503


def test_tile_upstream_failure_returns_502():
    def handler(url):
        if url.endswith("/index.json"):
            return FakeResponse(json_data=INDEX)
        raise ConnectionError("boom")

    client, _ = make_client(handler)
    assert client.get("/buildings/tiles/Lahore_buildings/14/1/1.pbf").status_code == 502


def test_tile_upstream_500_returns_502():
    def handler(url):
        if url.endswith("/index.json"):
            return FakeResponse(json_data=INDEX)
        return FakeResponse(status_code=500)

    client, _ = make_client(handler)
    assert client.get("/buildings/tiles/Lahore_buildings/14/1/1.pbf").status_code == 502


def test_catalog_is_fetched_once_and_reused():
    client, fake = make_client(ok_handler)
    client.get("/buildings/districts")
    client.get("/buildings/districts")
    client.get("/buildings/tiles/Lahore_buildings/14/1/1.pbf")
    assert sum(u.endswith("/index.json") for u in fake.calls) == 1
