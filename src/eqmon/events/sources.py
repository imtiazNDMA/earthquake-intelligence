"""Seismic event sources. USGSSource (Secondary) and PMDSource (Primary, the
PMD feed) are both implemented behind the SeismicSource
protocol. parse_usgs and parse_pmd are pure (no network) for testability."""
from __future__ import annotations
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Protocol

import httpx

from ..config import COVERAGE_BBOX

logger = logging.getLogger("uvicorn.error")

USGS_FEED_URL = (
    "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
)

# PMD seismic catalog (full catalog per call, bearer auth).
# HTTPS so the bearer token is never sent in cleartext.
PMD_API_URL = "https://weather.gov.pk/api/seismic-events"

FDSN_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
FDSN_COUNT_URL = "https://earthquake.usgs.gov/fdsnws/event/1/count"
DEFAULT_WINDOW_DAYS = 30
_CHUNK_DAYS = 1  # split large time windows into 1-day chunks to stay under 20k limit
_HISTORICAL_CHUNK_DAYS = 3653
MAX_REJECT_RECORD_BYTES = 16 * 1024
MAX_REJECT_METADATA_BYTES = 4 * 1024


@dataclass(frozen=True)
class RawEvent:
    source: str
    source_event_id: str
    occurred_at: datetime
    magnitude: float
    depth_km: float | None
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


class RejectReason(StrEnum):
    INVALID_PAYLOAD_SHAPE = "invalid_payload_shape"
    INVALID_RECORD_SHAPE = "invalid_record_shape"
    MISSING_EVENT_ID = "missing_event_id"
    MISSING_COORDINATES = "missing_coordinates"
    INVALID_COORDINATES = "invalid_coordinates"
    COORDINATE_OUT_OF_RANGE = "coordinate_out_of_range"
    MISSING_MAGNITUDE = "missing_magnitude"
    INVALID_MAGNITUDE = "invalid_magnitude"
    MAGNITUDE_OUT_OF_RANGE = "magnitude_out_of_range"
    MISSING_ORIGIN_TIME = "missing_origin_time"
    INVALID_ORIGIN_TIME = "invalid_origin_time"
    ORIGIN_TIME_BEFORE_MINIMUM = "origin_time_before_minimum"
    ORIGIN_TIME_IN_FUTURE = "origin_time_in_future"
    INVALID_DEPTH = "invalid_depth"
    OUTSIDE_COVERAGE = "outside_coverage"


@dataclass(frozen=True)
class ParserReject:
    source: str
    reason_code: RejectReason
    source_event_id: str | None
    parser_version: str
    payload_sha256: str
    source_record: Any
    retrieval_metadata: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_record",
            _bounded_json(self.source_record, MAX_REJECT_RECORD_BYTES),
        )
        object.__setattr__(
            self, "retrieval_metadata",
            _bounded_json(self.retrieval_metadata, MAX_REJECT_METADATA_BYTES),
        )


@dataclass(frozen=True)
class ParseResult:
    events: list[RawEvent]
    rejects: list[ParserReject]


FetchBatch = ParseResult


class SeismicSource(Protocol):
    name: str
    def fetch(self, since: datetime | None = None,
              updatedafter: datetime | None = None) -> list[RawEvent]: ...


def _in_region(lon: float, lat: float) -> bool:
    minx, miny, maxx, maxy = COVERAGE_BBOX
    return minx <= lon <= maxx and miny <= lat <= maxy


def _utc_from_epoch_ms(value: int | float) -> datetime:
    """Convert Unix milliseconds without Windows' pre-1970 timestamp limit."""
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=value)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def _bounded_json(value: Any, max_bytes: int) -> Any:
    encoded = _canonical_json_bytes(value)
    if len(encoded) <= max_bytes:
        return value
    return {"truncated": True, "original_bytes": len(encoded)}


def _payload_sha256(record: Any) -> str:
    encoded = _canonical_json_bytes(record)
    return hashlib.sha256(encoded).hexdigest()


