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
