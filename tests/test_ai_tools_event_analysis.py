"""Compact model-facing projection of a versioned event-impact artifact."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from eqmon.ai.contracts import (MAX_AFFECTED_UNITS_PER_LEVEL,
                                EventAnalysisResult, ToolFailure)
from eqmon.ai.tools import analysis as analysis_tools
from eqmon.ai.tools.schemas import get_event_analysis_tool


def _event():
    return {
        "id": 7,
        "magnitude": 6.2,
        "mag_type": "Mw",
        "depth_km": 12.0,
        "lat": 34.0,
        "lon": 72.0,
        "place": "Quetta area",
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "source": "PMD",
        "is_mainshock": True,
    }


def _artifact():
    districts = [
        {"id": index, "name": f"District {index}", "parent": "Test",
         "mmi_max": 8 - index % 3, "mmi_repr": 6.5 - index / 10}
        for index in range(9)
    ]
    payload = {
        "bands": {
            "type": "FeatureCollection",
            "features": [
                {"properties": {"mmi_lower": level},
                 "geometry": {"type": "Polygon", "coordinates": [[[]]]}}
                for level in (2, 3, 4, 5, 6, 7, 8)
            ],
        },
        "rollups": {
            "province": [
                {"id": 100, "name": "Balochistan", "parent": None,
                 "mmi_max": 8, "mmi_repr": 5.8},
            ],
            "district": districts,
            "tehsil": [],
        },
    }
    return SimpleNamespace(
        id=91,
        schema_version="1.0",
        calculation_version="1.0",
        created_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
        payload=payload,
    )


def test_event_analysis_is_compact_bounded_and_keeps_artifact_evidence(monkeypatch):
    monkeypatch.setattr(analysis_tools, "get_event", lambda conn, event_id: _event())
    monkeypatch.setattr(analysis_tools, "get_grid", lambda: object())
    monkeypatch.setattr(
        analysis_tools, "get_or_compute_event_impact",
        lambda conn, event, grid: SimpleNamespace(artifact=_artifact(), created=False),
    )

    result = analysis_tools.get_event_analysis(None, event_id=7)
    payload = result.model_dump_json()

    assert isinstance(result, EventAnalysisResult)
    assert result.artifact_id == 91
    assert result.event.source == "PMD"
    assert result.modeled_impact.maximum_mmi_class == 8
    district = next(item for item in result.modeled_impact.admin_levels
                    if item.level == "district")
    assert district.analyzed_units == 9
    assert district.affected_units == 9
    assert len(district.top_units) == MAX_AFFECTED_UNITS_PER_LEVEL
    assert "geometry" not in payload
    assert "coordinates" not in payload
    assert "District 8" not in payload


def test_event_analysis_missing_event_is_typed_without_loading_grid(monkeypatch):
    monkeypatch.setattr(analysis_tools, "get_event", lambda conn, event_id: None)
    grid_loaded = False

    def load_grid():
        nonlocal grid_loaded
        grid_loaded = True

    monkeypatch.setattr(analysis_tools, "get_grid", load_grid)

    with pytest.raises(ToolFailure) as failure:
        analysis_tools.get_event_analysis(None, event_id=999_999)

    assert failure.value.code == "not_found"
    assert grid_loaded is False


def test_event_analysis_rejects_invalid_id_before_database_lookup(monkeypatch):
    queried = False

    def get_event(conn, event_id):
        nonlocal queried
        queried = True

    monkeypatch.setattr(analysis_tools, "get_event", get_event)

    with pytest.raises(ToolFailure) as failure:
        analysis_tools.get_event_analysis(None, event_id=0)

    assert failure.value.code == "invalid_request"
    assert queried is False


def test_event_analysis_tool_schema_requires_positive_known_event_id():
    function = get_event_analysis_tool()["function"]
    parameters = function["parameters"]

    assert function["name"] == "get_event_analysis"
    assert parameters["required"] == ["event_id"]
    assert parameters["properties"]["event_id"]["minimum"] == 1
    assert parameters["additionalProperties"] is False