def _parser_reject(source: str, parser_version: str, reason: RejectReason,
                   record: Any, retrieval_metadata: dict[str, Any] | None,
                   source_event_id: Any = None) -> ParserReject:
    return ParserReject(
        source=source,
        reason_code=reason,
        source_event_id=(str(source_event_id) if source_event_id is not None else None),
        parser_version=parser_version,
        payload_sha256=_payload_sha256(record),
        source_record=record,
        retrieval_metadata=dict(retrieval_metadata or {}),
    )


def parse_usgs_result(geojson: dict, *,
                      retrieval_metadata: dict[str, Any] | None = None) -> ParseResult:
    events: list[RawEvent] = []
    rejects: list[ParserReject] = []
    parser_version = "usgs-1"
    features = geojson.get("features") if isinstance(geojson, dict) else None
    if not isinstance(features, list):
        return ParseResult([], [_parser_reject(
            "USGS", parser_version, RejectReason.INVALID_PAYLOAD_SHAPE,
            geojson, retrieval_metadata,
        )])
    for feature in features:
        if not isinstance(feature, dict):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_RECORD_SHAPE,
                feature, retrieval_metadata,
            ))
            continue
        eid = feature.get("id")
        if eid is None:
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.MISSING_EVENT_ID,
                feature, retrieval_metadata,
            ))
            continue
        props = feature.get("properties")
        geom = feature.get("geometry")
        props = props if isinstance(props, dict) else {}
        geom = geom if isinstance(geom, dict) else {}
        coords = geom.get("coordinates")
        if not isinstance(coords, (list, tuple)) or len(coords) < 2:
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.MISSING_COORDINATES,
                feature, retrieval_metadata, eid,
            ))
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_COORDINATES,
                feature, retrieval_metadata, eid,
            ))
            continue
        if not math.isfinite(lon) or not math.isfinite(lat):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_COORDINATES,
                feature, retrieval_metadata, eid,
            ))
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.COORDINATE_OUT_OF_RANGE,
                feature, retrieval_metadata, eid,
            ))
            continue
        mag_value = props.get("mag")
        if mag_value is None:
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.MISSING_MAGNITUDE,
                feature, retrieval_metadata, eid,
            ))
            continue
        try:
            mag = float(mag_value)
        except (TypeError, ValueError):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_MAGNITUDE,
                feature, retrieval_metadata, eid,
            ))
            continue
        if not math.isfinite(mag):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_MAGNITUDE,
                feature, retrieval_metadata, eid,
            ))
            continue
        if not (_PMD_MAG_MIN <= mag <= _PMD_MAG_MAX):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.MAGNITUDE_OUT_OF_RANGE,
                feature, retrieval_metadata, eid,
            ))
            continue
        time_ms = props.get("time")
        if time_ms is None:
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.MISSING_ORIGIN_TIME,
                feature, retrieval_metadata, eid,
            ))
            continue
        try:
            occurred_at = _utc_from_epoch_ms(float(time_ms))
        except (TypeError, ValueError, OverflowError):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_ORIGIN_TIME,
                feature, retrieval_metadata, eid,
            ))
            continue
        if not _in_region(lon, lat):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.OUTSIDE_COVERAGE,
                feature, retrieval_metadata, eid,
            ))
            continue
        depth_value = coords[2] if len(coords) >= 3 else None
        try:
            depth = float(depth_value) if depth_value is not None else None
        except (TypeError, ValueError):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_DEPTH,
                feature, retrieval_metadata, eid,
            ))
            continue
        if depth is not None and not math.isfinite(depth):
            rejects.append(_parser_reject(
                "USGS", parser_version, RejectReason.INVALID_DEPTH,
                feature, retrieval_metadata, eid,
            ))
            continue
        updated_ms = props.get("updated")
        try:
            updated_at = (
                _utc_from_epoch_ms(float(updated_ms))
                if updated_ms is not None else None
            )
        except (TypeError, ValueError, OverflowError):
            updated_at = None
        events.append(RawEvent(
            source="USGS",
            source_event_id=str(eid),
            occurred_at=occurred_at,
            magnitude=mag,
            depth_km=depth,
            lon=lon,
            lat=lat,
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
            updated_at=updated_at,
        ))
    return ParseResult(events, rejects)


