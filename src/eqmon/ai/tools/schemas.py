"""Versioned model-facing tool schemas over deterministic contracts."""
from __future__ import annotations

from eqmon.aftershock_service import AftershockForecastInput
from eqmon.events.search import EVENT_SEARCH_SCHEMA_VERSION, EventSearchSpec
from eqmon.ai.contracts import ExposureSummaryInput, PlaceResolutionInput

SEARCH_EVENTS_TOOL_NAME = "search_events"
SEARCH_EVENTS_TOOL_SCHEMA_VERSION = "1.2"

GET_EVENT_SUMMARY_TOOL_NAME = "get_event_summary"
GET_EVENT_SUMMARY_TOOL_SCHEMA_VERSION = "1.0"
GET_EVENT_ANALYSIS_TOOL_SCHEMA_VERSION = "1.0"


def search_events_tool() -> dict:
    """OpenAI-compatible schema for the deterministic event search contract."""
    schema = EventSearchSpec.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": SEARCH_EVENTS_TOOL_NAME,
            "description": (
                "Search the earthquake event catalog when the user asks for "
                "earthquakes filtered by magnitude, source, time, coordinates, "
                "radius, or mainshock/aftershock state. Do not call this tool "
                "for general knowledge, writing, weather, or non-earthquake tasks. "
                f"Domain contract {EVENT_SEARCH_SCHEMA_VERSION}; model schema "
                f"{SEARCH_EVENTS_TOOL_SCHEMA_VERSION}."
            ),
            "parameters": schema,
        },
    }


def get_event_summary_tool() -> dict:
    """Schema for fetching one known event by catalog id.

    Takes an id rather than a description on purpose: resolving "the Quetta
    earthquake" to a row is a search, and conflating the two would let a model
    skip the step where the operator sees which event was chosen.
    """
    return {
        "type": "function",
        "function": {
            "name": GET_EVENT_SUMMARY_TOOL_NAME,
            "description": (
                "Fetch the summary of one earthquake by its catalog id. Use only "
                "when the id is already known, typically from a search_events "
                "result. To find an event from a description, call search_events "
                f"instead. Model schema {GET_EVENT_SUMMARY_TOOL_SCHEMA_VERSION}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "integer",
                        "description": "Catalog id of the event.",
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    }


def get_event_analysis_tool() -> dict:
    """Schema for one versioned modeled-impact artifact by catalog id."""
    return {
        "type": "function",
        "function": {
            "name": "get_event_analysis",
            "description": (
                "Get the versioned modeled MMI impact summary for one known "
                "catalog event. Use only when event_id is already known. Returns "
                "bounded administrative summaries and artifact evidence, not "
                "contour geometry. Do not use this to search for events. "
                f"Model schema {GET_EVENT_ANALYSIS_TOOL_SCHEMA_VERSION}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Catalog id of the event to analyze.",
                    },
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        },
    }


def get_exposure_summary_tool() -> dict:
    """Schema for versioned element exposure under a known event footprint."""
    return {
        "type": "function",
        "function": {
            "name": "get_exposure_summary",
            "description": (
                "Get population and infrastructure exposure at MMI VI and above "
                "for one known catalog event. Uses the event's versioned modeled "
                "impact and a versioned ARC release. Do not use this to search "
                "for events or infer casualties, damage, or risk."
            ),
            "parameters": ExposureSummaryInput.model_json_schema(),
        },
    }


def get_catalog_analytics_tool() -> dict:
    """Schema for headline catalog statistics over a time window."""
    return {
        "type": "function",
        "function": {
            "name": "get_catalog_analytics",
            "description": (
                "Statistics describing the earthquake catalog over a time "
                "window: b-value, completeness magnitude, event rates, and the "
                "most active tectonic zones. Use for questions about seismicity "
                "as a whole, not to look up individual earthquakes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window": {
                        "type": "string",
                        "enum": ["30d", "1y", "5y", "all"],
                        "description": "Time window, measured back from the "
                                       "newest event in the catalog.",
                    },
                    "min_mag": {
                        "type": "string",
                        "description": "Magnitude floor, or \"mc\" to use the "
                                       "estimated completeness magnitude.",
                    },
                },
                "required": ["window"],
                "additionalProperties": False,
            },
        },
    }


def get_aftershock_summary_tool() -> dict:
    """Schema for aftershock probabilities following a mainshock."""
    parameters = AftershockForecastInput.model_json_schema()
    parameters["oneOf"] = [
        {
            "required": ["event_id"],
            "not": {"anyOf": [
                {"required": ["magnitude"]},
                {"required": ["lat"]},
                {"required": ["lon"]},
            ]},
        },
        {
            "required": ["magnitude", "lat", "lon"],
            "not": {"required": ["event_id"]},
        },
    ]
    return {
        "type": "function",
        "function": {
            "name": "get_aftershock_summary",
            "description": (
                "Aftershock probabilities following a mainshock, by target "
                "magnitude and days elapsed. Provide event_id for a catalogued "
                "earthquake, or magnitude with lat and lon for a hypothetical "
                "one. Do not use this to search for earthquakes."
            ),
            "parameters": parameters,
        },
    }


def resolve_place_tool() -> dict:
    """Schema for resolving place text or coordinates to a boundary."""
    return {
        "type": "function",
        "function": {
            "name": "resolve_place",
            "description": (
                "Resolve a place name, coordinates, or both to Pakistani "
                "administrative boundaries. Returns status \"ambiguous\" when a "
                "name matches several boundaries — duplicate names are common, "
                "so ask the user which was meant rather than choosing one."
            ),
            "parameters": PlaceResolutionInput.model_json_schema(),
        },
    }
