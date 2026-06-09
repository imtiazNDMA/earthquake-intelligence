"""Seismic event sources. USGSSource (Secondary) is fully implemented; METSource
(Primary) is a stub until the Pakistan MET feed format is known. parse_usgs is
pure (no network) for testability."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx

from ..config import COVERAGE_BBOX

USGS_FEED_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)


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


class METSource:
    """Primary Seismic Source (Pakistan MET Department).

    Stub: the feed endpoint and format are not yet known. Implement `fetch` to
    return RawEvent(source="MET", ...) once the format is provided.
    """
    name = "MET"

    def fetch(self, since: datetime | None = None) -> list[RawEvent]:
        raise NotImplementedError("MET feed format not yet defined")
