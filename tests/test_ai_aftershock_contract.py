"""Pure validation tests for the model-facing aftershock request."""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from eqmon.aftershock_service import AftershockForecastInput
from eqmon.ai.contracts import ToolFailure
from eqmon.ai.tools.analysis import get_aftershock_summary
from eqmon.ai.tools.schemas import get_aftershock_summary_tool


def test_aftershock_input_accepts_exactly_the_two_supported_modes():
    by_id = AftershockForecastInput(event_id=42)
    inline = AftershockForecastInput(magnitude=6.5, lat=34.0, lon=72.0)

    assert by_id.event_id == 42
    assert inline.magnitude == 6.5


@pytest.mark.parametrize("kwargs", [
    {},
    {"event_id": 0},
    {"magnitude": 6.5},
    {"magnitude": 6.5, "lat": 34.0},
    {"event_id": 42, "magnitude": 6.5, "lat": 34.0, "lon": 72.0},
    {"magnitude": -0.1, "lat": 34.0, "lon": 72.0},
    {"magnitude": 10.1, "lat": 34.0, "lon": 72.0},
    {"magnitude": math.nan, "lat": 34.0, "lon": 72.0},
    {"magnitude": 6.5, "lat": math.inf, "lon": 72.0},
    {"magnitude": 6.5, "lat": 90.1, "lon": 72.0},
    {"magnitude": 6.5, "lat": 34.0, "lon": -180.1},
])
def test_aftershock_input_rejects_invalid_modes_and_ranges(kwargs):
    with pytest.raises(ValidationError):
        AftershockForecastInput(**kwargs)


def test_aftershock_adapter_maps_validation_to_a_typed_failure():
    with pytest.raises(ToolFailure) as failure:
        get_aftershock_summary(None, magnitude=6.5, lat=91.0, lon=72.0)

    assert failure.value.code == "invalid_request"


def test_aftershock_tool_schema_advertises_ranges_and_exclusive_modes():
    parameters = get_aftershock_summary_tool()["function"]["parameters"]
    properties = parameters["properties"]

    assert properties["event_id"]["anyOf"][0]["minimum"] == 1
    assert properties["magnitude"]["anyOf"][0]["minimum"] == 0.0
    assert properties["magnitude"]["anyOf"][0]["maximum"] == 10.0
    assert properties["lat"]["anyOf"][0]["minimum"] == -90.0
    assert properties["lat"]["anyOf"][0]["maximum"] == 90.0
    assert properties["lon"]["anyOf"][0]["minimum"] == -180.0
    assert properties["lon"]["anyOf"][0]["maximum"] == 180.0
    assert len(parameters["oneOf"]) == 2
