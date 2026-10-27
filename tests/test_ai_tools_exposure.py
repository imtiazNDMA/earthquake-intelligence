"""Bounded model-facing exposure over versioned impact and ARC evidence."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from eqmon.ai.contracts import (ExposureSummaryInput, ExposureSummaryResult,
                                ToolFailure)
from eqmon.ai.registry import (CostClass, Role, ToolRegistry, ToolSpec,
                               default_registry)
from eqmon.ai.tools import exposure as exposure_tools
from eqmon.ai.tools.schemas import get_exposure_summary_tool


ARC_SUMMARY = {
    "min_mmi": 6,
    "at_min_mmi": {
        "area_km2": 7102.0,
        "elements": {
            "population": {"total": 9188426.0, "male": 4708426.0},
            "hospitals": {"count": 300},
        },
    },
    "bands": [
        {"mmi_low": 7, "mmi_high": 8, "area_km2": 1787.0,
         "elements": {"population": {"total": 1856644.0},
                      "hospitals": {"count": 83}}},
        {"mmi_low": 6, "mmi_high": 7, "area_km2": 5315.0,
         "elements": {"population": {"total": 7331782.0},
                      "hospitals": {"count": 217}}},
    ],
    # These must never cross the model projection boundary.
    "cumulative": [{"mmi_min": 6, "elements": {"population": {"total": 99}}}],
    "totals": {"population": {"total": 99}},
    "meta": {"internal_path": "C:/arc/cache"},
}


def _impact():
    return SimpleNamespace(
        id=91,
        input_hash="a" * 64,
        payload={"bands": {"type": "FeatureCollection", "features": [{"x": 1}]}},
    )


def _exposure_artifact(payload):
    return SimpleNamespace(
        id=101,
        schema_version="1.0",
        calculation_version="1.0",
        created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        computation_input={"event_id": 7, "impact_artifact_id": 91},
        data_fingerprint={"arc_data_version": "arc-pk-2026-08"},
        payload=payload,
    )


def test_exposure_tool_projects_versioned_bounded_headline(monkeypatch):
    monkeypatch.setattr(exposure_tools.domain_config, "ARC_DATA_VERSION", "arc-pk-2026-08")
    monkeypatch.setattr(exposure_tools, "get_event", lambda conn, event_id: {"id": event_id})
    monkeypatch.setattr(exposure_tools, "get_grid", lambda: object())
    monkeypatch.setattr(
        exposure_tools, "get_or_compute_event_impact",
        lambda conn, event, grid: SimpleNamespace(artifact=_impact()),
    )
    monkeypatch.setattr(exposure_tools, "find_artifact", lambda *a, **k: None)
    calls = []

    async def analyze(bands, layers):
        calls.append((bands, layers))
        return ARC_SUMMARY

    monkeypatch.setattr(exposure_tools.exposure, "analyze", analyze)

    def persist(conn, **kwargs):
        payload = kwargs["compute"]()
        return SimpleNamespace(artifact=_exposure_artifact(payload), created=True)

    monkeypatch.setattr(exposure_tools, "get_or_compute_artifact", persist)

    result = asyncio.run(exposure_tools.get_exposure_summary(
        None, event_id=7, layers=["population", "hospitals"]))
    text = result.model_dump_json()

    assert isinstance(result, ExposureSummaryResult)
    assert result.artifact_id == 101
    assert result.source_impact_artifact_id == 91
    assert result.arc_data_version == "arc-pk-2026-08"
    assert result.status == "complete"
    assert result.at_min_mmi.population == 9188426.0
    assert result.at_min_mmi.hospitals == 300
    assert calls[0][1] == ["hospitals", "population"]
    assert "cumulative" not in text
    assert "internal_path" not in text
    assert "male" not in text


def test_exposure_tool_reuses_artifact_without_calling_arc(monkeypatch):
    monkeypatch.setattr(exposure_tools.domain_config, "ARC_DATA_VERSION", "arc-pk-2026-08")
    monkeypatch.setattr(exposure_tools, "get_event", lambda conn, event_id: {"id": event_id})
    monkeypatch.setattr(exposure_tools, "get_grid", lambda: object())
    monkeypatch.setattr(
        exposure_tools, "get_or_compute_event_impact",
        lambda conn, event, grid: SimpleNamespace(artifact=_impact()),
    )
    payload = exposure_tools._compact_payload(
        ARC_SUMMARY, ["hospitals", "population"])
    monkeypatch.setattr(
        exposure_tools, "find_artifact",
        lambda *a, **k: _exposure_artifact(payload),
    )

    async def forbidden(*args, **kwargs):
        raise AssertionError("ARC should not be called for a matching artifact")

    monkeypatch.setattr(exposure_tools.exposure, "analyze", forbidden)
    result = asyncio.run(exposure_tools.get_exposure_summary(
        None, event_id=7, layers=["population", "hospitals"]))
    assert result.artifact_id == 101


def test_exposure_tool_requires_explicit_arc_release(monkeypatch):
    monkeypatch.setattr(exposure_tools.domain_config, "ARC_DATA_VERSION", "")
    with pytest.raises(ToolFailure) as failure:
        asyncio.run(exposure_tools.get_exposure_summary(None, event_id=7))
    assert failure.value.code == "upstream_unavailable"


def test_exposure_schema_is_strict_and_registry_has_exact_l0_set():
    parameters = get_exposure_summary_tool()["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    registry = default_registry()
    assert set(registry.names()) == {
        "search_events", "get_event_summary", "get_event_analysis",
        "get_exposure_summary", "get_aftershock_summary",
        "get_catalog_analytics", "resolve_place",
    }
    spec = registry.get("get_exposure_summary")
    assert spec.cost_class == CostClass.EXTERNAL
    assert spec.side_effects == "none"


def test_dispatch_rejects_bad_arguments_before_handler():
    registry = ToolRegistry()
    called = False

    async def handler(*args, **kwargs):
        nonlocal called
        called = True

    registry.register(ToolSpec(
        name="get_exposure_summary", schema_version="1.0", schema={},
        handler=handler, authz=Role.VIEWER, cost_class=CostClass.EXTERNAL,
        input_model=ExposureSummaryInput, output_model=ExposureSummaryResult,
    ))
    with pytest.raises(ToolFailure) as failure:
        asyncio.run(registry.dispatch(
            None, "get_exposure_summary", {"event_id": 0, "extra": True},
            allowlist=["get_exposure_summary"], role=Role.VIEWER,
        ))
    assert failure.value.code == "invalid_request"
    assert called is False
