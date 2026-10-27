"""Catalog analytics orchestration, independent of the API.

The sequencing here is the part worth naming: completeness magnitude is
estimated from the *whole* time slice using a floor of -1, and only then is the
caller's magnitude floor applied. Estimating Mc from an already-filtered slice
would bias it upward toward whatever floor the caller happened to pass, so the
two passes are not interchangeable.

Failures are typed for the caller to map — the API turns `EmptyCatalogError`
into a 404 and `ValueError` into a 400 — because a service that raises
`HTTPException` cannot be called from a scheduler or a tool adapter.
"""
from __future__ import annotations

import numpy as np
import psycopg

from . import analytics as ana
from . import config
from .events.repo import analytics_rows, catalog_max_time

# The quality-gate minimum used for the first pass. Low enough to admit the
# whole catalog slice so Mc is estimated from an unfiltered magnitude sample.
_MC_ESTIMATION_FLOOR = -1.0

# Scatter plots stop being readable long before they stop being expensive.
_DEPTH_SCATTER_LIMIT = 1000


class EmptyCatalogError(LookupError):
    """No events at all, so there is no anchor time to window against."""


def compute_analytics(conn: psycopg.Connection, *, window: str = "1y",
                      min_mag: str = "mc", zone_id: int | None = None,
                      bbox: str | tuple[float, float, float, float] | None = None,
                      ) -> dict:
    """Full analytics payload for one catalog slice.

    `window` is parsed against the newest event time rather than wall-clock now,
    so a stale catalog yields a window over data that exists.
    """
    anchor = catalog_max_time(conn)
    if anchor is None:
        raise EmptyCatalogError("catalog is empty")

    from_dt, to_dt = ana.parse_window(window, anchor)
    box = _parse_bbox(bbox)

    rows = analytics_rows(conn, from_dt, to_dt, min_mag=_MC_ESTIMATION_FLOOR,
                          zone_id=zone_id, bbox=box)
    mags = [row["magnitude"] for row in rows]
    mc = ana.mc_maxc(mags)
    floor = _parse_floor(min_mag, mc)
    used = [row for row in rows if row["magnitude"] >= floor]

    b = ana.b_value_aki([row["magnitude"] for row in used], mc) if mc is not None else None
    n_years = max((to_dt - from_dt).days / 365.25, 1e-9)
    mains = [row for row in used if row["is_mainshock"]]
    largest = max(used, key=lambda row: row["magnitude"], default=None)
    sequences = {row["sequence_id"] for row in used
                 if not row["is_mainshock"] and row.get("sequence_id")}

    mag_types: dict[str, int] = {}
    for row in used:
        key = row.get("mag_type") or "unknown"
        mag_types[key] = mag_types.get(key, 0) + 1

    return {
        "provenance": {
            "from": from_dt.isoformat(), "to": to_dt.isoformat(),
            "n_used": len(used), "n_excluded": len(rows) - len(used),
            "mag_types": mag_types,
        },
        "kpis": {
            "b": b[0] if b else None, "b_sigma": b[1] if b else None,
            "b_n": b[2] if b else None, "mc": mc,
            "background_rate": round(len(mains) / n_years, 1),
            "total_rate": round(len(used) / n_years, 1),
            "pct_aftershocks": round(1 - (len(mains) / len(used)), 2) if used else None,
            "active_sequences": len(sequences),
            "largest": None if largest is None else {
                "magnitude": largest["magnitude"], "place": largest.get("place"),
                "occurred_at": largest["occurred_at"].isoformat()},
        },
        "grid": ana.spatial_grid(used),
        "zones": _zone_rollup(conn, used) if zone_id is None else [],
        "fmd": fmd_payload(used, mc),
        "depth": {"regimes": ana.depth_regime_split(used),
                  "scatter": [{"mag": row["magnitude"], "depth": row["depth_km"]}
                              for row in used[:_DEPTH_SCATTER_LIMIT]]},
        "rate": ana.rate_series(used),
    }


def fmd_payload(rows: list[dict], mc: float | None) -> dict:
    """Cumulative + incremental frequency-magnitude distribution for the
    Gutenberg-Richter plot."""
    if not rows:
        return {"bins": [], "incremental": [], "cumulative": [], "mc": mc}
    width = config.MAG_BIN_WIDTH
    mags = np.asarray([row["magnitude"] for row in rows], dtype=float)
    lo = np.floor(mags.min() / width) * width
    edges = np.arange(lo, mags.max() + width, width)
    incremental, _ = np.histogram(mags, bins=edges)
    cumulative = incremental[::-1].cumsum()[::-1]
    centers = [round(float(edge + width / 2), 2) for edge in edges[:-1]]
    return {"bins": centers, "incremental": incremental.tolist(),
            "cumulative": cumulative.tolist(), "mc": mc}


def _parse_bbox(bbox) -> tuple | None:
    if bbox is None or bbox == "":
        return None
    if isinstance(bbox, (tuple, list)):
        values = tuple(float(value) for value in bbox)
    else:
        try:
            values = tuple(float(part) for part in bbox.split(","))
        except ValueError as exc:
            raise ValueError("bad bbox") from exc
    if len(values) != 4:
        raise ValueError("bad bbox")
    return values


def _parse_floor(min_mag: str, mc: float | None) -> float:
    """The caller's magnitude floor; "mc" defers to the estimated completeness."""
    if min_mag == "mc":
        return mc if mc is not None else _MC_ESTIMATION_FLOOR
    try:
        return float(min_mag)
    except (TypeError, ValueError) as exc:
        raise ValueError("bad min_mag") from exc


def _zone_rollup(conn: psycopg.Connection, used: list[dict]) -> list[dict]:
    """Per-zone statistics, largest population first.

    Skipped when the caller already drilled into a single zone — the rollup
    would then be a one-row restatement of the headline figures.
    """
    grouped: dict[int, list[dict]] = {}
    for row in used:
        if row.get("zone_id"):
            grouped.setdefault(row["zone_id"], []).append(row)

    names = dict(conn.execute("SELECT id, name FROM tectonic_zone").fetchall())
    rollup = []
    for zone_id, rows in grouped.items():
        mags = [row["magnitude"] for row in rows]
        mc = ana.mc_maxc(mags)
        b = ana.b_value_aki(mags, mc) if mc is not None else None
        depths = sorted(row["depth_km"] for row in rows)
        rollup.append({
            "zone_id": zone_id, "name": names.get(zone_id, f"Zone {zone_id}"),
            "n": len(rows), "b": b[0] if b else None,
            "sigma": b[1] if b else None,
            "mc": mc, "median_depth": depths[len(depths) // 2],
            "max_mag": max(mags),
            "pct_aftershocks": round(
                1 - sum(1 for row in rows if row["is_mainshock"]) / len(rows), 2),
        })
    rollup.sort(key=lambda zone: zone["n"], reverse=True)
    return rollup
