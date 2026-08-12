"""Exposure (ARC) adapter. No live ARC service: the upstream httpx client is
replaced with a fake, so these run anywhere."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eqmon import exposure

BANDS = {
    "type": "FeatureCollection",
    "features": [
        {"type": "Feature",
         "properties": {"mmi_lower": 6, "mmi_upper": 7, "color": "#ffff00", "label": "VI (Strong)"},
         "geometry": {"type": "Polygon", "coordinates": [[[73, 34], [74, 34], [74, 35], [73, 34]]]}},
        {"type": "Feature",
         "properties": {"mmi_lower": 7, "mmi_upper": 8, "color": "#ffc800", "label": "VII (Very strong)"},
         "geometry": {"type": "Polygon", "coordinates": [[[73.2, 34.2], [73.6, 34.2], [73.6, 34.6], [73.2, 34.2]]]}},
    ],
}

# Shaped after a real response. Note the cumulative rows: ARC keys `mmi_min` on
# each band's UPPER bound, so its "mmi_min: 6" row folds in the 5-6 band — the
# one this platform labels MMI V. Reading that row as "MMI VI and above" would
# overstate the headline by the whole MMI V population.
ARC_OK = {
    "ok": True,
    "bands": [
        {"mmi_low": 7, "mmi_high": 8, "color": "#ffc800", "area_km2": 1787.0,
         "elements": {"population": {"total": 1856644.0, "male": 956644.0,
                                     "female": 900000.0, "points": 10},
                      "hospitals": {"count": 83}}},
        {"mmi_low": 6, "mmi_high": 7, "color": "#ffff00", "area_km2": 5315.0,
         "elements": {"population": {"total": 7331782.0, "male": 3731782.0,
                                     "female": 3600000.0, "points": 20},
                      "hospitals": {"count": 217}}},
        {"mmi_low": 5, "mmi_high": 6, "color": "#7aff93", "area_km2": 11508.0,
         "elements": {"population": {"total": 8010546.0, "male": 4010546.0,
                                     "female": 4000000.0, "points": 30},
                      "hospitals": {"count": 437}}},
    ],
    "totals": {"population": {"total": 17198972.0}, "hospitals": {"count": 737}},
    "cumulative": [
        {"mmi_min": 8, "area_km2": 1787.0,
         "elements": {"population": {"total": 1856644.0}, "hospitals": {"count": 83}}},
        {"mmi_min": 7, "area_km2": 7102.0,
         "elements": {"population": {"total": 9188426.0}, "hospitals": {"count": 300}}},
        {"mmi_min": 6, "area_km2": 18610.0,
         "elements": {"population": {"total": 17198972.0}, "hospitals": {"count": 737}}},
    ],
    "meta": {"crs": "EPSG:4326"},
}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


class FakeClient:
    """Records every request so tests can assert what we actually sent."""

    def __init__(self, handler):
        self._handler = handler
        self.posts = []
        self.gets = []

    async def post(self, url, json=None):
        self.posts.append((url, json))
        return self._handler(url, json)

    async def get(self, url):
        self.gets.append(url)
        return self._handler(url, None)


@pytest.fixture(autouse=True)
def _restore_client():
    real = exposure._get_client
    yield
    exposure._get_client = real


def make_client(handler):
    fake = FakeClient(handler)
    exposure._get_client = lambda: fake
    app = FastAPI()
    app.include_router(exposure.router)
    return TestClient(app), fake


def ok_handler(url, payload=None):
    if url.endswith("/api/analyze"):
        return FakeResponse(json_data=ARC_OK)
    if url.endswith("/api/health"):
        return FakeResponse(json_data={"caches_missing": [], "layers": {}})
    if url.endswith("/api/layers"):
        return FakeResponse(json_data={"ok": True, "layers": [{"name": "population"}]})
    raise AssertionError(f"unexpected url {url}")


# --- band translation -------------------------------------------------------

def test_arc_bands_carry_the_field_arc_dissolves_on():
    out = exposure.to_arc_bands(BANDS)
    assert [f["properties"]["mmi_high"] for f in out["features"]] == [7, 8]
    assert [f["properties"]["mmi_low"] for f in out["features"]] == [6, 7]


def test_arc_bands_keep_our_own_properties():
    props = exposure.to_arc_bands(BANDS)["features"][0]["properties"]
    assert props["mmi_upper"] == 7 and props["color"] == "#ffff00"


def test_arc_bands_does_not_mutate_the_caller_s_bands():
    exposure.to_arc_bands(BANDS)
    assert "mmi_high" not in BANDS["features"][0]["properties"]


# --- summarising ------------------------------------------------------------

def test_summary_headline_bands_by_our_own_mmi_label():
    # A band labelled MMI VI is one whose LOWER bound is 6, matching how
    # impact.py rolls up admin units and how the strip labels them.
    s = exposure.summarize(ARC_OK, min_mmi=6)
    assert s["at_min_mmi"]["elements"]["population"]["total"] == 1856644.0 + 7331782.0
    assert s["at_min_mmi"]["area_km2"] == 1787.0 + 5315.0
    assert s["min_mmi"] == 6


def test_summary_headline_does_not_take_arcs_cumulative_row_at_face_value():
    # ARC's mmi_min=6 row includes the 5-6 band. If we ever read it directly,
    # the headline silently gains every person in MMI V.
    s = exposure.summarize(ARC_OK, min_mmi=6)
    arc_row = next(c for c in ARC_OK["cumulative"] if c["mmi_min"] == 6)
    assert s["at_min_mmi"]["elements"]["population"]["total"] != \
        arc_row["elements"]["population"]["total"]


def test_summary_headline_sums_every_element_field():
    s = exposure.summarize(ARC_OK, min_mmi=6)
    pop = s["at_min_mmi"]["elements"]["population"]
    assert pop["male"] == 956644.0 + 3731782.0
    assert pop["points"] == 30          # grid cells hit, not people
    assert s["at_min_mmi"]["elements"]["hospitals"]["count"] == 300


def test_summary_headline_is_empty_when_shaking_never_reaches_the_threshold():
    # Bands top out at a lower bound of 7; nothing is labelled MMI IX.
    s = exposure.summarize(ARC_OK, min_mmi=9)
    assert s["at_min_mmi"]["elements"] == {}
    assert s["at_min_mmi"]["area_km2"] == 0


def test_summary_keeps_bands_strongest_first_and_totals():
    s = exposure.summarize(ARC_OK, min_mmi=6)
    assert [b["mmi_low"] for b in s["bands"]] == [7, 6, 5]
    assert s["totals"]["population"]["total"] == 17198972.0


# --- calling ARC ------------------------------------------------------------

def test_analyze_sends_geojson_and_suppresses_arc_geometry():
    client, fake = make_client(ok_handler)
    client.post("/exposure/analyze", json={"bands": BANDS})
    _, payload = fake.posts[0]
    assert payload["source"] == "geojson"
    # We render our own bands; ARC's smoothed copy would be a second, subtly
    # different footprint on the same map.
    assert payload["include_geometry"] is False
    assert payload["geojson"]["features"][0]["properties"]["mmi_high"] == 7


def test_analyze_narrows_layers_when_asked():
    client, fake = make_client(ok_handler)
    client.post("/exposure/analyze", json={"bands": BANDS, "layers": ["population"]})
    assert fake.posts[0][1]["layers"] == ["population"]


def test_analyze_omits_layers_by_default_so_arc_uses_all_of_them():
    client, fake = make_client(ok_handler)
    client.post("/exposure/analyze", json={"bands": BANDS})
    assert "layers" not in fake.posts[0][1]


def test_analyze_returns_the_summary():
    client, _ = make_client(ok_handler)
    body = client.post("/exposure/analyze", json={"bands": BANDS}).json()
    assert body["at_min_mmi"]["elements"]["population"]["total"] == 1856644.0 + 7331782.0
    assert len(body["bands"]) == 3


def test_empty_bands_are_rejected_without_calling_arc():
    client, fake = make_client(ok_handler)
    resp = client.post("/exposure/analyze",
                       json={"bands": {"type": "FeatureCollection", "features": []}})
    assert resp.status_code == 400
    # An empty footprint costs ARC a full layer scan to return zeros.
    assert fake.posts == []


# --- failure modes ----------------------------------------------------------

def test_arc_unreachable_returns_503():
    def handler(url, payload=None):
        raise ConnectionError("arc is down")

    client, _ = make_client(handler)
    assert client.post("/exposure/analyze", json={"bands": BANDS}).status_code == 503


def test_arc_error_body_is_surfaced_not_swallowed():
    def handler(url, payload=None):
        return FakeResponse(status_code=400, json_data={"ok": False, "error": "bad band field"})

    client, _ = make_client(handler)
    resp = client.post("/exposure/analyze", json={"bands": BANDS})
    assert resp.status_code == 502
    assert "bad band field" in resp.json()["detail"]


def test_arc_200_with_ok_false_is_still_a_failure():
    def handler(url, payload=None):
        return FakeResponse(status_code=200, json_data={"ok": False, "error": "no usable polygons"})

    client, _ = make_client(handler)
    resp = client.post("/exposure/analyze", json={"bands": BANDS})
    assert resp.status_code == 502
    assert "no usable polygons" in resp.json()["detail"]


# --- passthroughs -----------------------------------------------------------

def test_health_passthrough():
    client, _ = make_client(ok_handler)
    assert client.get("/exposure/health").json()["caches_missing"] == []


def test_layers_passthrough():
    client, _ = make_client(ok_handler)
    assert client.get("/exposure/layers").json()["layers"] == [{"name": "population"}]


def test_health_reports_unavailable_rather_than_raising():
    def handler(url, payload=None):
        raise ConnectionError("down")

    client, _ = make_client(handler)
    resp = client.get("/exposure/health")
    # The UI polls this to decide whether to offer exposure at all, so it must
    # answer even when ARC does not.
    assert resp.status_code == 200
    assert resp.json()["available"] is False