def parse_usgs(geojson: dict) -> list[RawEvent]:
    return parse_usgs_result(geojson).events


_NUM = re.compile(r"-?\d+(?:\.\d+)?")

# Plausible bounds for sanity-checking PMD's dirty numeric fields.
_PMD_MAG_MIN, _PMD_MAG_MAX = -1.0, 10.0
_PMD_DEPTH_MAX = 800.0  # km; deepest recorded earthquakes are ~700 km


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


def _pmd_datetime(date_str, time_str) -> datetime | None:
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


def parse_pmd_result(payload: dict, *,
                     retrieval_metadata: dict[str, Any] | None = None,
                     now: datetime | None = None) -> ParseResult:
    """Map the PMD ``{status, message, data: [...]}`` response into RawEvents.

    Defensive by necessity (the feed has malformed coordinates, magnitudes, and
    dates): a row is skipped when its id, magnitude, or coordinates are missing
    or unparseable, when coordinates fall outside valid lat/lon ranges, or when
    it falls outside the Coverage Region. Depth defaults to 0.0 when absent.
    """
    events: list[RawEvent] = []
    rejects: list[ParserReject] = []
    parser_version = "pmd-1"
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return ParseResult([], [_parser_reject(
            "PMD", parser_version, RejectReason.INVALID_PAYLOAD_SHAPE,
            payload, retrieval_metadata,
        )])
    current_time = now or datetime.now(timezone.utc)
    for r in rows:
        if not isinstance(r, dict):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.INVALID_RECORD_SHAPE,
                r, retrieval_metadata,
            ))
            continue
        eid = r.get("id")
        if eid is None:
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.MISSING_EVENT_ID,
                r, retrieval_metadata,
            ))
            continue
        lat = _parse_coord(r.get("latitude"), is_lat=True)
        lon = _parse_coord(r.get("longitude"), is_lat=False)
        if lat is None or lon is None:
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.INVALID_COORDINATES,
                r, retrieval_metadata, eid,
            ))
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.INVALID_COORDINATES,
                r, retrieval_metadata, eid,
            ))
            continue
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.COORDINATE_OUT_OF_RANGE,
                r, retrieval_metadata, eid,
            ))
            continue
        mag = _parse_float(r.get("magnitude"))
        if mag is None or not math.isfinite(mag):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.INVALID_MAGNITUDE,
                r, retrieval_metadata, eid,
            ))
            continue
        # Plausible magnitude range. PMD occasionally swaps the magnitude and
        # depth fields (e.g. magnitude="317", depth="4.4"); such rows are not
        # trustworthy, so skip them rather than ingest a bogus magnitude.
        if not (_PMD_MAG_MIN <= mag <= _PMD_MAG_MAX):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.MAGNITUDE_OUT_OF_RANGE,
                r, retrieval_metadata, eid,
            ))
            continue
        if not _in_region(lon, lat):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.OUTSIDE_COVERAGE,
                r, retrieval_metadata, eid,
            ))
            continue
        occurred_at = _pmd_datetime(r.get("event_date"), r.get("event_time"))
        if occurred_at is None:
            reason = (RejectReason.MISSING_ORIGIN_TIME
                      if not r.get("event_date") else RejectReason.INVALID_ORIGIN_TIME)
            rejects.append(_parser_reject(
                "PMD", parser_version, reason, r, retrieval_metadata, eid,
            ))
            continue
        if occurred_at < datetime(1900, 1, 1, tzinfo=timezone.utc):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.ORIGIN_TIME_BEFORE_MINIMUM,
                r, retrieval_metadata, eid,
            ))
            continue
        if occurred_at > current_time + timedelta(days=1):
            rejects.append(_parser_reject(
                "PMD", parser_version, RejectReason.ORIGIN_TIME_IN_FUTURE,
                r, retrieval_metadata, eid,
            ))
            continue
        depth = _parse_float(r.get("depth"))
        # Implausible depth (also from swapped/garbled fields) → unknown (0.0).
        if depth is None or not (0.0 <= depth <= _PMD_DEPTH_MAX):
            depth = 0.0
        events.append(RawEvent(
            source="PMD",
            source_event_id=str(eid),
            occurred_at=occurred_at,
            magnitude=float(mag),
            depth_km=float(depth),
            lon=float(lon),
            lat=float(lat),
            place=r.get("region"),
            event_type=r.get("mode"),
        ))
    return ParseResult(events, rejects)


