import json
import httpx
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eqmon.events.sources import (
    parse_usgs, RawEvent, fdsn_query_params, USGSSource, FDSN_QUERY_URL, USGS_FEED_URL,
    parse_met, METSource, PMD_API_URL, _parse_coord,
)
from eqmon.config import COVERAGE_BBOX

FIXTURE = Path(__file__).parent / "fixtures" / "usgs_sample.json"
MET_FIXTURE = Path(__file__).parent / "fixtures" / "met_sample.json"


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
    # new USGS metadata fields
    assert ev.place == "near Pakistan"
    assert ev.mag_type == "mww"
    assert ev.event_type == "earthquake"
    assert ev.alert == "yellow"
    assert ev.tsunami == 0
    assert ev.sig == 450
    assert ev.review_status == "reviewed"
    assert ev.felt == 120
    assert ev.cdi == 5.2
    assert ev.mmi_report == 4.8
    assert ev.gap == 45.0
    assert ev.nst == 80
    assert ev.url == "https://earthquake.usgs.gov/earthquakes/eventpage/us1000abcd"
    assert ev.detail_url == \
        "https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us1000abcd&format=geojson"
    assert ev.updated_at == datetime(2026, 1, 1, 0, 5, 0, tzinfo=timezone.utc)


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
    assert p["eventtype"] == "earthquake"
    assert "minmagnitude" not in p


def test_fdsn_query_params_eventtype_earthquake_by_default():
    st = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX)
    assert p["eventtype"] == "earthquake"
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX, eventtype=None)
    assert "eventtype" not in p


def test_fdsn_query_params_minmagnitude_included_only_when_set():
    st = datetime(2026, 1, 1, tzinfo=timezone.utc)
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX, eventtype=None)
    assert "minmagnitude" not in p
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX, minmagnitude=2.5)
    assert p["minmagnitude"] == 2.5


