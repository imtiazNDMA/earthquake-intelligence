"""Aftershock probability computation using Omori-Utsu + Gutenberg-Richter.

Region-specific parameters from the Colab notebooks for Northern, Central,
and Southern Pakistan.  Pure NumPy — no DB dependency.
"""

from __future__ import annotations

import numpy as np

REGION_PARAMS: dict[str, dict] = {
    "northern": {
        "name": "Northern Pakistan (Kashmir / Himalayan Thrust)",
        "k": 45.0, "c": 0.4, "p": 1.25, "b": 0.85, "Mmin": 4.0,
        "Mref": 7.6, "alpha": 1.0,
        "ref": "2005 Kashmir M7.6",
    },
    "central": {
        "name": "Central Pakistan (Indus Basin / Punjab)",
        "k": 40.0, "c": 0.3, "p": 1.1, "b": 0.9, "Mmin": 4.0,
        "Mref": 5.7, "alpha": 1.0,
        "ref": "2024 Karor M5.7",
    },
    "southern": {
        "name": "Southern Pakistan (Chaman Fault / Quetta)",
        "k": 60.0, "c": 0.3, "p": 1.15, "b": 1.0, "Mmin": 4.0,
        "Mref": 7.7, "alpha": 1.0,
        "ref": "1935 Quetta M7.7",
    },
}

# Lat-band fallback when tectonic-zone spatial lookup has no match.
_LAT_BANDS: list[tuple[float, float, str]] = [
    (33.5, 90.0, "northern"),
    (28.0, 33.5, "central"),
    (-90.0, 28.0, "southern"),
]

# Rough mapping of tectonic-zone keywords to region keys.
_ZONE_KEYWORDS: dict[str, str] = {
    "kashmir": "northern", "himalaya": "northern", "himalayan": "northern",
    "karakoram": "northern", "kohistan": "northern", "northern pakistan": "northern",
    "chaman": "southern", "makran": "southern", "balochistan": "southern",
    "baluchistan": "southern", "sulaiman": "southern", "kirthar": "southern",
    "quetta": "southern", "sibi": "southern",
}


def detect_region(lat: float, lon: float, zone_name: str | None = None) -> str:
    """Return a region key for the given coordinates / tectonic zone.

    Prefers the tectonic-zone keyword match (when *zone_name* is provided).
    Falls back to latitude bands.  Defaults to ``"central"``.
    """
    if zone_name:
        name_lower = zone_name.lower()
        for keyword, region in _ZONE_KEYWORDS.items():
            if keyword in name_lower:
                return region
    for lo, hi, region in _LAT_BANDS:
        if lo <= lat < hi:
            return region
    return "central"


def gutenberg_richter_scaling(
    Mtarget: float, b: float, Mmin: float,
) -> float:
    """Rate multiplier from M>=Mmin to M>=Mtarget.

    Targets below Mmin are extrapolated and therefore produce multipliers above
    1.0. Keep that visible in the API/UI as a completeness caveat.
    """
    return float(10.0 ** (-b * (Mtarget - Mmin)))


def omori_utsu_rate(t: int, k: float, c: float, p: float) -> float:
    """Expected number of M≥*Mmin* aftershocks on day *t*."""
    return round(k / ((t + c) ** p), 4)


def aftershock_prob_per_day(
    t: int, Mtarget: float, params: dict,
) -> tuple[float, float]:
    """Poisson probability (%) of ≥1 aftershock ≥*Mtarget* on day *t*.

    Returns ``(prob_pct, omori_rate)``.
    """
    lam_total = omori_utsu_rate(t, params["k"], params["c"], params["p"])
    mag_scale = gutenberg_richter_scaling(
        Mtarget, params["b"], params["Mmin"],
    )
    lam_target = lam_total * mag_scale
    prob = 1.0 - np.exp(-lam_target)
    return round(float(prob * 100.0), 2), lam_total


DEFAULT_DAYS = [1, 3, 5, 7, 14, 30]
DEFAULT_TARGET_MAGS = [3, 4, 5, 6, 7]
MIN_DISPLAY_MAG = 3.0


def _target_mags_for_model(main_mag: float, target_mags: list[float],
                           params: dict) -> list[float]:
    """Keep only model-supported targets.

    M3 is allowed as an extrapolated operator aid, but the calibrated catalog
    completeness remains Mmin. The forecast stays scoped to magnitudes below the
    current mainshock.
    """
    return sorted(set(m for m in target_mags if MIN_DISPLAY_MAG <= m < main_mag))


def _scale_params_for_mainshock(params: dict, main_mag: float) -> dict:
    """Scale reference-sequence productivity to the current mainshock size."""
    scaled = dict(params)
    factor = 10.0 ** (params.get("alpha", 1.0) * (main_mag - params["Mref"]))
    scaled["k"] = params["k"] * factor
    scaled["productivity_scale"] = factor
    return scaled


def compute_table(
    main_mag: float,
    region: str,
    days: list[int] | None = None,
    target_mags: list[float] | None = None,
) -> dict:
    """Compute full aftershock probability table.

    By default, only target magnitudes inside the calibrated completeness range
    are shown. Productivity is scaled from the regional reference sequence to
    the current mainshock magnitude.

    Returns a serialisable dict ready for the API response.
    """
    days = days or DEFAULT_DAYS
    params = REGION_PARAMS[region]
    target_mags = _target_mags_for_model(main_mag, target_mags or DEFAULT_TARGET_MAGS,
                                         params)
    forecast_params = _scale_params_for_mainshock(params, main_mag)

    if not target_mags:
        return {
            "main_mag": main_mag,
            "region": region,
            "region_name": params["name"],
            "params": {k: forecast_params[k] for k in (
                "k", "c", "p", "b", "Mmin", "Mref", "alpha", "productivity_scale")},
            "days": days,
            "target_mags": [],
            "probabilities": [],
            "note": "No target magnitudes fall below the mainshock and within the display range.",
        }

    rows: list[dict] = []
    for t in days:
        for mt in target_mags:
            prob, rate = aftershock_prob_per_day(t, mt, forecast_params)
            rows.append({
                "DaysSince": t,
                "Mtarget": mt,
                "AftershockProb": prob,
                "OmoriRate": rate,
            })

    return {
        "main_mag": main_mag,
        "region": region,
        "region_name": params["name"],
        "params": {k: forecast_params[k] for k in (
            "k", "c", "p", "b", "Mmin", "Mref", "alpha", "productivity_scale")},
        "days": days,
        "target_mags": target_mags,
        "probabilities": rows,
    }
