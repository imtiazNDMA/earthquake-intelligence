import json
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eqmon.events.sources import (
    parse_usgs, RawEvent, fdsn_query_params, USGSSource, FDSN_QUERY_URL, USGS_FEED_URL,
)
from eqmon.config import COVERAGE_BBOX

FIXTURE = Path(__file__).parent / "fixtures" / "usgs_sample.json"


def test_parse_usgs_maps_fields_and_filters_region():
    data = json.loads(FIXTURE.read_text())
    events = parse_usgs(data)
    # only the in-region feature survives the Coverage Region filter
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, RawEvent)
    assert ev.source == "USGS"
    assert ev.source_event_id == "us1000abcd"
    assert ev.magnitude == 5.4
    assert ev.depth_km == 15.0
    assert ev.lon == 72.5 and ev.lat == 34.0
    assert ev.occurred_at == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_parse_usgs_skips_features_missing_required_fields():
    data = {"features": [{"id": "x", "properties": {"mag": None, "time": 1767225600000},
                          "geometry": {"type": "Point", "coordinates": [72.5, 34.0, 5.0]}}]}
    assert parse_usgs(data) == []


def test_fdsn_query_params_region_time_format():
    st = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX)
    assert p["format"] == "geojson"
    assert p["orderby"] == "time"
    assert p["limit"] == 20000
    assert p["minlongitude"] == 44.0
    assert p["minlatitude"] == 8.0
    assert p["maxlongitude"] == 105.0
    assert p["maxlatitude"] == 56.0
    assert p["starttime"] == "2026-01-01T00:00:00"
    assert "minmagnitude" not in p


def test_fdsn_query_params_minmagnitude_included_only_when_set():
    st = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert "minmagnitude" not in fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX)
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX, minmagnitude=2.5)
    assert p["minmagnitude"] == 2.5


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_uses_fdsn_query(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    calls = {}

    def fake_get(url, params=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    events = USGSSource().fetch()
    assert calls["url"] == FDSN_QUERY_URL
    assert calls["params"]["format"] == "geojson"
    assert len(events) == 1  # only the in-region feature survives
    assert events[0].source_event_id == "us1000abcd"


def test_fetch_falls_back_to_feed_on_http_error(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    used = []

    def fake_get(url, params=None, timeout=None):
        used.append(url)
        if url == FDSN_QUERY_URL:
            raise httpx.ConnectError("boom")
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    events = USGSSource().fetch()
    assert FDSN_QUERY_URL in used and USGS_FEED_URL in used
    assert len(events) == 1


def test_fetch_default_starttime_is_window_days_ago(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResp({"features": []})

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    before = datetime.now(timezone.utc)
    USGSSource(window_days=30).fetch()
    st = datetime.strptime(captured["params"]["starttime"], "%Y-%m-%dT%H:%M:%S") \
        .replace(tzinfo=timezone.utc)
    delta = before - st
    assert timedelta(days=29, hours=23) <= delta <= timedelta(days=30, hours=1)


def test_fetch_since_is_passed_and_postfilters(monkeypatch):
    # two in-region events: 2026-01-01 and 2026-02-01
    payload = {"features": [
        {"id": "a", "properties": {"mag": 5.0, "time": 1767225600000},
         "geometry": {"coordinates": [72.5, 34.0, 10.0]}},
        {"id": "b", "properties": {"mag": 5.0, "time": 1769904000000},
         "geometry": {"coordinates": [72.5, 34.0, 10.0]}},
    ]}
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    since = datetime(2026, 1, 15, tzinfo=timezone.utc)
    events = USGSSource().fetch(since=since)
    assert captured["params"]["starttime"] == "2026-01-15T00:00:00"
    assert [e.source_event_id for e in events] == ["b"]  # only Feb >= since


def test_fetch_threads_min_magnitude_into_query(monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResp({"features": []})

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    USGSSource(min_magnitude=3.0).fetch()
    assert captured["params"]["minmagnitude"] == 3.0
    # default source sets no floor
    USGSSource().fetch()
    assert "minmagnitude" not in captured["params"]
