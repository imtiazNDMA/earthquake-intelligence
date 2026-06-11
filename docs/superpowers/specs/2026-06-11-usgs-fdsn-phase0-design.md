# USGS FDSN Phase 0 — Swap real-time feed → FDSN `query` API

**Date:** 2026-06-11
**Status:** Approved (design)
**Roadmap:** `docs/superpowers/roadmaps/2026-06-11-usgs-fdsn-roadmap.md` (Phase 0)
**Scope:** `src/eqmon/events/sources.py` + its tests. No DB, API, ingest, or
frontend changes.

## Problem

`USGSSource` ingests the USGS **real-time feed**
(`.../summary/all_day.geojson`): a rolling 24-hour, global file that is
downloaded in full and filtered to the region in Python. This gives no control
over time range or magnitude, fetches the whole world to keep a small region, and
caps history at 24 hours. The FDSN `query` API supports server-side region, time,
and magnitude filtering and arbitrary history.

## Goal

Change only the data-acquisition layer so `USGSSource.fetch()` calls the FDSN
`query` endpoint (region + time filtered server-side), falling back to the
existing feed on HTTP failure. Everything downstream is unchanged because FDSN's
`format=geojson` output is the same GeoJSON shape `parse_usgs` already consumes.

## Design decisions (locked)

- **Default window:** last 30 days when `fetch()` is called with no `since`.
- **Magnitude floor:** none (ingest all magnitudes, matching today's feed).
- **Old feed:** retained as a fallback used only when the FDSN call raises
  `httpx.HTTPError`.
- **20k cap:** pass `limit=20000` + `orderby=time` (keep most-recent if capped).
  Proper time-windowing is deferred to Phase 1.
- **Fallback scope:** catch only `httpx.HTTPError` (network/status), so parse
  errors still surface as real bugs.

## Data flow

```
fetch(since)
  starttime = since or (now_utc - 30 days)
  try:
    httpx.get(FDSN_QUERY_URL, params=fdsn_query_params(starttime, COVERAGE_BBOX))
    raise_for_status()
    events = parse_usgs(resp.json())
  except httpx.HTTPError:
    resp = httpx.get(USGS_FEED_URL)          # fallback: all_day feed
    raise_for_status()
    events = parse_usgs(resp.json())
  if since is not None:
    events = [e for e in events if e.occurred_at >= since]
  return events
```

`parse_usgs` is unchanged: it still parses `[lon, lat, depth]` geometry and
`properties.mag/time`, `id`, and re-applies the `COVERAGE_BBOX` region filter
(redundant but harmless on the FDSN path; meaningful on the fallback path).

## Components

### New constants (in `sources.py`)
```python
FDSN_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
DEFAULT_WINDOW_DAYS = 30
```
`USGS_FEED_URL` is retained for the fallback.

### `fdsn_query_params(*, starttime, bbox, minmagnitude=None, limit=20000) -> dict`
Pure function (no network), returns the FDSN query-param dict:

```python
def fdsn_query_params(*, starttime: datetime, bbox: tuple[float, float, float, float],
                      minmagnitude: float | None = None, limit: int = 20000) -> dict:
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
- `bbox` is `(minx, miny, maxx, maxy)` = `(min lon, min lat, max lon, max lat)`,
  matching `config.COVERAGE_BBOX` = `(44.0, 8.0, 105.0, 56.0)`.
- `starttime` is formatted as ISO8601 without timezone suffix; FDSN assumes UTC.
  Callers pass timezone-aware UTC datetimes.

### `USGSSource`
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
            # FDSN unreachable / returned an error status -> fall back to the
            # real-time feed (24h, global; parse_usgs filters to the region).
            resp = httpx.get(self.feed_url, timeout=self.timeout)
            resp.raise_for_status()
            events = parse_usgs(resp.json())
        if since is not None:
            events = [e for e in events if e.occurred_at >= since]
        return events
```

The constructor signature stays backward-compatible: `USGSSource()` (as called
in `api.py`) works with all new args defaulted. `RawEvent`, `parse_usgs`,
`METSource`, and the `SeismicSource` protocol are unchanged.

## Error handling

- **FDSN failure** (DNS, timeout, connection error, or non-2xx via
  `raise_for_status`) raises `httpx.HTTPError` → fall back to the feed.
- **Fallback failure** propagates (the feed `raise_for_status` or network error
  raises out of `fetch`). `ingest()` already wraps `source.fetch(...)` in
  try/except and records the failure non-fatally in `IngestResult.errors`, so a
  total outage degrades gracefully without crashing the endpoint.
- **Parse errors are not caught** — a malformed-but-200 response surfaces as a
  real bug rather than being masked by the fallback.
- **20k cap:** `limit=20000` prevents FDSN's HTTP-400-on-overflow; `orderby=time`
  keeps the most recent events if the region/window ever saturates. A code comment
  records that Phase 1 adds proper windowing.

## Testing (TDD, no network)

New tests are added to `tests/test_sources.py` (which already tests `parse_usgs`).
Network is avoided by monkeypatching `eqmon.events.sources.httpx` (its `.get`).
The existing fixture `tests/fixtures/usgs_sample.json` (one in-region + one
out-of-region feature) is reused as the FDSN fixture — FDSN `format=geojson` is
the same shape, so no new fixture is needed.

1. **`fdsn_query_params` — region/time/format/limit.** Given a fixed `starttime`
   and `COVERAGE_BBOX`, asserts `format=geojson`, `orderby=time`, `limit=20000`,
   the four lat/lon bounds map correctly (`minlatitude=8`, `maxlatitude=56`,
   `minlongitude=44`, `maxlongitude=105`), and `starttime` is the expected
   ISO8601 string.
2. **`fdsn_query_params` — minmagnitude.** Omitted when `None`; present and equal
   when a float is given.
3. **`parse_usgs` — FDSN fixture.** The existing `usgs_sample.json` (one
   in-region, one out-of-region feature) parses to exactly the in-region
   `RawEvent` — already covered by `test_parse_usgs_maps_fields_and_filters_region`;
   reused as the FDSN response body in tests 4–5, proving schema reuse.
4. **`fetch` — happy path.** Monkeypatch `httpx.get` to return a fake response
   whose `.json()` is the FDSN fixture and `.raise_for_status()` is a no-op;
   assert `fetch()` returns the parsed events and that the URL hit was
   `FDSN_QUERY_URL`.
5. **`fetch` — fallback.** Monkeypatch `httpx.get` so the FDSN URL raises
   `httpx.HTTPError` (or returns a response whose `raise_for_status` raises) and
   the feed URL returns the feed fixture; assert events still come back and the
   feed URL was used.
6. **`fetch` — `since` mapping.** With `since=None`, capture the `params` passed
   to `httpx.get` and assert `starttime` is ~`window_days` ago (within a tolerance
   window); with an explicit `since`, assert `starttime` equals that value and the
   post-filter retains only `occurred_at >= since`.

## Out of scope (later phases)

- Historical backfill / time-window chunking (Phase 1).
- New metadata fields / schema changes (Phase 2).
- `GET /events` filtering and `/events/count` (Phase 3).
- ShakeMap/PAGER/DYFI products (Phase 4).
- Scheduled polling / `updatedafter` watermark (Phase 5).