def test_fdsn_query_params_endtime_included_only_when_set():
    st = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert "endtime" not in fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX)
    et = datetime(2026, 2, 1, tzinfo=timezone.utc)
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX, endtime=et)
    assert p["endtime"] == "2026-02-01T00:00:00"


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_fetch_uses_fdsn_query(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    events = USGSSource().fetch()
    # All ~30 chunk calls hit the FDSN query URL
    for url, _ in calls:
        assert url == FDSN_QUERY_URL
    assert calls[0][1]["format"] == "geojson"
    assert len(events) == 1  # only the in-region feature, deduped across chunks
    assert events[0].source_event_id == "us1000abcd"


def test_fdsn_query_params_updatedafter():
    st = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ua = datetime(2026, 6, 1, tzinfo=timezone.utc)
    p = fdsn_query_params(starttime=st, bbox=COVERAGE_BBOX, updatedafter=ua)
    assert "starttime" in p
    assert p["updatedafter"] == "2026-06-01T00:00:00"
    p2 = fdsn_query_params(bbox=COVERAGE_BBOX, updatedafter=ua, eventtype=None)
    assert "starttime" not in p2
    assert p2["updatedafter"] == "2026-06-01T00:00:00"


def test_fetch_uses_updatedafter_when_provided(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    ua = datetime(2026, 6, 1, tzinfo=timezone.utc)
    events = USGSSource().fetch(updatedafter=ua)
    # Single query, no chunking
    assert len(calls) == 1
    url, params = calls[0]
    assert url == FDSN_QUERY_URL
    assert "updatedafter" in params
    assert params["updatedafter"] == "2026-06-01T00:00:00"
    assert "starttime" not in params
    assert len(events) == 1
    assert events[0].source_event_id == "us1000abcd"


def test_fetch_updatedafter_falls_back_on_http_error(monkeypatch):
    payload = json.loads(FIXTURE.read_text())
    used = []

    def fake_get(url, params=None, timeout=None):
        used.append(url)
        if "updatedafter" in (params or {}):
            raise httpx.ConnectError("boom")
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    ua = datetime(2026, 6, 1, tzinfo=timezone.utc)
    events = USGSSource().fetch(updatedafter=ua)
    # updatedafter query fails → falls back to chunking (FDSN_QUERY_URL with starttime)
    assert FDSN_QUERY_URL in used
    assert len(events) == 1


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
    # First chunk fails (FDSN_QUERY_URL), falls back to feed (USGS_FEED_URL)
    assert used[0] == FDSN_QUERY_URL
    assert USGS_FEED_URL in used
    assert len(events) == 1


def test_fetch_default_starttime_is_window_days_ago(monkeypatch):
    captured = []

    def fake_get(url, params=None, timeout=None):
        captured.append(params)
        return _FakeResp({"features": []})

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    before = datetime.now(timezone.utc)
    USGSSource(window_days=30).fetch()
    # First chunk's starttime should be ~30 days ago
    st = datetime.strptime(captured[0]["starttime"], "%Y-%m-%dT%H:%M:%S") \
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
    captured = []

    def fake_get(url, params=None, timeout=None):
        captured.append(params)
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    since = datetime(2026, 1, 15, tzinfo=timezone.utc)
    events = USGSSource().fetch(since=since)
    # First chunk's starttime should be `since`
    assert captured[0]["starttime"] == "2026-01-15T00:00:00"
    # Each chunk returns both events; dedup keeps first occurrence of each;
    # post-filter removes event "a" (Jan 1 < Jan 15), keeps "b" (Feb 1 >= Jan 15)
    assert [e.source_event_id for e in events] == ["b"]


def test_fetch_threads_min_magnitude_into_query(monkeypatch):
    captured = []

    def fake_get(url, params=None, timeout=None):
        captured.append(params)
        return _FakeResp({"features": []})

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    USGSSource(min_magnitude=3.0).fetch()
    # All chunks should have minmagnitude set
    for p in captured:
        assert p["minmagnitude"] == 3.0
    # default source sets no floor
    captured.clear()
    USGSSource().fetch()
    for p in captured:
        assert "minmagnitude" not in p


def test_fetch_event_returns_feature_dict(monkeypatch):
    payload = {"type": "Feature", "id": "us1000abcd",
               "properties": {"mag": 5.4, "place": "near Pakistan",
                              "products": {"shakemap": [{"properties": {}}]}},
               "geometry": {"type": "Point", "coordinates": [72.5, 34.0, 15.0]}}
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append((url, params))
        class _Fake:
            def raise_for_status(self): pass
            def json(self): return payload
        return _Fake()

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    result = USGSSource().fetch_event("us1000abcd")
    assert result is not None
    assert result["type"] == "Feature"
    assert result["properties"]["products"]["shakemap"][0]["properties"] == {}
    assert len(calls) == 1
    assert calls[0][1]["eventid"] == "us1000abcd"
    assert calls[0][1]["format"] == "geojson"


def test_fetch_event_returns_none_on_error(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    assert USGSSource().fetch_event("bad") is None


# --- Pakistan MET Department source -----------------------------------------

def test_parse_coord_handles_hemispheres_and_dirty_values():
    # clean values with hemisphere suffix
    assert _parse_coord("24.87 N", is_lat=True) == 24.87
    assert _parse_coord("63.18 E", is_lat=False) == 63.18
    # Western / Southern hemispheres → negative
    assert _parse_coord("146.21 W", is_lat=False) == -146.21
    assert _parse_coord("6.99 S", is_lat=True) == -6.99
    # dirty: missing space, lowercase suffix, comma decimal
    assert _parse_coord("30.50N", is_lat=True) == 30.50
    assert _parse_coord("70.10e", is_lat=False) == 70.10
    assert _parse_coord("73,20 E", is_lat=False) == 73.20
    # plain signed decimal with no suffix (newer rows)
    assert _parse_coord("36.5202", is_lat=True) == 36.5202
    # unparseable → None
    assert _parse_coord("M", is_lat=True) is None
    assert _parse_coord("", is_lat=False) is None
    assert _parse_coord(None, is_lat=True) is None


def test_parse_met_maps_fields_and_filters_region():
    data = json.loads(MET_FIXTURE.read_text())
    events = parse_met(data)
    # Kept: in-region + parseable rows (17316, 1001-1004, 1009).
    # Dropped: Alaska (W lon, out of region), Indonesia (S lat, out of region),
    # lat=607 (out of range), magnitude="M" (unparseable), magnitude=317 (out
    # of plausible range — a swapped mag/depth row).
    assert sorted(e.source_event_id for e in events) == \
        ["1001", "1002", "1003", "1004", "1009", "17316"]
    ev = next(e for e in events if e.source_event_id == "17316")
    assert isinstance(ev, RawEvent)
    assert ev.source == "MET"
    assert ev.magnitude == 4.5
    assert ev.depth_km == 13.0
    assert ev.lon == 63.18 and ev.lat == 24.87
    assert ev.occurred_at == datetime(2026, 4, 18, 8, 49, 31, tzinfo=timezone.utc)
    assert ev.place == "Off Coast of Pakistan ( 48 Km SW of Pasni )"
    assert ev.event_type == "Automatic"


def test_parse_met_parses_dirty_coordinates_in_region():
    data = json.loads(MET_FIXTURE.read_text())
    events = {e.source_event_id: e for e in parse_met(data)}
    assert events["1001"].lat == 30.50 and events["1001"].lon == 70.00
    assert events["1002"].lat == 30.05 and events["1002"].lon == 70.10
    assert events["1003"].lon == 73.20  # comma decimal
    assert events["1004"].lat == 36.5202 and events["1004"].lon == 71.2628


def test_parse_met_skips_unparseable_and_out_of_range_rows():
    data = json.loads(MET_FIXTURE.read_text())
    ids = {e.source_event_id for e in parse_met(data)}
    assert "1006" not in ids  # latitude 607 out of range
    assert "1007" not in ids  # magnitude "M" unparseable
    assert "1008" not in ids  # magnitude 317 (swapped mag/depth) out of range


def test_parse_met_clamps_implausible_depth_to_zero():
    data = json.loads(MET_FIXTURE.read_text())
    events = {e.source_event_id for e in parse_met(data)}
    assert "1009" in events  # kept: magnitude is valid
    ev = next(e for e in parse_met(data) if e.source_event_id == "1009")
    assert ev.magnitude == 4.5
    assert ev.depth_km == 0.0  # depth 1010 km is implausible → treated as unknown


def test_met_source_fetch_sends_bearer_and_parses(monkeypatch):
    payload = json.loads(MET_FIXTURE.read_text())
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    src = METSource(url=PMD_API_URL, token="tok123")
    events = src.fetch()
    assert src.name == "MET"
    assert len(calls) == 1
    url, headers = calls[0]
    assert url == PMD_API_URL
    assert headers["Authorization"] == "Bearer tok123"
    assert headers["Accept"] == "application/json"
    assert len(events) == 6


def test_met_source_does_not_send_bearer_over_plaintext_http(monkeypatch):
    payload = json.loads(MET_FIXTURE.read_text())
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["headers"] = headers
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    # An http:// override must never leak the credential.
    METSource(url="http://weather.gov.pk/api/seismic-events", token="secret").fetch()
    assert "Authorization" not in captured["headers"]


def test_met_source_fetch_returns_empty_on_http_error(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    assert METSource(url=PMD_API_URL, token="tok").fetch() == []


def test_met_source_fetch_postfilters_since(monkeypatch):
    payload = json.loads(MET_FIXTURE.read_text())

    def fake_get(url, headers=None, timeout=None):
        return _FakeResp(payload)

    monkeypatch.setattr("eqmon.events.sources.httpx.get", fake_get)
    # 17316 occurred 2026-04-18; the 1001-1004 rows are in June 2026.
    since = datetime(2026, 5, 1, tzinfo=timezone.utc)
    events = METSource(url=PMD_API_URL, token="tok").fetch(since=since)
    assert "17316" not in {e.source_event_id for e in events}
    assert len(events) == 5
