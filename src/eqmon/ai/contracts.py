"""Versioned, model-facing tool result schemas.

Domain functions return whatever is convenient for the API: 28 columns per
event, raw upstream product trees, thousand-point scatter arrays. None of that
is safe to hand a model, and the reason is not only context size. Every field a
model can see is a field it can quote back as fact, so the allowlist *is* the
safety boundary and belongs in one reviewable place rather than distributed
across prompts.

Two rules hold across every contract here:

- **Project, never truncate silently.** A capped list says it was capped and
  still reports the true total, so a shortened list cannot be read as a smaller
  catalog.
- **Failures are typed.** `ToolFailure` carries a machine-readable code the
  agent loop can branch on. A tool that returns an error string invites the
  model to interpret prose, which is the thing this layer exists to prevent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

CONTRACTS_SCHEMA_VERSION = "1.0"

# A context budget, not a page size. `EventSearchSpec` admits limit=200, which
# is right for a UI table and far too much for a prompt.
MAX_EVENTS_IN_CONTEXT = 25

# Hard ceiling on any single projection handed to a model. Exceeding it is a
# bug in a contract, not something to trim at runtime.
MAX_PROJECTION_BYTES = 32_000

FailureCode = Literal[
    "not_found",
    "ambiguous",
    "invalid_request",
    "upstream_unavailable",
    "partial",
]


class ToolFailure(Exception):
    """A tool refused or could not complete, with a code the loop can branch on."""

    def __init__(self, code: FailureCode, message: str, *,
                 detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def as_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.detail}


class _Projection(BaseModel):
    """Base for every model-facing payload."""
    model_config = ConfigDict(extra="forbid")


class EventSummary(_Projection):
    """The allowlisted view of a catalog event.

    Deliberately excluded: `usgs_detail` (an unvalidated upstream product tree),
    `url` and `detail_url` (a model presenting a link as a citation is exactly
    the failure the claim ledger exists to prevent), and the ingest bookkeeping
    columns, which carry no analytical meaning.
    """
    id: int
    magnitude: float
    mag_type: str | None = None
    depth_km: float | None = None
    lat: float
    lon: float
    place: str | None = None
    occurred_at: datetime
    source: str
    is_mainshock: bool | None = None


class CatalogCoverage(_Projection):
    """Observed extent of the catalog.

    Present so that "no events found" cannot be read as "no events occurred".
    `completeness` is never asserted: the catalog records what was ingested, not
    what happened.
    """
    earliest_occurred_at: datetime | None = None
    latest_occurred_at: datetime | None = None
    completeness: Literal["not_asserted"] = "not_asserted"


class SearchEventsResult(_Projection):
    """Result of `search_events`."""
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    total: int = Field(description="Events matching the filter, before capping.")
    returned: int = Field(description="Events included in this projection.")
    truncated: bool = Field(
        description="True when `total` exceeds what is shown.")
    events: list[EventSummary]
    catalog_coverage: CatalogCoverage
    distance_semantics: str | None = None


def enforce_projection_size(payload: BaseModel) -> BaseModel:
    """Guard the byte ceiling. Raises rather than trimming: a projection that
    outgrew its budget is a contract bug, and quietly dropping the tail would
    hide it behind a plausible-looking answer."""
    size = len(payload.model_dump_json().encode("utf-8"))
    if size > MAX_PROJECTION_BYTES:
        raise ToolFailure(
            "partial",
            f"projection is {size} bytes, over the {MAX_PROJECTION_BYTES} limit",
            detail={"bytes": size},
        )
    return payload


# Zone rollups are a long tail: the top few carry the signal, the rest are
# single-event zones that spend context without changing an answer.
MAX_ZONES_IN_CONTEXT = 5

# Candidate lists exist to show ambiguity, not to enumerate a gazetteer.
MAX_PLACE_CANDIDATES = 5

# Full impact rollups can contain hundreds of units. The artifact retains all of
# them; the model receives only the strongest few per administrative level.
MAX_AFFECTED_UNITS_PER_LEVEL = 5
EXPOSURE_LAYERS = (
    "population", "settlements", "hospitals", "schools", "roads", "bridges",
    "airports",
)
MAX_EXPOSURE_BANDS = 9


class LargestEvent(_Projection):
    magnitude: float
    place: str | None = None
    occurred_at: datetime | None = None


class ZoneSummary(_Projection):
    """Per-zone statistics, without the plotting series."""
    zone_id: int
    name: str
    n: int
    b_value: float | None = None
    mc: float | None = None
    max_magnitude: float
    median_depth_km: float | None = None
    pct_aftershocks: float | None = None


class CatalogAnalyticsResult(_Projection):
    """Headline catalog statistics.

    Excludes `grid`, `fmd`, `rate`, and the depth scatter. Those are drawing
    instructions — thousands of numbers whose meaning is the shape they make,
    which a model cannot see and should not narrate.
    """
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    window_from: datetime
    window_to: datetime
    n_used: int
    n_excluded: int
    mc: float | None = None
    b_value: float | None = None
    b_sigma: float | None = None
    b_n: int | None = None
    background_rate_per_year: float
    total_rate_per_year: float
    pct_aftershocks: float | None = None
    active_sequences: int
    largest: LargestEvent | None = None
    top_zones: list[ZoneSummary] = Field(default_factory=list)


class AffectedAdminUnitSummary(_Projection):
    unit_id: int
    name: str
    parent: str | None = None
    maximum_mmi_class: int = Field(ge=1, le=10)
    representative_mmi: float = Field(ge=1.0, le=10.0)


class AdminLevelImpactSummary(_Projection):
    level: Literal["province", "district", "tehsil"]
    analyzed_units: int = Field(ge=0)
    affected_units: int = Field(ge=0)
    maximum_mmi_class: int | None = Field(None, ge=1, le=10)
    top_units: list[AffectedAdminUnitSummary] = Field(default_factory=list)


class ModeledImpactSummary(_Projection):
    classification: Literal["modeled"] = "modeled"
    maximum_mmi_class: int | None = Field(None, ge=1, le=10)
    admin_levels: list[AdminLevelImpactSummary] = Field(default_factory=list)


class EventAnalysisResult(_Projection):
    """Compact evidence view of one versioned deterministic impact artifact."""
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    artifact_id: int = Field(gt=0)
    artifact_schema_version: str
    calculation_version: str
    artifact_created_at: datetime
    event: EventSummary
    modeled_impact: ModeledImpactSummary


class EventIdInput(_Projection):
    event_id: int = Field(gt=0)


class CatalogAnalyticsInput(_Projection):
    window: Literal["30d", "1y", "5y", "all"] = "1y"
    min_mag: str = Field("mc", pattern=r"^(mc|-?\d+(\.\d+)?)$")


class PlaceResolutionInput(_Projection):
    probe: str | None = Field(None, min_length=1, max_length=200)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    level: Literal["national", "province", "district", "tehsil"] | None = None
    parent: str | None = Field(None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def require_probe_or_point(self) -> "PlaceResolutionInput":
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        if self.probe is None and self.lat is None:
            raise ValueError("provide probe or lat+lon")
        return self


class ExposureSummaryInput(EventIdInput):
    layers: list[Literal[
        "population", "settlements", "hospitals", "schools", "roads",
        "bridges", "airports",
    ]] | None = Field(None, min_length=1, max_length=len(EXPOSURE_LAYERS))

    @field_validator("layers")
    @classmethod
    def unique_layers(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("layers must not contain duplicates")
        return value


class ExposureMetrics(_Projection):
    population: float | None = Field(None, ge=0)
    settlements: int | None = Field(None, ge=0)
    hospitals: int | None = Field(None, ge=0)
    schools: int | None = Field(None, ge=0)
    roads: int | None = Field(None, ge=0)
    bridges: int | None = Field(None, ge=0)
    airports: int | None = Field(None, ge=0)


class ExposureBandSummary(_Projection):
    mmi_lower: int = Field(ge=1, le=10)
    mmi_upper: int = Field(ge=2, le=11)
    area_km2: float = Field(ge=0)
    elements: ExposureMetrics


class ExposureSummaryResult(_Projection):
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    artifact_id: int = Field(gt=0)
    artifact_schema_version: str
    calculation_version: str
    artifact_created_at: datetime
    source_impact_artifact_id: int = Field(gt=0)
    event_id: int = Field(gt=0)
    arc_data_version: str = Field(min_length=1)
    status: Literal["complete", "partial"]
    requested_layers: list[str]
    missing_layers: list[str]
    min_mmi: int = Field(ge=1, le=10)
    at_min_mmi_area_km2: float = Field(ge=0)
    at_min_mmi: ExposureMetrics
    bands: list[ExposureBandSummary] = Field(max_length=MAX_EXPOSURE_BANDS)


class AftershockProbability(_Projection):
    days_since: int
    target_magnitude: float
    probability_pct: float


class AftershockSummaryResult(_Projection):
    """Aftershock forecast, without the fitted parameters.

    `k`, `c`, `p`, `alpha`, `Mref`, and the productivity scale are calibration
    internals. They are not claims about this sequence, and a model that can
    read them can present them as if they were.
    """
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    mainshock_magnitude: float
    region: str
    region_name: str | None = None
    zone_name: str | None = None
    event: EventSummary | None = None
    forecast: list[AftershockProbability] = Field(default_factory=list)
    note: str | None = None


class BoundaryCandidateSummary(_Projection):
    """A boundary keyed by id.

    Duplicate administrative names are real and preserved. A candidate carrying
    only a name cannot be disambiguated by anything downstream.
    """
    unit_id: int
    name: str
    level: str
    parent: str | None = None
    score: float | None = None


class PlaceResolutionResult(_Projection):
    schema_version: str = CONTRACTS_SCHEMA_VERSION
    status: Literal["resolved", "ambiguous", "conflict", "not_found"]
    method: Literal["spatial", "text", "spatial+text"] | None = None
    match: BoundaryCandidateSummary | None = None
    candidates: list[BoundaryCandidateSummary] = Field(default_factory=list)
    margin: float | None = None
