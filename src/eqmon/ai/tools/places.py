"""Place-resolution adapter over the deterministic resolver."""
from __future__ import annotations

import psycopg

from .. import places as place_resolver
from ..contracts import (MAX_PLACE_CANDIDATES, BoundaryCandidateSummary,
                         PlaceResolutionResult, ToolFailure,
                         enforce_projection_size)


def _candidate(candidate: place_resolver.BoundaryCandidate
               ) -> BoundaryCandidateSummary:
    return BoundaryCandidateSummary(
        unit_id=candidate.unit_id, name=candidate.name, level=candidate.level,
        parent=candidate.parent, score=candidate.score,
    )


def resolve_place(conn: psycopg.Connection, probe: str = "", *,
                  lon: float | None = None, lat: float | None = None,
                  level: str | None = None,
                  parent: str | None = None) -> PlaceResolutionResult:
    """Resolve place text and/or coordinates to administrative boundaries.

    Passes through the resolver's four states unchanged. `ambiguous` and
    `conflict` are answers, not failures: collapsing them to a single best guess
    is precisely the behaviour the resolver was built to avoid, since duplicate
    administrative names are common and picking by row order is arbitrary.
    """
    try:
        resolution = place_resolver.resolve_place(
            conn, probe, lon=lon, lat=lat, level=level, parent=parent)
    except ValueError as exc:
        raise ToolFailure("invalid_request", str(exc)) from exc

    result = PlaceResolutionResult(
        status=resolution.status,
        method=resolution.method,
        match=_candidate(resolution.match) if resolution.match else None,
        candidates=[_candidate(candidate)
                    for candidate in resolution.candidates[:MAX_PLACE_CANDIDATES]],
        margin=resolution.margin,
    )
    return enforce_projection_size(result)
