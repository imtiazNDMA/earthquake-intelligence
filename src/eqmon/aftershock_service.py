"""Aftershock forecasting orchestration, independent of the API.

`aftershock.py` owns the seismology. This module owns the sequence around it:
resolve the mainshock from either a catalog id or inline parameters, look up the
tectonic zone containing it, and fall back to latitude bands when no zone
matches.

The zone lookup is deliberately best-effort. Region detection already has a
latitude-band fallback, so a missing or unreadable `tectonic_zone` table should
downgrade the forecast rather than fail it. The lookup runs inside a savepoint
so that a failure cannot abort a transaction the caller is still using — the
handler used to get that isolation for free by opening a second connection,
which a service taking an explicit connection cannot do.
"""
from __future__ import annotations

import logging

import psycopg
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import aftershock as ashock

logger = logging.getLogger("uvicorn.error")


class EventNotFoundError(LookupError):
    """The requested catalog event does not exist."""


class AftershockForecastInput(BaseModel):
    """Validated request for a catalog event or one inline mainshock."""

    event_id: int | None = Field(
        None, ge=1, description="Catalog id of the mainshock.")
    magnitude: float | None = Field(
        None, ge=0.0, le=10.0, description="Mainshock magnitude.")
    lat: float | None = Field(
        None, ge=-90.0, le=90.0,
        description="WGS84 latitude, north positive.")
    lon: float | None = Field(
        None, ge=-180.0, le=180.0,
        description="WGS84 longitude, east positive.")

    @model_validator(mode="after")
    def require_one_complete_mode(self) -> "AftershockForecastInput":
        inline = (self.magnitude, self.lat, self.lon)
        if self.event_id is not None:
            if any(value is not None for value in inline):
                raise ValueError(
                    "provide event_id or magnitude+lat+lon, but not both")
        elif not all(value is not None for value in inline):
            raise ValueError("provide event_id or magnitude+lat+lon")
        return self

    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, strict=True)


def lookup_zone_name(conn: psycopg.Connection, lon: float,
                     lat: float) -> str | None:
    """Name of the tectonic zone containing a point, or None.

    Never raises: callers treat a missing zone and an unreadable zone table the
    same way, by falling back to latitude bands.
    """
    try:
        with conn.transaction():
            row = conn.execute(
                "SELECT name FROM tectonic_zone "
                "WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) "
                "LIMIT 1",
                (lon, lat),
            ).fetchone()
    except psycopg.Error as exc:
        logger.warning("tectonic zone lookup failed, using latitude bands: %s", exc)
        return None
    return row[0] if row is not None else None


def compute_forecast(conn: psycopg.Connection, *, event_id: int | None = None,
                     magnitude: float | None = None, lat: float | None = None,
                     lon: float | None = None) -> dict:
    """Aftershock probability table for a catalog event or an inline point.

    Provide `event_id`, or all of `magnitude`, `lat`, and `lon`.
    """
    request = AftershockForecastInput(
        event_id=event_id, magnitude=magnitude, lat=lat, lon=lon)
    event_id = request.event_id
    magnitude, lat, lon = request.magnitude, request.lat, request.lon

    if event_id is not None:
        from .events.repo import get_event

        event = get_event(conn, event_id)
        if event is None:
            raise EventNotFoundError(f"event {event_id} not found")
        main_magnitude = event["magnitude"]
        lat, lon = event["lat"], event["lon"]
        event_info = {
            "id": event["id"], "magnitude": event["magnitude"],
            "lat": event["lat"], "lon": event["lon"],
            "place": event.get("place"), "source": event["source"],
            "occurred_at": (event["occurred_at"].isoformat()
                             if event.get("occurred_at") else None),
        }
    else:
        # The input contract proves all three inline values are present.
        assert magnitude is not None and lat is not None and lon is not None
        main_magnitude = magnitude
        event_info = None

    zone_name = lookup_zone_name(conn, lon, lat)
    region = ashock.detect_region(lat, lon, zone_name=zone_name)

    result = ashock.compute_table(main_magnitude, region)
    result["event"] = event_info
    if zone_name:
        result["zone_name"] = zone_name
    return result