def parse_pmd(payload: dict) -> list[RawEvent]:
    return parse_pmd_result(payload).events


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
                 count_url: str = FDSN_COUNT_URL,
                 feed_url: str = USGS_FEED_URL,
                 min_magnitude: float | None = None,
                 window_days: int = DEFAULT_WINDOW_DAYS,
                 timeout: float = 15.0):
        self.query_url = query_url
        self.count_url = count_url
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
        return self.fetch_batch(since, updatedafter=updatedafter).events

    def fetch_batch(self, since: datetime | None = None,
                    updatedafter: datetime | None = None) -> FetchBatch:
        """Fetch accepted observations and retain typed row-level rejects."""
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
                parsed = parse_usgs_result(
                    resp.json(), retrieval_metadata=self._retrieval_metadata(
                        self.query_url, params))
            except httpx.HTTPError:
                return self._fetch_chunked_batch(since)
            events = parsed.events
            if since is not None:
                events = [e for e in events if e.occurred_at >= since]
            return FetchBatch(events, parsed.rejects)
        return self._fetch_chunked_batch(since)

    @staticmethod
    def _retrieval_metadata(url: str, params: dict | None = None) -> dict[str, Any]:
        return {
            "url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            **(params or {}),
        }

    def fetch_range(self, start: datetime, end: datetime) -> list[RawEvent]:
        """Fetch an explicit historical interval without silently truncating it.

        Ten-year windows keep the request count reasonable. Each window is sized
        with the FDSN count endpoint and recursively divided when it exceeds the
        20,000-event query limit. Event IDs are deduplicated at window edges.
        Unlike the rolling sync path, source errors are allowed to propagate so
        a backfill cannot report success after substituting the one-day feed.
        """
        return self.fetch_range_batch(start, end).events

    def fetch_range_batch(self, start: datetime, end: datetime) -> FetchBatch:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("historical range requires timezone-aware datetimes")
        if end <= start:
            raise ValueError("historical range end must be after start")
        chunk_size = timedelta(days=_HISTORICAL_CHUNK_DAYS)
        events: list[RawEvent] = []
        rejects: list[ParserReject] = []
        seen: set[str] = set()
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + chunk_size, end)
            batch = self._fetch_sized_window_batch(cursor, chunk_end)
            rejects.extend(batch.rejects)
            for event in batch.events:
                if event.source_event_id not in seen:
                    seen.add(event.source_event_id)
                    events.append(event)
            cursor = chunk_end
        return FetchBatch(events, _deduplicate_rejects(rejects))

    def _fetch_sized_window_batch(self, start: datetime,
                                  end: datetime) -> FetchBatch:
        query_params = fdsn_query_params(
            starttime=start, endtime=end, bbox=COVERAGE_BBOX,
            minmagnitude=self.min_magnitude,
        )
        count_params = {
            key: value for key, value in query_params.items()
            if key not in {"format", "orderby", "limit"}
        }
        count_response = httpx.get(
            self.count_url, params=count_params, timeout=self.timeout)
        count_response.raise_for_status()
        count = int(count_response.text.strip())
        if count == 0:
            return FetchBatch([], [])
        if count > 20_000:
            if (end - start).total_seconds() <= 1:
                raise RuntimeError("USGS historical query cannot be split below one second")
            midpoint = start + (end - start) / 2
            left = self._fetch_sized_window_batch(start, midpoint)
            right = self._fetch_sized_window_batch(midpoint, end)
            return FetchBatch(
                left.events + right.events,
                _deduplicate_rejects(left.rejects + right.rejects),
            )
        response = httpx.get(
            self.query_url, params=query_params, timeout=self.timeout)
        response.raise_for_status()
        parsed = parse_usgs_result(
            response.json(), retrieval_metadata=self._retrieval_metadata(
                self.query_url, query_params))
        return FetchBatch(parsed.events, parsed.rejects)

    def _fetch_chunked_batch(self, since: datetime | None = None) -> FetchBatch:
        now = datetime.now(timezone.utc)
        start = since or (now - timedelta(days=self.window_days))
        chunks = max(1, math.ceil((now - start).total_seconds()
                                   / (_CHUNK_DAYS * 86400)))
        chunk_size = timedelta(days=_CHUNK_DAYS)
        all_events: list[RawEvent] = []
        rejects: list[ParserReject] = []
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
                parsed = parse_usgs_result(
                    resp.json(), retrieval_metadata=self._retrieval_metadata(
                        self.query_url, params))
                chunk_events = parsed.events
                rejects.extend(parsed.rejects)
            except httpx.HTTPError:
                # Any chunk failure: fall back to the 24h feed for the whole fetch.
                resp = httpx.get(self.feed_url, timeout=self.timeout)
                resp.raise_for_status()
                parsed = parse_usgs_result(
                    resp.json(), retrieval_metadata=self._retrieval_metadata(
                        self.feed_url))
                return FetchBatch(parsed.events, parsed.rejects)
            for e in chunk_events:
                if e.source_event_id not in seen:
                    seen.add(e.source_event_id)
                    all_events.append(e)
            cursor = chunk_end
        if since is not None:
            all_events = [e for e in all_events if e.occurred_at >= since]
        return FetchBatch(all_events, _deduplicate_rejects(rejects))


