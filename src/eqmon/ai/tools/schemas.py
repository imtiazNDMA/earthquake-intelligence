"""Versioned model-facing tool schemas over deterministic contracts."""
from __future__ import annotations

from eqmon.events.search import EVENT_SEARCH_SCHEMA_VERSION, EventSearchSpec

SEARCH_EVENTS_TOOL_NAME = "search_events"
SEARCH_EVENTS_TOOL_SCHEMA_VERSION = "1.2"


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
