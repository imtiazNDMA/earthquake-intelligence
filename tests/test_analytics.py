import math
import numpy as np
from eqmon.analytics import mc_maxc


def test_mc_maxc_returns_peak_bin_plus_correction():
    # Peak of the non-cumulative FMD at magnitude 3.0 (>= MC_MIN_N samples).
    mags = ([3.0] * 200) + ([3.1] * 120) + ([2.9] * 80) + ([4.0] * 30) + ([5.0] * 10)
    assert mc_maxc(mags) == 3.2  # 3.0 peak + 0.2 correction


def test_mc_maxc_none_when_too_few():
    assert mc_maxc([3.0, 3.1, 3.2]) is None
