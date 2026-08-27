"""Validated, bounded browser workspace context for conversational workflows."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (BaseModel, ConfigDict, Field, StringConstraints,
                      field_validator, model_validator)

ANALYST_CONTEXT_SCHEMA_VERSION = "1.0"
MAX_CONTEXT_BYTES = 16 * 1024
MAX_CONTEXT_AGE_S = 30
MAX_LAYERS_PER_GROUP = 64

ShortId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                            max_length=120)]
ShortLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1,
                                               max_length=160)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MapContext(StrictModel):
    mode: Literal["2d", "3d"]
    center: tuple[float, float]
    zoom: float = Field(ge=0, le=24, strict=True)
    bearing: float = Field(ge=0, lt=360, strict=True)
    pitch: float = Field(ge=0, le=70, strict=True)
    basemap: ShortLabel | None = None

    @field_validator("center")
    @classmethod
    def valid_center(cls, value: tuple[float, float]) -> tuple[float, float]:
        lon, lat = value
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("map center is outside geographic bounds")
        return value


class SelectionContext(StrictModel):
    event_id: ShortId | None = None
    mmi_level: int | None = Field(default=None, ge=1, le=12, strict=True)
    sidebar_section: Literal[
        "event", "catalog", "mapEvents", "aftershock", "landslide", "infra",
        "dashboard", "config",
    ] | None = None


class LayerContext(StrictModel):
    id: ShortId
    visible: bool = Field(strict=True)
    opacity: float | None = Field(default=None, ge=0, le=1, strict=True)


class PgaLayerContext(StrictModel):
    visible: bool = Field(strict=True)
    return_period: int | None = Field(default=None, ge=1, le=100_000, strict=True)
    opacity: float | None = Field(default=None, ge=0, le=1, strict=True)


class BuildingLayerContext(StrictModel):
    visible: bool = Field(strict=True)
    selected_district: ShortId | None = None
    opacity: float | None = Field(default=None, ge=0, le=1, strict=True)


class MmiLayerContext(StrictModel):
    visible: bool = Field(strict=True)
    opacity: float | None = Field(default=None, ge=0, le=1, strict=True)


class LayersContext(StrictModel):
    reference: list[LayerContext] = Field(
        default_factory=list, max_length=MAX_LAYERS_PER_GROUP)
    landslides: list[LayerContext] = Field(
        default_factory=list, max_length=MAX_LAYERS_PER_GROUP)
    pga: PgaLayerContext | None = None
    buildings: BuildingLayerContext | None = None
    mmi: MmiLayerContext | None = None


class EventFiltersContext(StrictModel):
    sources: list[Literal["PMD", "USGS", "MANUAL"]] = Field(
        default_factory=list, max_length=3)
    minimum_magnitude: float | None = Field(default=None, ge=-2, le=10, strict=True)
    maximum_magnitude: float | None = Field(default=None, ge=-2, le=10, strict=True)
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: Annotated[str, StringConstraints(strip_whitespace=True,
                                              max_length=120)] | None = None
    time_window_indices: tuple[int, int] | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("filter datetimes require a timezone")
        return value

    @model_validator(mode="after")
    def valid_ranges(self):
        if (self.minimum_magnitude is not None
                and self.maximum_magnitude is not None
                and self.minimum_magnitude > self.maximum_magnitude):
            raise ValueError("minimum magnitude exceeds maximum magnitude")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from exceeds date_to")
        if self.time_window_indices is not None:
            start, end = self.time_window_indices
            if start < 0 or end < start or end > 100_000:
                raise ValueError("invalid time window indices")
        return self


class DisplayContext(StrictModel):
    theme: Literal["light", "dark"]
    reduced_motion: bool = Field(strict=True)


class AnalystContextV1(StrictModel):
    schema_version: Literal[ANALYST_CONTEXT_SCHEMA_VERSION]
    captured_at: datetime
    map: MapContext
    selection: SelectionContext = Field(default_factory=SelectionContext)
    layers: LayersContext = Field(default_factory=LayersContext)
    event_filters: EventFiltersContext = Field(default_factory=EventFiltersContext)
    display: DisplayContext

    @field_validator("captured_at")
    @classmethod
    def recent_timezone_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("captured_at requires a timezone")
        now = datetime.now(timezone.utc)
        age = (now - value.astimezone(timezone.utc)).total_seconds()
        if age > MAX_CONTEXT_AGE_S:
            raise ValueError("analyst context is stale")
        if age < -5:
            raise ValueError("analyst context is from the future")
        return value

    @model_validator(mode="after")
    def bounded_payload(self):
        if len(canonical_context_json(self)) > MAX_CONTEXT_BYTES:
            raise ValueError(f"analyst context exceeds {MAX_CONTEXT_BYTES} bytes")
        return self


def canonical_context_json(context: AnalystContextV1) -> bytes:
    payload = json.dumps(context.model_dump(mode="json"), ensure_ascii=True,
                         sort_keys=True, separators=(",", ":"))
    return payload.encode("utf-8")


def context_fingerprint(context: AnalystContextV1 | None) -> dict:
    """Audit metadata that records context use without retaining its contents."""
    if context is None:
        return {"context_present": False}
    payload = canonical_context_json(context)
    return {
        "context_present": True,
        "context_schema_version": context.schema_version,
        "context_sha256": hashlib.sha256(payload).hexdigest(),
        "context_bytes": len(payload),
        "context_fields": sorted(context.model_fields_set),
    }
