"""Structured claims bound to immutable deterministic artifact evidence."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import psycopg
import pytest

from eqmon.analysis_artifacts import (ANALYSIS_ARTIFACT_SCHEMA_VERSION,
                                      AnalysisArtifact, AnalysisKind,
                                      get_or_compute_artifact)
from eqmon.claims import (CLAIM_SCHEMA_VERSION, AnalysisClaim, ClaimConflictError,
                          ClaimDraft, ClaimType, ClaimUnit, EntityType,
                          get_or_create_claim, resolve_source_path, validate_claim)


def _payload():
    return {
        "bands": {"features": [
            {"properties": {"mmi_lower": 2}},
            {"properties": {"mmi_lower": 8}},
        ]},
        "rollups": {"district": [
            {"id": 11, "name": "Alpha", "parent": "Test",
             "mmi_max": 7, "mmi_repr": 6.4},
            {"id": 12, "name": "Beta", "parent": "Test",
             "mmi_max": 7, "mmi_repr": 5.9},
        ], "province": [], "tehsil": []},
    }


def _artifact(artifact_id=1):
    return AnalysisArtifact(
        id=artifact_id,
        kind=AnalysisKind.IMPACT,
        schema_version=ANALYSIS_ARTIFACT_SCHEMA_VERSION,
        calculation_version="1.0",
        input_hash="a" * 64,
        computation_input={"event_id": 7, "magnitude": 6.2},
        data_fingerprint={"vs30": "a", "boundaries": "b"},
        payload=_payload(),
        provenance={"event": {
            "place": "Quetta area",
            "occurred_at": "2026-01-01T00:00:00Z",
        }},
        created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
    )


def _admin_draft(artifact_id=1, **changes):
    values = {
        "claim_type": ClaimType.MODELED_ADMIN_MAXIMUM_MMI_CLASS,
        "entity_type": EntityType.ADMIN_BOUNDARY,
        "entity_id": 11,
        "display_name": "Alpha",
        "value": Decimal("7"),
        "unit": ClaimUnit.MMI_CLASS,
        "source_kind": AnalysisKind.IMPACT,
        "source_artifact_id": artifact_id,
        "source_path": "/payload/rollups/district/0/mmi_max",
        "source_artifact_schema_version": ANALYSIS_ARTIFACT_SCHEMA_VERSION,
        "calculation_version": "1.0",
        "observed_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    values.update(changes)
    return ClaimDraft(**values)


def test_json_pointer_resolves_objects_arrays_and_escaped_keys():
    artifact = _artifact().model_copy(update={
        "payload": {"a/b": {"~value": [3]}},
    })
    assert resolve_source_path(artifact, "/payload/a~1b/~0value/0") == 3


@pytest.mark.parametrize("path", [
    "payload/rollups/district/0/mmi_max",
    "/payload/rollups/district/-/mmi_max",
    "/payload/rollups/district/00/mmi_max",
    "/payload/rollups/district/-1/mmi_max",
    "/payload/rollups/district/9/mmi_max",
    "/payload/rollups/district/0/missing",
    "/payload/bad~2escape",
])
def test_json_pointer_rejects_noncanonical_or_missing_paths(path):
    with pytest.raises(ValueError):
        resolve_source_path(_artifact(), path)


def test_claim_validation_binds_value_unit_and_admin_entity_to_same_row():
    validated = validate_claim(_artifact(), _admin_draft())
    assert validated.value == Decimal("7")

    with pytest.raises(ValueError, match="entity"):
        validate_claim(_artifact(), _admin_draft(entity_id=12, display_name="Beta"))
    with pytest.raises(ValueError, match="source value"):
        validate_claim(_artifact(), _admin_draft(value=Decimal("6")))


def test_event_maximum_claim_must_point_to_the_actual_maximum_band():
    draft = ClaimDraft(
        claim_type=ClaimType.MODELED_EVENT_MAXIMUM_MMI_CLASS,
        entity_type=EntityType.SEISMIC_EVENT,
        entity_id=7,
        display_name="Quetta area",
        value=Decimal("8"),
        unit=ClaimUnit.MMI_CLASS,
        source_kind=AnalysisKind.IMPACT,
        source_artifact_id=1,
        source_path="/payload/bands/features/1/properties/mmi_lower",
        source_artifact_schema_version="1.0",
        calculation_version="1.0",
    )
    assert validate_claim(_artifact(), draft) == draft

    with pytest.raises(ValueError, match="maximum"):
        validate_claim(
            _artifact(), draft.model_copy(update={
                "value": Decimal("2"),
                "source_path": "/payload/bands/features/0/properties/mmi_lower",
            }))


pytest_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set")


def _persist_artifact(conn):
    return get_or_compute_artifact(
        conn,
        kind=AnalysisKind.IMPACT,
        calculation_version="1.0",
        computation_input={"event_id": 7, "magnitude": 6.2},
        data_fingerprint={"vs30": "a", "boundaries": "b"},
        provenance={"event": {
            "place": "Quetta area",
            "occurred_at": "2026-01-01T00:00:00Z",
        }},
        compute=_payload,
    ).artifact


@pytest_db
def test_identical_claim_is_idempotent(db_conn):
    artifact = _persist_artifact(db_conn)
    first = get_or_create_claim(db_conn, _admin_draft(artifact.id))
    second = get_or_create_claim(db_conn, _admin_draft(artifact.id))

    assert isinstance(first.claim, AnalysisClaim)
    assert first.claim.schema_version == CLAIM_SCHEMA_VERSION
    assert first.created is True
    assert second.created is False
    assert first.claim.id == second.claim.id


@pytest_db
def test_natural_key_conflict_with_different_metadata_is_rejected(db_conn):
    artifact = _persist_artifact(db_conn)
    get_or_create_claim(db_conn, _admin_draft(artifact.id))

    with pytest.raises(ClaimConflictError):
        get_or_create_claim(
            db_conn, _admin_draft(artifact.id, limitation="Preliminary"))


@pytest_db
def test_database_rejects_claim_metadata_that_disagrees_with_artifact(db_conn):
    artifact = _persist_artifact(db_conn)

    with pytest.raises(psycopg.Error, match="source kind"):
        with db_conn.transaction():
            db_conn.execute(
                "INSERT INTO analysis_claim "
                "(schema_version, claim_type, entity_type, entity_id, display_name, "
                " value, unit, source_kind, source_artifact_id, source_path, "
                " source_artifact_schema_version, calculation_version) "
                "VALUES ('1.0', 'modeled_admin_maximum_mmi_class', "
                "'admin_boundary', 11, 'Alpha', 7, 'mmi_class', 'analytics', %s, "
                "'/payload/rollups/district/0/mmi_max', '1.0', '1.0')",
                (artifact.id,),
            )


@pytest_db
@pytest.mark.parametrize("statement", [
    "UPDATE analysis_claim SET value = 6 WHERE id = %s",
    "DELETE FROM analysis_claim WHERE id = %s",
])
def test_claims_are_immutable_in_the_database(db_conn, statement):
    artifact = _persist_artifact(db_conn)
    claim_id = get_or_create_claim(db_conn, _admin_draft(artifact.id)).claim.id

    with pytest.raises(psycopg.Error, match="immutable"):
        with db_conn.transaction():
            db_conn.execute(statement, (claim_id,))

    assert db_conn.execute(
        "SELECT count(*) FROM analysis_claim WHERE id = %s", (claim_id,)
    ).fetchone()[0] == 1
