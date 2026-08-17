"""Immutable, compute-once records of deterministic scientific analysis.

The artifact identity is the normalized computation input plus the exact data
fingerprint and an explicit calculation version. The database owns same-key
serialization so concurrent callers cannot both perform an expensive analysis.
This module never commits: transaction ownership stays with its caller.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

ANALYSIS_ARTIFACT_SCHEMA_VERSION = "1.0"


class AnalysisKind(str, Enum):
    INTENSITY = "intensity"
    IMPACT = "impact"
    EXPOSURE = "exposure"
    ANALYTICS = "analytics"
    AFTERSHOCK = "aftershock"


class AnalysisArtifact(BaseModel):
    """One persisted deterministic result and the evidence needed to reuse it."""

    id: int = Field(gt=0)
    kind: AnalysisKind
    schema_version: str
    calculation_version: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    computation_input: dict[str, Any]
    data_fingerprint: dict[str, Any]
    payload: dict[str, Any]
    provenance: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ArtifactResolution:
    artifact: AnalysisArtifact
    created: bool


def artifact_input_hash(kind: AnalysisKind | str,
                        computation_input: Mapping[str, Any],
                        data_fingerprint: Mapping[str, Any]) -> str:
    """SHA-256 of canonical scientific input and underlying data identity."""
    envelope = {
        "kind": AnalysisKind(kind).value,
        "input": _json_object(computation_input, "computation_input", identity=True),
        "data": _json_object(data_fingerprint, "data_fingerprint", identity=True),
    }
    encoded = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_or_compute_artifact(
    conn: psycopg.Connection,
    *,
    kind: AnalysisKind | str,
    calculation_version: str,
    computation_input: Mapping[str, Any],
    data_fingerprint: Mapping[str, Any],
    provenance: Mapping[str, Any],
    compute: Callable[[], Mapping[str, Any]],
) -> ArtifactResolution:
    """Return an existing artifact or compute and insert it exactly once per key.

    Same-key callers serialize on a transaction-scoped advisory lock. The
    second lookup after acquiring that lock is what prevents duplicate compute,
    rather than merely resolving duplicate inserts after the work is done.
    """
    artifact_kind = AnalysisKind(kind)
    version = calculation_version.strip()
    if not version:
        raise ValueError("calculation_version must not be empty")

    normalized_input = _json_object(
        computation_input, "computation_input", identity=True)
    normalized_data = _json_object(
        data_fingerprint, "data_fingerprint", identity=True)
    normalized_provenance = _json_object(provenance, "provenance", identity=False)
    input_hash = artifact_input_hash(
        artifact_kind, normalized_input, normalized_data)
    key = (artifact_kind.value, ANALYSIS_ARTIFACT_SCHEMA_VERSION,
           version, input_hash)

    existing = _find(conn, key)
    if existing is not None:
        return ArtifactResolution(existing, created=False)

    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_advisory_key(key),))
    existing = _find(conn, key)
    if existing is not None:
        return ArtifactResolution(existing, created=False)

    payload = _json_object(compute(), "payload", identity=False)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "INSERT INTO analysis_artifact "
            "(kind, schema_version, calculation_version, input_hash, "
            " computation_input, data_fingerprint, payload, provenance) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
            (*key, Jsonb(normalized_input), Jsonb(normalized_data),
             Jsonb(payload), Jsonb(normalized_provenance)),
        )
        artifact = AnalysisArtifact.model_validate(cur.fetchone())
    return ArtifactResolution(artifact, created=True)


def get_artifact(conn: psycopg.Connection,
                 artifact_id: int) -> AnalysisArtifact | None:
    """Load one deterministic artifact by its durable evidence ID."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM analysis_artifact WHERE id = %s", (artifact_id,))
        row = cur.fetchone()
    return AnalysisArtifact.model_validate(row) if row is not None else None


def _find(conn: psycopg.Connection, key: tuple[str, str, str, str]
          ) -> AnalysisArtifact | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM analysis_artifact WHERE kind = %s "
            "AND schema_version = %s AND calculation_version = %s "
            "AND input_hash = %s",
            key,
        )
        row = cur.fetchone()
    return AnalysisArtifact.model_validate(row) if row is not None else None


def _advisory_key(key: tuple[str, str, str, str]) -> int:
    digest = hashlib.sha256("\0".join(key).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _json_object(value: Mapping[str, Any], name: str, *,
                 identity: bool) -> dict[str, Any]:
    normalized = _normalize_json(value, identity=identity)
    if not isinstance(normalized, dict):
        raise TypeError(f"{name} must be an object")
    return normalized


def _normalize_json(value: Any, *, identity: bool) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if isinstance(value, Enum):
        return _normalize_json(value.value, identity=identity)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("datetime values must include a timezone")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: _normalize_json(item, identity=identity)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item, identity=identity) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("artifact values must be finite")
        if identity and value.is_integer():
            return int(value)
        return value
    raise TypeError(f"unsupported artifact value type: {type(value).__name__}")
