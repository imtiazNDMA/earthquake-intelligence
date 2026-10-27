"""Versioned, bounded exposure adapter over ARC and impact artifacts."""
from __future__ import annotations

import asyncio

import psycopg
from fastapi import HTTPException

from ... import config as domain_config
from ... import exposure
from ...analysis_artifacts import (AnalysisArtifact, AnalysisKind, find_artifact,
                                   get_or_compute_artifact)
from ...events.repo import get_event
from ...impact import get_or_compute_event_impact
from ...vs30 import get_grid
from .. import config as ai_config
from ..contracts import (EXPOSURE_LAYERS, MAX_EXPOSURE_BANDS,
                         ExposureBandSummary, ExposureMetrics,
                         ExposureSummaryResult, ToolFailure,
                         enforce_projection_size)

EXPOSURE_CALCULATION_VERSION = "1.0"


def _metrics(elements: dict) -> ExposureMetrics:
    values = elements or {}
    return ExposureMetrics(
        population=(values.get("population") or {}).get("total"),
        settlements=(values.get("settlements") or {}).get("count"),
        hospitals=(values.get("hospitals") or {}).get("count"),
        schools=(values.get("schools") or {}).get("count"),
        roads=(values.get("roads") or {}).get("count"),
        bridges=(values.get("bridges") or {}).get("count"),
        airports=(values.get("airports") or {}).get("count"),
    )


def _compact_payload(summary: dict, requested: list[str]) -> dict:
    headline = summary["at_min_mmi"]
    bands = summary.get("bands", [])[:MAX_EXPOSURE_BANDS]
    present = {
        layer for band in bands for layer in (band.get("elements") or {})
    }
    missing = sorted(set(requested) - present)
    return {
        "status": "partial" if missing else "complete",
        "requested_layers": requested,
        "missing_layers": missing,
        "min_mmi": summary["min_mmi"],
        "at_min_mmi_area_km2": headline.get("area_km2", 0),
        "at_min_mmi": _metrics(headline.get("elements") or {}).model_dump(),
        "bands": [{
            "mmi_lower": band["mmi_low"],
            "mmi_upper": band["mmi_high"],
            "area_km2": band.get("area_km2", 0),
            "elements": _metrics(band.get("elements") or {}).model_dump(),
        } for band in bands],
    }


def _project(artifact: AnalysisArtifact) -> ExposureSummaryResult:
    payload = artifact.payload
    result = ExposureSummaryResult(
        artifact_id=artifact.id,
        artifact_schema_version=artifact.schema_version,
        calculation_version=artifact.calculation_version,
        artifact_created_at=artifact.created_at,
        source_impact_artifact_id=artifact.computation_input["impact_artifact_id"],
        event_id=artifact.computation_input["event_id"],
        arc_data_version=artifact.data_fingerprint["arc_data_version"],
        **payload,
    )
    return enforce_projection_size(result)


async def get_exposure_summary(conn: psycopg.Connection, *, event_id: int,
                               layers: list[str] | None = None,
                               ) -> ExposureSummaryResult:
    if not domain_config.ARC_DATA_VERSION:
        raise ToolFailure(
            "upstream_unavailable",
            "ARC_DATA_VERSION is required before exposure artifacts can be reused",
        )
    event = get_event(conn, event_id)
    if event is None:
        raise ToolFailure("not_found", f"no event with id {event_id}",
                          detail={"event_id": event_id})
    impact = get_or_compute_event_impact(conn, event, get_grid()).artifact
    requested = sorted(layers or EXPOSURE_LAYERS)
    computation_input = {
        "event_id": event_id,
        "impact_artifact_id": impact.id,
        "layers": requested,
        "min_mmi": domain_config.EXPOSURE_MIN_MMI,
    }
    data_fingerprint = {
        "arc_data_version": domain_config.ARC_DATA_VERSION,
        "impact_input_hash": impact.input_hash,
    }
    existing = find_artifact(
        conn, kind=AnalysisKind.EXPOSURE,
        calculation_version=EXPOSURE_CALCULATION_VERSION,
        computation_input=computation_input, data_fingerprint=data_fingerprint,
    )
    if existing is not None:
        return _project(existing)

    try:
        summary = await asyncio.wait_for(
            exposure.analyze(impact.payload["bands"], requested),
            timeout=ai_config.EXPOSURE_TOOL_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise ToolFailure("upstream_unavailable", "exposure service deadline exceeded") from exc
    except HTTPException as exc:
        code = "invalid_request" if exc.status_code == 400 else "upstream_unavailable"
        raise ToolFailure(code, str(exc.detail)) from exc

    payload = _compact_payload(summary, requested)
    resolution = get_or_compute_artifact(
        conn,
        kind=AnalysisKind.EXPOSURE,
        calculation_version=EXPOSURE_CALCULATION_VERSION,
        computation_input=computation_input,
        data_fingerprint=data_fingerprint,
        provenance={
            "source": "ARC",
            "arc_data_version": domain_config.ARC_DATA_VERSION,
            "source_impact_artifact_id": impact.id,
        },
        compute=lambda: payload,
    )
    return _project(resolution.artifact)
