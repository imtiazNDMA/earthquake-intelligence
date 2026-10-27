"""Immutable scalar claims bound to exact deterministic artifact evidence."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

from .analysis_artifacts import (ANALYSIS_ARTIFACT_SCHEMA_VERSION,
                                 AnalysisArtifact, AnalysisKind, get_artifact)

CLAIM_SCHEMA_VERSION = "1.0"
_JSON_POINTER_TOKEN = re.compile(r"(?:[^~]|~0|~1)*\Z")
_ARRAY_INDEX = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class ClaimType(str, Enum):
    MODELED_EVENT_MAXIMUM_MMI_CLASS = "modeled_event_maximum_mmi_class"
    MODELED_ADMIN_MAXIMUM_MMI_CLASS = "modeled_admin_maximum_mmi_class"
    MODELED_ADMIN_REPRESENTATIVE_MMI = "modeled_admin_representative_mmi"


class EntityType(str, Enum):
    SEISMIC_EVENT = "seismic_event"
    ADMIN_BOUNDARY = "admin_boundary"


class ClaimUnit(str, Enum):
    MMI_CLASS = "mmi_class"
    MMI = "mmi"


class ClaimDraft(BaseModel):
    schema_version: Literal["1.0"] = CLAIM_SCHEMA_VERSION
    claim_type: ClaimType
    entity_type: EntityType
    entity_id: int = Field(gt=0)
    display_name: str
    value: Decimal
    unit: ClaimUnit
    source_kind: AnalysisKind
    source_artifact_id: int = Field(gt=0)
    source_path: str
    source_artifact_schema_version: str
    calculation_version: str
    observed_at: datetime | None = None
    freshness: timedelta | None = None
    limitation: str | None = None

    @field_validator("schema_version", "display_name",
                     "source_artifact_schema_version", "calculation_version")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("limitation")
    @classmethod
    def reject_blank_limitation(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("limitation must not be blank")
        return value

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.utcoffset() is None:
                raise ValueError("observed_at must include a timezone")
            return value.astimezone(timezone.utc)
        return None

    @field_validator("freshness")
    @classmethod
    def reject_negative_freshness(cls, value: timedelta | None) -> timedelta | None:
        if value is not None and value < timedelta(0):
            raise ValueError("freshness must not be negative")
        return value

    @model_validator(mode="after")
    def validate_type_shape(self) -> "ClaimDraft":
        if not self.value.is_finite():
            raise ValueError("claim value must be finite")
        if self.claim_type == ClaimType.MODELED_EVENT_MAXIMUM_MMI_CLASS:
            expected = (EntityType.SEISMIC_EVENT, ClaimUnit.MMI_CLASS)
        elif self.claim_type == ClaimType.MODELED_ADMIN_MAXIMUM_MMI_CLASS:
            expected = (EntityType.ADMIN_BOUNDARY, ClaimUnit.MMI_CLASS)
        else:
            expected = (EntityType.ADMIN_BOUNDARY, ClaimUnit.MMI)
        if (self.entity_type, self.unit) != expected:
            raise ValueError("claim type, entity type, and unit do not agree")
        if not Decimal("1") <= self.value <= Decimal("10"):
            raise ValueError("MMI claim value must be between 1 and 10")
        if self.unit == ClaimUnit.MMI_CLASS and self.value != self.value.to_integral():
            raise ValueError("mmi_class claims must be integers")
        _pointer_tokens(self.source_path)
        return self

    model_config = ConfigDict(extra="forbid")


class AnalysisClaim(ClaimDraft):
    id: int = Field(gt=0)
    created_at: datetime


@dataclass(frozen=True)
class ClaimResolution:
    claim: AnalysisClaim
    created: bool


class ClaimConflictError(RuntimeError):
    """A claim identity already exists with different immutable metadata."""


def resolve_source_path(artifact: AnalysisArtifact, source_path: str) -> Any:
    """Resolve a canonical RFC 6901 pointer against persisted artifact fields."""
    value: Any = {
        "computation_input": artifact.computation_input,
        "data_fingerprint": artifact.data_fingerprint,
        "payload": artifact.payload,
        "provenance": artifact.provenance,
    }
    for token in _pointer_tokens(source_path):
        if isinstance(value, dict):
            if token not in value:
                raise ValueError(f"source path key {token!r} does not exist")
            value = value[token]
        elif isinstance(value, list):
            if not _ARRAY_INDEX.fullmatch(token):
                raise ValueError("array indices must be canonical unsigned integers")
            index = int(token)
            if index >= len(value):
                raise ValueError("source path array index is out of range")
            value = value[index]
        else:
            raise ValueError("source path traverses through a scalar")
    return value


def validate_claim(artifact: AnalysisArtifact, draft: ClaimDraft) -> ClaimDraft:
    """Bind a scalar claim to artifact version, value, unit, and exact entity."""
    from .impact import EVENT_IMPACT_CALCULATION_VERSION

    # `model_copy(update=...)` does not validate updates; re-enter through the
    # public contract so programmatic callers cannot bypass type/unit rules.
    draft = ClaimDraft.model_validate(draft.model_dump())
    if artifact.id != draft.source_artifact_id:
        raise ValueError("claim references a different source artifact")
    if artifact.kind != draft.source_kind:
        raise ValueError("claim source kind does not match artifact")
    if artifact.schema_version != draft.source_artifact_schema_version:
        raise ValueError("claim source schema version does not match artifact")
    if artifact.calculation_version != draft.calculation_version:
        raise ValueError("claim calculation version does not match artifact")
    if (artifact.kind != AnalysisKind.IMPACT
            or artifact.schema_version != ANALYSIS_ARTIFACT_SCHEMA_VERSION
            or artifact.calculation_version != EVENT_IMPACT_CALCULATION_VERSION):
        raise ValueError("unsupported artifact version for claim validation")

    resolved = resolve_source_path(artifact, draft.source_path)
    if isinstance(resolved, bool) or not isinstance(resolved, (int, float)):
        raise ValueError("claim source path must resolve to a numeric scalar")
    if isinstance(resolved, float) and not math.isfinite(resolved):
        raise ValueError("claim source value must be finite")
    if Decimal(str(resolved)) != draft.value:
        raise ValueError("claim value does not equal the source value")

    tokens = _pointer_tokens(draft.source_path)
    if draft.claim_type == ClaimType.MODELED_EVENT_MAXIMUM_MMI_CLASS:
        _validate_event_claim(artifact, draft, tokens)
    else:
        _validate_admin_claim(artifact, draft, tokens)
    _validate_observed_at(artifact, draft)
    return draft


def get_or_create_claim(conn: psycopg.Connection,
                        draft: ClaimDraft) -> ClaimResolution:
    """Validate and idempotently persist one immutable claim."""
    artifact = get_artifact(conn, draft.source_artifact_id)
    if artifact is None:
        raise ValueError(f"analysis artifact {draft.source_artifact_id} not found")
    validated = validate_claim(artifact, draft)
    fields = tuple(ClaimDraft.model_fields)
    values = [getattr(validated, field) for field in fields]

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "INSERT INTO analysis_claim (" + ", ".join(fields) + ") "
            "VALUES (" + ", ".join(["%s"] * len(fields)) + ") "
            "ON CONFLICT (schema_version, source_artifact_id, claim_type, "
            "entity_type, entity_id, source_path) DO NOTHING RETURNING *",
            values,
        )
        row = cur.fetchone()
    if row is not None:
        return ClaimResolution(AnalysisClaim.model_validate(row), created=True)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM analysis_claim WHERE schema_version = %s "
            "AND source_artifact_id = %s AND claim_type = %s "
            "AND entity_type = %s AND entity_id = %s AND source_path = %s",
            (validated.schema_version, validated.source_artifact_id,
             validated.claim_type, validated.entity_type, validated.entity_id,
             validated.source_path),
        )
        existing = AnalysisClaim.model_validate(cur.fetchone())
    if any(getattr(existing, field) != getattr(validated, field) for field in fields):
        raise ClaimConflictError("claim identity exists with different metadata")
    return ClaimResolution(existing, created=False)


def _validate_event_claim(artifact: AnalysisArtifact, draft: ClaimDraft,
                          tokens: list[str]) -> None:
    if draft.entity_id != artifact.computation_input.get("event_id"):
        raise ValueError("event entity does not match artifact input")
    expected_name = artifact.provenance.get("event", {}).get("place")
    expected_name = expected_name or f"Event {draft.entity_id}"
    if draft.display_name != expected_name:
        raise ValueError("event display name does not match artifact provenance")
    if (len(tokens) != 6 or tokens[:3] != ["payload", "bands", "features"]
            or tokens[4:] != ["properties", "mmi_lower"]):
        raise ValueError("event maximum claim must cite a contour-band MMI value")
    levels = [feature["properties"]["mmi_lower"]
              for feature in artifact.payload["bands"]["features"]]
    if not levels or draft.value != Decimal(str(max(levels))):
        raise ValueError("event claim does not cite the maximum MMI class")


def _validate_admin_claim(artifact: AnalysisArtifact, draft: ClaimDraft,
                          tokens: list[str]) -> None:
    expected_field = (
        "mmi_max" if draft.claim_type == ClaimType.MODELED_ADMIN_MAXIMUM_MMI_CLASS
        else "mmi_repr"
    )
    if (len(tokens) != 5 or tokens[:2] != ["payload", "rollups"]
            or tokens[2] not in {"province", "district", "tehsil"}
            or not _ARRAY_INDEX.fullmatch(tokens[3]) or tokens[4] != expected_field):
        raise ValueError("administrative claim path does not match its claim type")
    rows = artifact.payload["rollups"][tokens[2]]
    index = int(tokens[3])
    if index >= len(rows):
        raise ValueError("administrative claim row is out of range")
    row = rows[index]
    if row["id"] != draft.entity_id or row["name"] != draft.display_name:
        raise ValueError("administrative entity does not match the cited artifact row")


def _validate_observed_at(artifact: AnalysisArtifact, draft: ClaimDraft) -> None:
    if draft.observed_at is None:
        return
    value = artifact.provenance.get("event", {}).get("occurred_at")
    if not value:
        raise ValueError("artifact has no observation time for this claim")
    expected = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    if draft.observed_at != expected:
        raise ValueError("claim observation time does not match artifact provenance")


def _pointer_tokens(source_path: str) -> list[str]:
    if not source_path.startswith("/"):
        raise ValueError("source path must be an absolute JSON pointer")
    raw_tokens = source_path[1:].split("/")
    if not raw_tokens or raw_tokens[0] not in {
            "computation_input", "data_fingerprint", "payload", "provenance"}:
        raise ValueError("source path must start at a persisted artifact field")
    tokens = []
    for token in raw_tokens:
        if not _JSON_POINTER_TOKEN.fullmatch(token):
            raise ValueError("source path contains an invalid JSON pointer escape")
        tokens.append(token.replace("~1", "/").replace("~0", "~"))
    return tokens
