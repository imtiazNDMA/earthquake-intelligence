"""Validated, model-independent event catalog search contract."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVENT_SEARCH_SCHEMA_VERSION = "1.0"


class EventSearchSpec(BaseModel):
    """Complete deterministic input surface for catalog search.

    Radius is geodesic distance from ``center_lon``/``center_lat`` to each
    event point. Named-place interpretation happens before this contract.
    """

    min_magnitude: float | None = Field(
        None, ge=-1.0, le=10.0, description="Inclusive minimum magnitude.")
    max_magnitude: float | None = Field(
        None, ge=-1.0, le=10.0, description="Inclusive maximum magnitude.")
    source: Literal["PMD", "USGS", "MANUAL"] | None = Field(
        None, description=(
            "Canonical event source. Use uppercase PMD, USGS, or MANUAL exactly. "
            "Manually entered events map to MANUAL."
        ))
    search: str | None = Field(
        None, max_length=200, description="Case-insensitive substring of event place.")
    occurred_after: datetime | None = Field(
        None, description="Inclusive lower event-time bound; ISO 8601 with timezone.")
    occurred_before: datetime | None = Field(
        None, description="Inclusive upper event-time bound; ISO 8601 with timezone.")
    center_lon: float | None = Field(
        None, ge=-180.0, le=180.0,
        description="WGS84 longitude in decimal degrees; east is positive.")
    center_lat: float | None = Field(
        None, ge=-90.0, le=90.0,
        description="WGS84 latitude in decimal degrees; north is positive.")
    radius_km: float | None = Field(
        None, gt=0.0, le=5000.0,
        description="Geodesic search radius in kilometers; requires center coordinates.")
    event_kind: Literal["all", "mainshocks", "aftershocks"] = Field(
        "all", description="Use mainshocks or aftershocks only when explicitly requested.")
    limit: int = Field(20, ge=1, le=200, description="Maximum events to return.")
    offset: int = Field(0, ge=0, description="Pagination offset.")
    orderby: Literal["time", "time-asc", "magnitude"] = Field(
        "time", description=(
            "Sort order: time is newest first, time-asc is oldest first, and "
            "magnitude is largest first."
        ))

    @field_validator("occurred_after", "occurred_before")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("datetime must include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "EventSearchSpec":
        if (self.min_magnitude is not None and self.max_magnitude is not None
                and self.min_magnitude > self.max_magnitude):
            raise ValueError("min_magnitude must not exceed max_magnitude")
        if (self.occurred_after is not None and self.occurred_before is not None
                and self.occurred_after > self.occurred_before):
            raise ValueError("occurred_after must not exceed occurred_before")

        spatial = (self.center_lon, self.center_lat, self.radius_km)
        if any(value is not None for value in spatial) and not all(
                value is not None for value in spatial):
            raise ValueError(
                "center_lon, center_lat, and radius_km must be provided together"
            )
        return self
    model_config = ConfigDict(extra="forbid")
