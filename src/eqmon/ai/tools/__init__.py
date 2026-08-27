"""Authorized adapters over deterministic domain services.

Each adapter is the only route by which a model reaches a domain capability. It
validates the request, calls the domain service, and projects the result down to
its contract in `ai/contracts.py`. No seismology lives here — an adapter that
computes anything is a domain service in the wrong directory.

The model-facing JSON schemas live in `schemas.py` and are re-exported here so
`eqmon.ai.tools` keeps its original import surface.
"""
from .schemas import (SEARCH_EVENTS_TOOL_NAME, SEARCH_EVENTS_TOOL_SCHEMA_VERSION,
                      search_events_tool)

__all__ = [
    "SEARCH_EVENTS_TOOL_NAME",
    "SEARCH_EVENTS_TOOL_SCHEMA_VERSION",
    "search_events_tool",
]
