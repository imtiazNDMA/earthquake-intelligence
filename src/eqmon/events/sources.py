"""Seismic event sources. USGSSource (Secondary) and METSource (Primary, the
Pakistan MET Department feed) are both implemented behind the SeismicSource
protocol. parse_usgs and parse_met are pure (no network) for testability."""
from __future__ import annotations
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from ..config import COVERAGE_BBOX

logger = logging.getLogger("uvicorn.error")

USGS_FEED_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)

# Pakistan MET Department seismic catalog (full catalog per call, bearer auth).
# HTTPS so the bearer token is never sent in cleartext.
PMD_API_URL = "https://weather.gov.pk/api/seismic-events"

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


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _parse_coord(raw, is_lat: bool) -> float | None:
    """Parse a PMD coordinate string into a signed decimal degree.

    PMD coordinates are dirty: a number plus an optional hemisphere suffix
    (``"24.87 N"``, ``"63.18 E"``) but also missing spaces (``"30.50N"``),
    lowercase suffixes, comma decimals (``"73,20 E"``), and plain signed
    decimals with no suffix at all (newer rows). Strategy: normalise the comma,
    pull the first number out, then sign it by the hemisphere letter if present.
    Returns None when no number can be extracted.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".")
    if not s:
        return None
    m = _NUM.search(s)
    if m is None:
        return None
    try:
        v = float(m.group())
    except ValueError:
        return None
    up = s.upper()
    if any(c in up for c in ("N", "S", "E", "W")):
        negative = ("S" in up) if is_lat else ("W" in up)
        return -abs(v) if negative else abs(v)
    return v  # plain signed decimal, no hemisphere suffix


def _parse_float(raw) -> float | None:
    """Pull the first number out of a possibly-dirty PMD numeric field."""
    if raw is None:
        return None
    m = _NUM.search(str(raw).replace(",", "."))
    if m is None:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _met_datetime(date_str, time_str) -> datetime | None:
    """Combine PMD ``event_date`` + ``event_time`` into a UTC datetime.

    PMD origin times carry no tz marker but are UTC (confirmed by cross-checking
    a shared event against USGS — they matched within seconds). Returns None if
    the date cannot be parsed.
    """
    if not date_str:
        return None
    combined = f"{date_str} {time_str or '00:00:00'}"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(combined, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_met(payload: dict) -> list[RawEvent]:
    """Map the PMD ``{status, message, data: [...]}`` response into RawEvents.

    Defensive by necessity (the feed has malformed coordinates, magnitudes, and
    dates): a row is skipped when its id, magnitude, or coordinates are missing
    or unparseable, when coordinates fall outside valid lat/lon ranges, or when
    it falls outside the Coverage Region. Depth defaults to 0.0 when absent.
    """
    out: list[RawEvent] = []
    for r in payload.get("data", []):
        eid = r.get("id")
        lat = _parse_coord(r.get("latitude"), is_lat=True)
        lon = _parse_coord(r.get("longitude"), is_lat=False)
        mag = _parse_float(r.get("magnitude"))
        if eid is None or lat is None or lon is None or mag is None:
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            continue
        if not _in_region(lon, lat):
            continue
        occurred_at = _met_datetime(r.get("event_date"), r.get("event_time"))
        if occurred_at is None:
            continue
        depth = _parse_float(r.get("depth"))
        out.append(RawEvent(
            source="MET",
            source_event_id=str(eid),
            occurred_at=occurred_at,
            magnitude=float(mag),
            depth_km=float(depth) if depth is not None else 0.0,
            lon=float(lon),
            lat=float(lat),
            place=r.get("region"),
            event_type=r.get("mode"),
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

    Fetches the full PMD catalog (bearer-authenticated) each call and maps it via
    parse_met. URL/token default to the PMD_API_URL/PMD_API_TOKEN environment
    variables (loaded from .env) so credentials stay out of the codebase.
    """
    name = "MET"

    def __init__(self, url: str | None = None, token: str | None = None,
                 timeout: float = 15.0):
        self.url = url or os.environ.get("PMD_API_URL", PMD_API_URL)
        self.token = token or os.environ.get("PMD_API_TOKEN")
        self.timeout = timeout

    def fetch(self, since: datetime | None = None,
              updatedafter: datetime | None = None) -> list[RawEvent]:
        """Fetch the PMD catalog and map to RawEvents.

        PMD returns the whole catalog every call — there is no server-side time
        filter, and created_at/updated_at are largely null — so `updatedafter`
        is unused; incremental dedup happens via upsert ON CONFLICT in ingest().
        Returns [] on HTTP error (non-fatal, mirrors USGSSource behaviour).
        When `since` is given, post-filters to events at or after it.
        """
        headers = {"Accept": "application/json"}
        if self.token:
            # Never transmit the bearer token over a non-HTTPS scheme.
            if self.url.lower().startswith("https://"):
                headers["Authorization"] = f"Bearer {self.token}"
            else:
                logger.warning(
                    "MET token not sent: %s is not HTTPS", self.url)
        try:
            resp = httpx.get(self.url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            events = parse_met(resp.json())
        except httpx.HTTPError:
            return []
        if since is not None:
            events = [e for e in events if e.occurred_at >= since]
        return events
