import math
import numpy as np

from eqmon.intensity import (
    epicentral_distance_m,
    pga_gal,
    pga_to_mmi,
    compute_mmi_grid,
)


def test_epicentral_distance_zero_at_epicenter():
    lon = np.array([[72.5]])
    lat = np.array([[34.0]])
    d = epicentral_distance_m(lon, lat, 72.5, 34.0)
    assert d.shape == (1, 1)
    assert d[0, 0] == 0.0


def test_epicentral_distance_one_degree_latitude_is_about_111km():
    # 1 degree of latitude is ~111.2 km on a great circle
    lon = np.array([[72.5]])
    lat = np.array([[35.0]])
    d = epicentral_distance_m(lon, lat, 72.5, 34.0)
    assert math.isclose(d[0, 0], 111_195.0, rel_tol=1e-3)


def _reference_pga_gal(dist_m, depth_m, mag, vs30):
    r = math.sqrt(dist_m**2 + depth_m**2) / 1000.0
    pga_g = 10 ** (0.49 + 0.23 * (mag - 6) - math.log10(r) - 0.0027 * r)
    pga = 1.385 * pga_g * 980.0
    arv = 10 ** (1.35 - 0.47 * math.log10(vs30))
    return pga * arv


def test_pga_gal_matches_reference_formula():
    dist = np.array([50_000.0])  # 50 km surface distance
    got = pga_gal(dist, depth_m=10_000.0, mag=6.5, vs30=np.array([760.0]))
    exp = _reference_pga_gal(50_000.0, 10_000.0, 6.5, 760.0)
    assert math.isclose(got[0], exp, rel_tol=1e-9)


def test_pga_decreases_with_distance():
    dist = np.array([10_000.0, 100_000.0])
    out = pga_gal(dist, depth_m=10_000.0, mag=6.5, vs30=np.array([760.0, 760.0]))
    assert out[0] > out[1]


def test_softer_soil_amplifies_pga():
    dist = np.array([50_000.0, 50_000.0])
    out = pga_gal(dist, depth_m=10_000.0, mag=6.5, vs30=np.array([300.0, 1000.0]))
    assert out[0] > out[1]  # lower Vs30 (softer) => higher PGA


def test_pga_to_mmi_uses_wald_segments_and_clamps():
    # high PGA -> high-intensity segment, clamped at 10
    assert pga_to_mmi(np.array([2000.0]))[0] <= 10.0
    # very low PGA -> clamped at 1, never below
    assert pga_to_mmi(np.array([0.001]))[0] >= 1.0
    # The two Wald segments are designed to meet at MMI 5: the low segment
    # reaches 5.0 at PGA ~= 65.8 gal, and the high segment gives ~4.99 there,
    # so the conversion is continuous across the crossover.
    near5 = pga_to_mmi(np.array([65.8]))[0]
    assert 4.7 < near5 < 5.3
    assert math.isclose(2.20 * math.log10(65.8) + 1.00,
                        3.66 * math.log10(65.8) - 1.66, abs_tol=0.05)


def test_compute_mmi_grid_shape_matches_input():
    lon = np.array([[70.0, 71.0]])
    lat = np.array([[30.0, 30.0]])
    vs30 = np.array([[760.0, 400.0]], dtype="float32")
    mmi = compute_mmi_grid(lon, lat, vs30, mag=6.5, depth_km=10.0, epi_lon=70.0, epi_lat=30.0)
    assert mmi.shape == (1, 2)
    assert np.all(mmi >= 1.0) and np.all(mmi <= 10.0)
