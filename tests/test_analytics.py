import math
import numpy as np
from eqmon.analytics import mc_maxc
from eqmon.analytics import b_value_aki


def test_mc_maxc_returns_peak_bin_plus_correction():
    # Peak of the non-cumulative FMD at magnitude 3.0 (>= MC_MIN_N samples).
    mags = ([3.0] * 200) + ([3.1] * 120) + ([2.9] * 80) + ([4.0] * 30) + ([5.0] * 10)
    assert mc_maxc(mags) == 3.2  # 3.0 peak + 0.2 correction


def test_mc_maxc_none_when_too_few():
    assert mc_maxc([3.0, 3.1, 3.2]) is None


def test_b_value_recovers_known_slope():
    # Synthetic GR sample with true b = 1.0 above Mc = 3.0.
    rng = np.random.default_rng(42)
    mc = 3.0
    # exponential in (M - Mc) with rate b*ln(10) -> b=1.0
    draws = rng.exponential(scale=1.0 / (1.0 * math.log(10)), size=20000)
    # Start at the completeness bin's lower edge (Mc - Δ/2) so the Mc bin is
    # fully populated — this is what the Utsu bin correction assumes.
    mags = np.round((mc - 0.05 + draws) / 0.1) * 0.1
    b, sigma, n = b_value_aki(mags, mc)
    assert abs(b - 1.0) < 0.05
    assert sigma > 0 and n > 10000


def test_b_value_none_when_too_few():
    assert b_value_aki([3.0, 3.1, 3.2, 3.3], 3.0) is None


def test_b_value_none_when_no_spread():
    # All 60 magnitudes identical -> zero variance -> b is meaningless -> None.
    mags = [3.0] * 60
    assert b_value_aki(mags, 3.0) is None


from datetime import datetime, timedelta, timezone
from eqmon.analytics import decluster_gardner_knopoff

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_decluster_groups_aftershock_and_separates_distant():
    events = [
        {"id": 1, "occurred_at": T0, "lat": 34.0, "lon": 72.0, "magnitude": 6.0},
        # 2 hours later, 10 km away -> inside M6 window -> aftershock of #1
        {"id": 2, "occurred_at": T0 + timedelta(hours=2), "lat": 34.05, "lon": 72.05, "magnitude": 4.0},
        # far away in space -> its own mainshock
        {"id": 3, "occurred_at": T0 + timedelta(hours=3), "lat": 40.0, "lon": 80.0, "magnitude": 5.0},
    ]
    flags = decluster_gardner_knopoff(events)
    assert flags[0] == (True, 1)
    assert flags[1] == (False, 1)
    assert flags[2] == (True, 3)


from eqmon.analytics import (spatial_grid, depth_regime_split, rate_series, parse_window)


def test_spatial_grid_bins_and_aggregates():
    rows = [
        {"lat": 34.1, "lon": 72.1, "magnitude": 4.0, "depth_km": 10.0},
        {"lat": 34.2, "lon": 72.2, "magnitude": 5.0, "depth_km": 20.0},  # same 0.25 cell
        {"lat": 40.0, "lon": 80.0, "magnitude": 3.0, "depth_km": 30.0},  # other cell
    ]
    cells = {(c["lon_low"], c["lat_low"]): c for c in spatial_grid(rows)}
    a = cells[(72.0, 34.0)]
    assert a["count"] == 2 and a["max_mag"] == 5.0 and a["mean_depth"] == 15.0
    assert (80.0, 40.0) in cells


def test_depth_regime_split_boundaries():
    rows = [{"depth_km": d} for d in [0, 34.9, 35.0, 70.0, 70.1, 200]]
    r = depth_regime_split(rows)
    assert r == {"crustal": 2, "intermediate": 2, "deep": 2}


def test_rate_series_total_vs_background():
    rows = [
        {"occurred_at": datetime(2026, 1, 5, tzinfo=timezone.utc), "is_mainshock": True},
        {"occurred_at": datetime(2026, 1, 20, tzinfo=timezone.utc), "is_mainshock": False},
        {"occurred_at": datetime(2026, 2, 3, tzinfo=timezone.utc), "is_mainshock": True},
    ]
    series = {s["month"]: s for s in rate_series(rows)}
    assert series["2026-01"]["total"] == 2 and series["2026-01"]["background"] == 1
    assert series["2026-02"]["total"] == 1 and series["2026-02"]["background"] == 1


def test_parse_window():
    anchor = datetime(2026, 7, 1, tzinfo=timezone.utc)
    f, t = parse_window("1y", anchor)
    assert t == anchor and f == anchor - timedelta(days=365)
    f2, _ = parse_window("all", anchor)
    assert f2.year <= 1970
    import pytest
    with pytest.raises(ValueError):
        parse_window("bogus", anchor)
