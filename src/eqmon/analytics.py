"""Pure seismicity-analytics functions: magnitude-of-completeness, MLE b-value,
Gardner-Knopoff declustering, spatial grid, depth regimes, rate series, and
time-window parsing. No DB or HTTP dependencies so each is unit-testable."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from .config import (BVALUE_MIN_N, MAG_BIN_WIDTH, MC_CORRECTION, MC_MIN_N)
from .config import (DEPTH_CRUSTAL_MAX_KM, DEPTH_INTERMEDIATE_MAX_KM, GRID_CELL_DEG)


def mc_maxc(mags) -> float | None:
    """Maximum-Curvature magnitude of completeness: peak bin of the
    non-cumulative FMD plus MC_CORRECTION. None if fewer than MC_MIN_N values."""
    m = np.asarray(mags, dtype=float)
    if m.size < MC_MIN_N:
        return None
    lo = math.floor(m.min() / MAG_BIN_WIDTH) * MAG_BIN_WIDTH
    edges = np.arange(lo, m.max() + MAG_BIN_WIDTH, MAG_BIN_WIDTH)
    counts, _ = np.histogram(m, bins=edges)
    if counts.sum() == 0:
        return None
    peak_left = edges[int(np.argmax(counts))]
    peak_center = peak_left + MAG_BIN_WIDTH / 2.0
    return round(peak_center + MC_CORRECTION, 1)


def b_value_aki(mags, mc) -> tuple[float, float, int] | None:
    """Aki-Utsu maximum-likelihood b-value with Shi & Bolt (1982) uncertainty,
    over events with M >= mc. None if fewer than BVALUE_MIN_N or degenerate."""
    m = np.asarray(mags, dtype=float)
    sample = m[m >= mc - MAG_BIN_WIDTH / 2.0 + 1e-9]
    n = int(sample.size)
    if n < BVALUE_MIN_N:
        return None
    mean_m = float(sample.mean())
    denom = mean_m - (mc - MAG_BIN_WIDTH / 2.0)
    if denom <= 0:
        return None
    b = math.log10(math.e) / denom
    var = float(((sample - mean_m) ** 2).sum()) / (n * (n - 1))
    sigma = 2.30 * b * b * math.sqrt(var)
    return (round(b, 3), round(sigma, 3), n)


_EARTH_R_KM = 6371.0088


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_R_KM * math.asin(math.sqrt(a))


def _gk_windows(mag) -> tuple[float, float]:
    """Gardner & Knopoff (1974): interaction distance L (km) and time T (days)."""
    dist_km = 10 ** (0.1238 * mag + 0.983)
    if mag >= 6.5:
        time_days = 10 ** (0.032 * mag + 2.7389)
    else:
        time_days = 10 ** (0.5409 * mag - 0.547)
    return dist_km, time_days


def decluster_gardner_knopoff(events) -> list[tuple[bool, int]]:
    """Flag each event (is_mainshock, sequence_id). Largest-magnitude first;
    events inside a larger event's space-time window inherit its sequence.
    Symmetric time window captures foreshocks and aftershocks."""
    n = len(events)
    order = sorted(range(n), key=lambda i: (-events[i]["magnitude"], events[i]["occurred_at"]))
    assigned = [False] * n
    out: dict[int, tuple[bool, int]] = {}
    for i in order:
        if assigned[i]:
            continue
        assigned[i] = True
        main_id = events[i]["id"]
        out[i] = (True, main_id)
        dist_km, time_days = _gk_windows(events[i]["magnitude"])
        for j in range(n):
            if assigned[j] or j == i:
                continue
            dt = abs((events[j]["occurred_at"] - events[i]["occurred_at"]).total_seconds()) / 86400.0
            if dt > time_days:
                continue
            if _haversine_km(events[i]["lat"], events[i]["lon"],
                             events[j]["lat"], events[j]["lon"]) <= dist_km:
                assigned[j] = True
                out[j] = (False, main_id)
    return [out[i] for i in range(n)]


def spatial_grid(rows) -> list[dict]:
    if not rows:
        return []
    agg: dict[tuple[float, float], dict] = {}
    for r in rows:
        lon_low = math.floor(r["lon"] / GRID_CELL_DEG) * GRID_CELL_DEG
        lat_low = math.floor(r["lat"] / GRID_CELL_DEG) * GRID_CELL_DEG
        key = (round(lon_low, 4), round(lat_low, 4))
        cell = agg.setdefault(key, {"lon_low": key[0], "lat_low": key[1],
                                    "count": 0, "max_mag": None, "_depth_sum": 0.0})
        cell["count"] += 1
        cell["_depth_sum"] += float(r["depth_km"])
        m = float(r["magnitude"])
        if cell["max_mag"] is None or m > cell["max_mag"]:
            cell["max_mag"] = m
    out = []
    for cell in agg.values():
        cell["mean_depth"] = round(cell.pop("_depth_sum") / cell["count"], 1)
        out.append(cell)
    return out


def depth_regime_split(rows) -> dict:
    res = {"crustal": 0, "intermediate": 0, "deep": 0}
    for r in rows:
        d = float(r["depth_km"])
        if d < DEPTH_CRUSTAL_MAX_KM:
            res["crustal"] += 1
        elif d <= DEPTH_INTERMEDIATE_MAX_KM:
            res["intermediate"] += 1
        else:
            res["deep"] += 1
    return res


def rate_series(rows) -> list[dict]:
    buckets: dict[str, dict] = {}
    for r in rows:
        month = r["occurred_at"].strftime("%Y-%m")
        b = buckets.setdefault(month, {"month": month, "total": 0, "background": 0})
        b["total"] += 1
        if r.get("is_mainshock"):
            b["background"] += 1
    return [buckets[k] for k in sorted(buckets)]


def parse_window(window: str, anchor: datetime) -> tuple[datetime, datetime]:
    if window == "all":
        return (datetime(1900, 1, 1, tzinfo=anchor.tzinfo), anchor)
    spans = {"30d": timedelta(days=30), "1y": timedelta(days=365),
             "5y": timedelta(days=365 * 5)}
    if window not in spans:
        raise ValueError(f"invalid window: {window!r}")
    return (anchor - spans[window], anchor)
