# USGS FDSN Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch `USGSSource` from the global 24-hour `all_day` feed to the USGS FDSN `query` API (region- and time-filtered server-side), falling back to the feed only on HTTP failure.

**Architecture:** Only `src/eqmon/events/sources.py` and `tests/test_sources.py` change. A new pure `fdsn_query_params()` builds the request parameters; `USGSSource.fetch()` calls the FDSN `query` endpoint, reuses the unchanged `parse_usgs()` (FDSN `format=geojson` is the same GeoJSON shape as the feed), and falls back to the feed on `httpx.HTTPError`. `parse_usgs`, `ingest()`, the DB, `/events/ingest`, and the frontend are untouched.

**Tech Stack:** Python 3.12, httpx, pytest. Tests run with `uv run pytest` (pyproject sets `pythonpath = ["src"]`); source tests need no database.

**Spec:** `docs/superpowers/specs/2026-06-11-usgs-fdsn-phase0-design.md`

**Reference — current `sources.py` facts:**
- Imports: `from datetime import datetime, timezone` (Task 2 adds `timedelta`).
- `USGS_FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"` (retained as fallback).
- `parse_usgs(geojson)` parses `[lon,lat,depth]` + `properties.mag/time` + `id`, and filters to `config.COVERAGE_BBOX = (44.0, 8.0, 105.0, 56.0)` = `(min lon, min lat, max lon, max lat)`. **Unchanged by this plan.**
- `COVERAGE_BBOX` is imported in `sources.py` as `from ..config import COVERAGE_BBOX`.
- Test fixture `tests/fixtures/usgs_sample.json`: in-region feature `us1000abcd` at `[72.5, 34.0, 15.0]`, mag 5.4, time `1767225600000` (2026-01-01T00:00:00Z); out-of-region `us1000ffff` at `[-150.0, 60.0]`.

---

### Task 1: `fdsn_query_params()` pure builder + constants

