"""Seismic event sources. USGSSource (Secondary) is fully implemented; METSource
(Primary) is a stub until the Pakistan MET feed format is known. parse_usgs is
pure (no network) for testability."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from ..config import COVERAGE_BBOX

USGS_FEED_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)

FDSN_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
DEFAULT_WINDOW_DAYS = 30


@dataclass(frozen=True)
class RawEvent:
    source: str
    source_event_id: str
    occurred_at: datetime
    magnitude: float
    depth_km: float
    lon: float
    lat: float


class SeismicSource(Protocol):
    name: str
    def fetch(self, since: datetime | None = None) -> list[RawEvent]: ...


def _in_region(lon: float, lat: float) -> bool:
    minx, miny, maxx, maxy = COVERAGE_BBOX
    return minx <= lon <= maxx and miny <= lat <= maxy


def parse_usgs(geojson: dict) -> list[RawEvent]:
    out: list[RawEvent] = []
    for f in geojson.get("features", []):
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 3:
            continue
        lon, lat, depth = coords[0], coords[1], coords[2]
        mag = props.get("mag")
        time_ms = props.get("time")
        eid = f.get("id")
        if mag is None or time_ms is None or eid is None:
            continue
        if not _in_region(lon, lat):
            continue
        out.append(RawEvent(
            source="USGS",
            source_event_id=str(eid),
            occurred_at=datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc),
            magnitude=float(mag),
            depth_km=float(depth),
            lon=float(lon),
            lat=float(lat),
        ))
    return out


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


class METSource:
    """Primary Seismic Source (Pakistan MET Department).

    Stub: the feed endpoint and format are not yet known. Implement `fetch` to
    return RawEvent(source="MET", ...) once the format is provided.
    """
    name = "MET"

    def fetch(self, since: datetime | None = None) -> list[RawEvent]:
        raise NotImplementedError("MET feed format not yet defined")
