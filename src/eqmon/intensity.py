"""Ported intensity model. Replaces the arcpy `Expression.cal` field
calculator with vectorized NumPy. Geodesic distance via pyproj (matches the
original GEODESIC measurement); no ArcGIS."""
from __future__ import annotations
import numpy as np
from pyproj import Geod

_GEOD = Geod(ellps="WGS84")


def epicentral_distance_m(lon: np.ndarray, lat: np.ndarray,
                          epi_lon: float, epi_lat: float) -> np.ndarray:
    """Geodesic surface distance (metres) from epicenter to every cell center."""
    flat_lon = lon.ravel()
    flat_lat = lat.ravel()
    epi_lons = np.full(flat_lon.shape, epi_lon, dtype="float64")
    epi_lats = np.full(flat_lat.shape, epi_lat, dtype="float64")
    _, _, dist = _GEOD.inv(epi_lons, epi_lats, flat_lon, flat_lat)
    return np.asarray(dist, dtype="float64").reshape(lon.shape)


def pga_gal(dist_m: np.ndarray, depth_m: float, mag: float,
            vs30: np.ndarray) -> np.ndarray:
    """Site-amplified PGA in gal (cm/s^2), per the ported attenuation +
    amplification relations. `dist_m` is surface distance; depth completes the
    slant (hypocentral) distance."""
    r = np.sqrt(dist_m**2 + depth_m**2) / 1000.0  # km, guard r>0 below
    r = np.maximum(r, 1e-6)
    log_pga_g = 0.49 + 0.23 * (mag - 6.0) - np.log10(r) - 0.0027 * r
    pga = 1.385 * (10.0**log_pga_g) * 980.0
    arv = 10.0 ** (1.35 - 0.47 * np.log10(vs30))
    return pga * arv


def pga_to_mmi(pga: np.ndarray) -> np.ndarray:
    """Wald et al. (1999) PGA->MMI, PGA in gal. Two segments joined at MMI 5,
    clamped to [1, 10]."""
    pga = np.maximum(pga, 1e-6)
    log_pga = np.log10(pga)
    low = 2.20 * log_pga + 1.00
    high = 3.66 * log_pga - 1.66
    mmi = np.where(low <= 5.0, low, high)
    return np.clip(mmi, 1.0, 10.0)


def compute_mmi_grid(lon: np.ndarray, lat: np.ndarray, vs30: np.ndarray,
                     *, mag: float, depth_km: float,
                     epi_lon: float, epi_lat: float) -> np.ndarray:
    """End-to-end: epicenter + magnitude -> MMI at every grid cell."""
    dist = epicentral_distance_m(lon, lat, epi_lon, epi_lat)
    pga = pga_gal(dist, depth_m=depth_km * 1000.0, mag=mag, vs30=vs30)
    return pga_to_mmi(pga)