**Files:**
- Modify: `src/eqmon/events/sources.py` (add two constants after `USGS_FEED_URL`; add the function just above the `USGSSource` class)
- Test: `tests/test_sources.py` (append two tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py`:

```python
from eqmon.events.sources import fdsn_query_params
from eqmon.config import COVERAGE_BBOX


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL with `ImportError: cannot import name 'fdsn_query_params'`.

- [ ] **Step 3: Add the constants**

In `src/eqmon/events/sources.py`, immediately after the `USGS_FEED_URL = (...)` block, add:

```python
FDSN_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
DEFAULT_WINDOW_DAYS = 30
```

- [ ] **Step 4: Add the function**

In `src/eqmon/events/sources.py`, add this function directly above the
`class USGSSource:` line:

```python
def fdsn_query_params(*, starttime: datetime,
                      bbox: tuple[float, float, float, float],
                      minmagnitude: float | None = None,
                      limit: int = 20000) -> dict:
    """Build FDSN `event/query` parameters for a region + time window.

    `bbox` is (min lon, min lat, max lon, max lat) — matches config.COVERAGE_BBOX.
    `starttime` must be a UTC datetime; formatted without a tz suffix (FDSN
    assumes UTC). `limit` is capped at FDSN's hard max (20000); `orderby=time`
    keeps the most recent events if the window ever saturates. Proper time
    windowing for large historical pulls is Phase 1.
    """
    minx, miny, maxx, maxy = bbox
    params: dict = {
        "format": "geojson",
        "starttime": starttime.strftime("%Y-%m-%dT%H:%M:%S"),
        "minlatitude": miny,
        "maxlatitude": maxy,
        "minlongitude": minx,
        "maxlongitude": maxx,
        "orderby": "time",
        "limit": limit,
    }
    if minmagnitude is not None:
        params["minmagnitude"] = minmagnitude
    return params
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_sources.py -v`
Expected: PASS (the two new tests plus the two existing `parse_usgs` tests).

- [ ] **Step 6: Commit**

```bash
git add src/eqmon/events/sources.py tests/test_sources.py
git commit -m "feat(events): fdsn_query_params builder + FDSN constants"
```

---

### Task 2: `USGSSource.fetch()` → FDSN query with feed fallback

**Files:**
- Modify: `src/eqmon/events/sources.py` (add `timedelta` import; replace the `USGSSource.__init__` and `fetch` methods)
- Test: `tests/test_sources.py` (append four tests + a fake-response helper)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources.py`:

```python
import httpx
from datetime import timedelta
from eqmon.events.sources import USGSSource, FDSN_QUERY_URL, USGS_FEED_URL


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL — `test_fetch_uses_fdsn_query` asserts `calls["url"] == FDSN_QUERY_URL` but the current `fetch` calls `self.url` (the feed), and `USGSSource(window_days=30)` raises `TypeError` (no such parameter yet).

- [ ] **Step 3: Add the `timedelta` import**

In `src/eqmon/events/sources.py`, change:

```python
from datetime import datetime, timezone
```
to:
```python
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 4: Replace the `USGSSource` `__init__` and `fetch`**

In `src/eqmon/events/sources.py`, replace the current `USGSSource` body:

```python
class USGSSource:
    name = "USGS"

    def __init__(self, url: str = USGS_FEED_URL, timeout: float = 15.0):
        self.url = url
        self.timeout = timeout

    def fetch(self, since: datetime | None = None) -> list[RawEvent]:
        resp = httpx.get(self.url, timeout=self.timeout)
        resp.raise_for_status()
        events = parse_usgs(resp.json())
        if since is not None:
            events = [e for e in events if e.occurred_at >= since]
        return events
```

with:

```python
class USGSSource:
    name = "USGS"

    def __init__(self, query_url: str = FDSN_QUERY_URL,
                 feed_url: str = USGS_FEED_URL,
                 min_magnitude: float | None = None,
                 window_days: int = DEFAULT_WINDOW_DAYS,
                 timeout: float = 15.0):
        self.query_url = query_url
        self.feed_url = feed_url
        self.min_magnitude = min_magnitude
        self.window_days = window_days
        self.timeout = timeout

    def fetch(self, since: datetime | None = None) -> list[RawEvent]:
        starttime = since or (datetime.now(timezone.utc)
                              - timedelta(days=self.window_days))
        try:
            params = fdsn_query_params(starttime=starttime, bbox=COVERAGE_BBOX,
                                       minmagnitude=self.min_magnitude)
            resp = httpx.get(self.query_url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            events = parse_usgs(resp.json())
        except httpx.HTTPError:
            # FDSN unreachable or returned an error status: fall back to the
            # real-time feed (24h, global; parse_usgs filters to the region).
            resp = httpx.get(self.feed_url, timeout=self.timeout)
            resp.raise_for_status()
            events = parse_usgs(resp.json())
        if since is not None:
            events = [e for e in events if e.occurred_at >= since]
        return events
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_sources.py -v`
Expected: PASS — all source tests (2 existing parse tests + 2 from Task 1 + 4 here).

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `uv run pytest tests/test_sources.py tests/test_ingest.py -v`
Expected: PASS. (`test_ingest.py` may construct `USGSSource` or a fake source; the constructor stays backward-compatible because every new parameter is defaulted. DB-backed tests skip if `DATABASE_URL_TEST` is unset — that is expected, not a failure.)

- [ ] **Step 7: Commit**

```bash
git add src/eqmon/events/sources.py tests/test_sources.py
git commit -m "feat(events): USGSSource fetches FDSN query API, feed as fallback"
```

---

## Self-Review Notes

- **Spec coverage:** `fdsn_query_params` (spec §Components) → Task 1; `USGSSource`
  constructor + `fetch` with fallback + `since`→`starttime` + 30-day default + 20k
  cap (spec §Components, §Error handling) → Task 2. Spec test list: tests 1–2 →
  Task 1; test 3 (parse FDSN fixture) is already covered by the existing
  `test_parse_usgs_maps_fields_and_filters_region` and reused as the response body
  in Task 2 tests 4–5; tests 4 (happy), 5 (fallback), 6 (since mapping) → Task 2.
- **Backward compatibility:** `api.py` calls `USGSSource()` with no args; every new
  constructor parameter is defaulted, so that call is unaffected (verified in Task 2
  Step 6).
- **Name/type consistency:** `fdsn_query_params`, `FDSN_QUERY_URL`,
  `DEFAULT_WINDOW_DAYS`, `USGS_FEED_URL`, `query_url`, `feed_url`, `min_magnitude`,
  `window_days` are used identically in spec and both tasks. `parse_usgs`,
  `RawEvent`, `COVERAGE_BBOX` are existing names, unchanged.
- **No placeholders:** every code and test block is complete and runnable; every
  run command has an expected result.
