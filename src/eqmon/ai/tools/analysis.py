"""Analysis adapters over versioned deterministic domain results."""
from __future__ import annotations

from datetime import datetime, timezone

import psycopg

from ...aftershock_service import EventNotFoundError, compute_forecast
from ...analytics_service import EmptyCatalogError, compute_analytics
from ...events.repo import get_event
from ...impact import get_or_compute_event_impact
from ...vs30 import get_grid
from ..contracts import (MAX_AFFECTED_UNITS_PER_LEVEL, MAX_ZONES_IN_CONTEXT,
                         AdminLevelImpactSummary, AffectedAdminUnitSummary,
                         AftershockProbability, AftershockSummaryResult,
                         CatalogAnalyticsResult, EventAnalysisResult,
                         EventSummary, LargestEvent, ModeledImpactSummary,
                         PlaceResolutionResult, ToolFailure, ZoneSummary,
                         enforce_projection_size)
from .events import project_event_summary


def _utc(value: str) -> datetime:
    """Parse a service timestamp and normalise it to UTC.

    `parse_window("all", ...)` anchors at 1900-01-01 in the *database session's*
    timezone, which for a named zone resolves to that era's local mean time —
    Asia/Karachi yields `+04:28:12`. That is valid ISO 8601 and unparseable by
    anything expecting whole-minute offsets. Normalising here keeps the quirk
    out of the model's view without changing the shape the API already returns.
    """
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def get_catalog_analytics(conn: psycopg.Connection, *, window: str = "1y",
                          min_mag: str = "mc", zone_id: int | None = None,
                          bbox: str | None = None) -> CatalogAnalyticsResult:
    """Headline catalog statistics for one slice.

    The service payload is built for a dashboard: a spatial grid, a
    frequency-magnitude histogram, a rate series, and up to a thousand scatter
    points. All four are dropped here — their meaning is the shape they draw,
    which a model cannot see and should not narrate.
    """
    try:
        payload = compute_analytics(conn, window=window, min_mag=min_mag,
                                    zone_id=zone_id, bbox=bbox)
    except EmptyCatalogError as exc:
        raise ToolFailure("not_found", str(exc)) from exc
    except ValueError as exc:
        raise ToolFailure("invalid_request", str(exc)) from exc

    provenance = payload["provenance"]
    kpis = payload["kpis"]
    largest = kpis.get("largest")

    result = CatalogAnalyticsResult(
        window_from=_utc(provenance["from"]),
        window_to=_utc(provenance["to"]),
        n_used=provenance["n_used"],
        n_excluded=provenance["n_excluded"],
        mc=kpis.get("mc"),
        b_value=kpis.get("b"),
        b_sigma=kpis.get("b_sigma"),
        b_n=kpis.get("b_n"),
        background_rate_per_year=kpis["background_rate"],
        total_rate_per_year=kpis["total_rate"],
        pct_aftershocks=kpis.get("pct_aftershocks"),
        active_sequences=kpis["active_sequences"],
        largest=LargestEvent(**largest) if largest else None,
        top_zones=[
            ZoneSummary(
                zone_id=zone["zone_id"], name=zone["name"], n=zone["n"],
                b_value=zone.get("b"), mc=zone.get("mc"),
                max_magnitude=zone["max_mag"],
                median_depth_km=zone.get("median_depth"),
                pct_aftershocks=zone.get("pct_aftershocks"),
            )
            # Already sorted by population; the tail is single-event zones.
            for zone in payload["zones"][:MAX_ZONES_IN_CONTEXT]
        ],
    )
    return enforce_projection_size(result)


def get_event_analysis(conn: psycopg.Connection, *,
                       event_id: int) -> EventAnalysisResult:
    """Compact modeled impact for one known catalog event.

    The artifact keeps the contour geometry and every administrative row. This
    projection exposes only the artifact evidence, source event, aggregate
    counts, and strongest bounded units.
    """
    if isinstance(event_id, bool) or not isinstance(event_id, int) or event_id < 1:
        raise ToolFailure("invalid_request", "event_id must be a positive integer")
    event = get_event(conn, event_id)
    if event is None:
        raise ToolFailure("not_found", f"no event with id {event_id}",
                          detail={"event_id": event_id})

    artifact = get_or_compute_event_impact(conn, event, get_grid()).artifact
    payload = artifact.payload
    band_levels = [
        feature["properties"]["mmi_lower"]
        for feature in payload.get("bands", {}).get("features", [])
    ]
    level_summaries = []
    for level in ("province", "district", "tehsil"):
        rows = payload.get("rollups", {}).get(level, [])
        affected = sorted(
            (row for row in rows if row["mmi_max"] > 0),
            key=lambda row: (-row["mmi_max"], -row["mmi_repr"],
                             row["name"], row["id"]),
        )
        level_summaries.append(AdminLevelImpactSummary(
            level=level,
            analyzed_units=len(rows),
            affected_units=len(affected),
            maximum_mmi_class=max(
                (row["mmi_max"] for row in affected), default=None),
            top_units=[AffectedAdminUnitSummary(
                unit_id=row["id"], name=row["name"], parent=row.get("parent"),
                maximum_mmi_class=row["mmi_max"],
                representative_mmi=row["mmi_repr"],
            ) for row in affected[:MAX_AFFECTED_UNITS_PER_LEVEL]],
        ))

    result = EventAnalysisResult(
        artifact_id=artifact.id,
        artifact_schema_version=artifact.schema_version,
        calculation_version=artifact.calculation_version,
        artifact_created_at=artifact.created_at,
        event=project_event_summary(event),
        modeled_impact=ModeledImpactSummary(
            maximum_mmi_class=max(band_levels, default=None),
            admin_levels=level_summaries,
        ),
    )
    return enforce_projection_size(result)


def get_aftershock_summary(conn: psycopg.Connection, *,
                           event_id: int | None = None,
                           magnitude: float | None = None,
                           lat: float | None = None, lon: float | None = None,
                           ) -> AftershockSummaryResult:
    """Aftershock probabilities for a catalog event or an inline point.

    The `params` block — k, c, p, alpha, Mref, productivity scale — is dropped.
    Those are calibration internals for the regional reference sequence, not
    statements about this one, and a model that can read them can quote them as
    findings.
    """
    try:
        payload = compute_forecast(conn, event_id=event_id, magnitude=magnitude,
                                   lat=lat, lon=lon)
    except EventNotFoundError as exc:
        raise ToolFailure("not_found", str(exc),
                          detail={"event_id": event_id}) from exc
    except ValueError as exc:
        raise ToolFailure("invalid_request", str(exc)) from exc

    event = payload.get("event")
    result = AftershockSummaryResult(
        mainshock_magnitude=payload["main_mag"],
        region=payload["region"],
        region_name=payload.get("region_name"),
        zone_name=payload.get("zone_name"),
        event=EventSummary(
            id=event["id"], magnitude=event["magnitude"],
            lat=event["lat"], lon=event["lon"], place=event.get("place"),
            occurred_at=event["occurred_at"], source=event["source"],
        ) if event else None,
        forecast=[
            AftershockProbability(
                days_since=row["DaysSince"],
                target_magnitude=row["Mtarget"],
                probability_pct=row["AftershockProb"],
            )
            for row in payload.get("probabilities", [])
        ],
        note=payload.get("note"),
    )
    return enforce_projection_size(result)
