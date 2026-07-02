"""Pure seismicity-analytics functions: magnitude-of-completeness, MLE b-value,
Gardner-Knopoff declustering, spatial grid, depth regimes, rate series, and
time-window parsing. No DB or HTTP dependencies so each is unit-testable."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np

from .config import (BVALUE_MIN_N, MAG_BIN_WIDTH, MC_CORRECTION, MC_MIN_N)


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
