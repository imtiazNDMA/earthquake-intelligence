"""Seismic event sources. USGSSource (Secondary) is fully implemented; METSource
(Primary) is a stub until the Pakistan MET feed format is known. parse_usgs is
pure (no network) for testability."""
from __future__ import annotations
import math
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
_CHUNK_DAYS = 1  # split large time windows into 1-day chunks to stay under 20k limit


@dataclass(frozen=True)
class RawEvent:
    source: str
    source_event_id: str
    occurred_at: datetime
    magnitude: float
    depth_km: float
    lon: float
    lat: float
    place: str | None = None
    mag_type: str | None = None
    event_type: str | None = None
    alert: str | None = None
    tsunami: int = 0
    sig: int | None = None
    review_status: str | None = None
    felt: int | None = None
    cdi: float | None = None
    mmi_report: float | None = None
    gap: float | None = None
    nst: int | None = None
    url: str | None = None
    detail_url: str | None = None
    updated_at: datetime | None = None


class SeismicSource(Protocol):
    name: str
    def fetch(self, since: datetime | None = None,
              updatedafter: datetime | None = None) -> list[RawEvent]: ...


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
        updated_ms = props.get("updated")
        out.append(RawEvent(
            source="USGS",
            source_event_id=str(eid),
            occurred_at=datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc),
            magnitude=float(mag),
            depth_km=float(depth),
            lon=float(lon),
            lat=float(lat),
            place=props.get("place"),
            mag_type=props.get("magType"),
            event_type=props.get("type"),
            alert=props.get("alert"),
            tsunami=props.get("tsunami", 0),
            sig=props.get("sig"),
            review_status=props.get("status"),
            felt=props.get("felt"),
            cdi=props.get("cdi"),
            mmi_report=props.get("mmi"),
            gap=props.get("gap"),
            nst=props.get("nst"),
            url=props.get("url"),
            detail_url=props.get("detail"),
            updated_at=(
                datetime.fromtimestamp(updated_ms / 1000.0, tz=timezone.utc)
                if updated_ms is not None else None
            ),
        ))
    return out


def fdsn_query_params(*, starttime: datetime | None = None,
                      bbox: tuple[float, float, float, float],
                      endtime: datetime | None = None,
                      updatedafter: datetime | None = None,
                      minmagnitude: float | None = None,
                      limit: int = 20000,
                      eventtype: str | None = "earthquake") -> dict:
    """Build FDSN `event/query` parameters for a region + time window.

    `bbox` is (min lon, min lat, max lon, max lat) — matches config.COVERAGE_BBOX.
    `starttime` is optional (incremental sync uses `updatedafter` instead);
    formatted without a tz suffix (FDSN assumes UTC). `endtime` is optional —
    without it the API defaults to the present time. `limit` is capped at
    FDSN's hard max (20000); `orderby=time` keeps the most recent events if
    the window ever saturates. `eventtype` defaults to "earthquake" to filter
    out quarry blasts / explosions.
    """
    minx, miny, maxx, maxy = bbox
    params: dict = {
        "format": "geojson",
        "minlatitude": miny,
        "maxlatitude": maxy,
        "minlongitude": minx,
        "maxlongitude": maxx,
        "orderby": "time",
        "limit": limit,
    }
    if starttime is not None:
        params["starttime"] = starttime.strftime("%Y-%m-%dT%H:%M:%S")
    if endtime is not None:
        params["endtime"] = endtime.strftime("%Y-%m-%dT%H:%M:%S")
    if updatedafter is not None:
        params["updatedafter"] = updatedafter.strftime("%Y-%m-%dT%H:%M:%S")
    if minmagnitude is not None:
        params["minmagnitude"] = minmagnitude
    if eventtype is not None:
        params["eventtype"] = eventtype
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

    def fetch_event(self, event_id: str) -> dict | None:
        """Fetch a single event's full GeoJSON detail from USGS FDSN by
        source_event_id. Returns the feature dict (which includes
        ``products`` — moment tensor, shakemap, DYFI, etc.) or None on
        HTTP error."""
        try:
            resp = httpx.get(self.query_url, params={
                "format": "geojson",
                "eventid": event_id,
            }, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None

    def fetch(self, since: datetime | None = None,
              updatedafter: datetime | None = None) -> list[RawEvent]:
        """Fetch events from USGS FDSN.

        When `updatedafter` is given (incremental sync), performs a single query
        — the time range is expected to be small (minutes to hours since last
        sync). Falls back to time-window chunking on HTTP error.

        When `updatedafter` is *not* given, splits the time window into 1-day
        chunks to stay under the 20k event-per-query limit. Falls back to the
        24h summary feed on HTTP error.
        """
        if updatedafter is not None:
            try:
                params = fdsn_query_params(
                    bbox=COVERAGE_BBOX,
                    updatedafter=updatedafter,
                    minmagnitude=self.min_magnitude,
                )
                resp = httpx.get(self.query_url, params=params,
                                 timeout=self.timeout)
                resp.raise_for_status()
                events = parse_usgs(resp.json())
            except httpx.HTTPError:
                return self._fetch_chunked(since)
            if since is not None:
                events = [e for e in events if e.occurred_at >= since]
            return events
        return self._fetch_chunked(since)

    def _fetch_chunked(self, since: datetime | None = None) -> list[RawEvent]:
        now = datetime.now(timezone.utc)
        start = since or (now - timedelta(days=self.window_days))
        chunks = max(1, math.ceil((now - start).total_seconds()
                                   / (_CHUNK_DAYS * 86400)))
        chunk_size = timedelta(days=_CHUNK_DAYS)
        all_events: list[RawEvent] = []
        seen: set[str] = set()
        cursor = start
        for _ in range(chunks):
            chunk_end = min(cursor + chunk_size, now)
            try:
                params = fdsn_query_params(starttime=cursor, bbox=COVERAGE_BBOX,
                                           endtime=chunk_end,
                                           minmagnitude=self.min_magnitude)
                resp = httpx.get(self.query_url, params=params,
                                 timeout=self.timeout)
                resp.raise_for_status()
                chunk_events = parse_usgs(resp.json())
            except httpx.HTTPError:
                # Any chunk failure: fall back to the 24h feed for the whole fetch.
                resp = httpx.get(self.feed_url, timeout=self.timeout)
                resp.raise_for_status()
                return parse_usgs(resp.json())
            for e in chunk_events:
                if e.source_event_id not in seen:
                    seen.add(e.source_event_id)
                    all_events.append(e)
            cursor = chunk_end
        if since is not None:
            all_events = [e for e in all_events if e.occurred_at >= since]
        return all_events


class METSource:
    """Primary Seismic Source (Pakistan MET Department).

    Stub: the feed endpoint and format are not yet known. Implement `fetch` to
    return RawEvent(source="MET", ...) once the format is provided.
    """
    name = "MET"

    def fetch(self, since: datetime | None = None,
              updatedafter: datetime | None = None) -> list[RawEvent]:
        raise NotImplementedError("MET feed format not yet defined")
