"""Catalog adapters: `search_events` and `get_event_summary`."""
from __future__ import annotations

import psycopg

from ...events.repo import (catalog_coverage, count_events, get_event,
                            list_events)
from ...events.search import EventSearchSpec
from ..contracts import (MAX_EVENTS_IN_CONTEXT, CatalogCoverage, EventSummary,
                         SearchEventsResult, ToolFailure,
                         enforce_projection_size)


def _summarise(row: dict) -> EventSummary:
    """Project one catalog row onto the allowlist.

    Field-by-field rather than by exclusion: a column added to `_SELECT` later
    should not silently become visible to the model.
    """
    return EventSummary(
        id=row["id"],
        magnitude=row["magnitude"],
        mag_type=row.get("mag_type"),
        depth_km=row.get("depth_km"),
        lat=row["lat"],
        lon=row["lon"],
        place=row.get("place"),
        occurred_at=row["occurred_at"],
        source=row["source"],
        is_mainshock=row.get("is_mainshock"),
    )


def search_events(conn: psycopg.Connection,
                  spec: EventSearchSpec) -> SearchEventsResult:
    """Search the catalog and project the result for a model context.

    The spec's own `limit` governs the database read; the context cap is applied
    afterwards so `total` still reflects the real match count. A model told
    "3 of 812" can ask a better next question than one shown 3 and left to
    assume that is all of them.
    """
    filters = spec.model_dump()
    rows = list_events(conn, **filters)

    count_filters = {key: value for key, value in filters.items()
                     if key not in {"limit", "offset", "orderby"}}
    total = count_events(conn, **count_filters)
    coverage = catalog_coverage(conn)

    shown = rows[:MAX_EVENTS_IN_CONTEXT]
    result = SearchEventsResult(
        total=total,
        returned=len(shown),
        truncated=total > len(shown),
        events=[_summarise(row) for row in shown],
        catalog_coverage=CatalogCoverage(**coverage),
        distance_semantics=(
            "geodesic distance from the supplied WGS84 point to each event point"
            if spec.radius_km is not None else None),
    )
    return enforce_projection_size(result)


def get_event_summary(conn: psycopg.Connection, event_id: int) -> EventSummary:
    """One event, allowlisted.

    `get_event` reads `usgs_detail` — an unvalidated upstream product tree that
    must never reach a model — so the projection is mandatory, not an
    optimisation.
    """
    event = get_event(conn, event_id)
    if event is None:
        raise ToolFailure("not_found", f"no event with id {event_id}",
                          detail={"event_id": event_id})
    return _summarise(event)