class PMDSource:
    """Primary Seismic Source (PMD).

    Fetches the full PMD catalog (bearer-authenticated) each call and maps it via
    parse_pmd. URL/token default to the PMD_API_URL/PMD_API_TOKEN environment
    variables (loaded from .env) so credentials stay out of the codebase.
    """
    name = "PMD"

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
        return self.fetch_batch(since, updatedafter=updatedafter).events

    def fetch_batch(self, since: datetime | None = None,
                    updatedafter: datetime | None = None) -> FetchBatch:
        headers = {"Accept": "application/json"}
        if self.token:
            # Never transmit the bearer token over a non-HTTPS scheme.
            if self.url.lower().startswith("https://"):
                headers["Authorization"] = f"Bearer {self.token}"
            else:
                logger.warning(
                    "PMD token not sent: %s is not HTTPS", self.url)
        try:
            resp = httpx.get(self.url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            parsed = parse_pmd_result(resp.json(), retrieval_metadata={
                "url": self.url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            })
        except httpx.HTTPError:
            return FetchBatch([], [])
        events = parsed.events
        if since is not None:
            events = [e for e in events if e.occurred_at >= since]
        return FetchBatch(events, parsed.rejects)


def _deduplicate_rejects(rejects: list[ParserReject]) -> list[ParserReject]:
    unique: dict[tuple[str, str, RejectReason, str], ParserReject] = {}
    for reject in rejects:
        key = (
            reject.source,
            reject.parser_version,
            reject.reason_code,
            reject.payload_sha256,
        )
        unique.setdefault(key, reject)
    return list(unique.values())
