"""Tests for the aftershock probability computation module."""
import math

from eqmon.aftershock import (
    REGION_PARAMS,
    compute_table,
    detect_region,
    gutenberg_richter_scaling,
    omori_utsu_rate,
    aftershock_prob_per_day,
)


def test_detect_region_by_zone_keyword():
    assert detect_region(34.0, 73.0, zone_name="Kashmir Himalaya") == "northern"
    assert detect_region(30.0, 70.0, zone_name="Indus Basin") == "central"
    assert detect_region(26.0, 66.0, zone_name="Chaman Fault") == "southern"


def test_detect_region_fallback_lat_bands():
    assert detect_region(35.0, 70.0) == "northern"
    assert detect_region(30.0, 70.0) == "central"
    assert detect_region(25.0, 66.0) == "southern"


def test_detect_region_boundary_values():
    assert detect_region(33.5, 70.0) == "northern"
    assert detect_region(28.0, 70.0) == "central"
    assert detect_region(27.999, 70.0) == "southern"


def test_detect_region_no_zone_far_south_is_southern():
    assert detect_region(-10.0, 100.0) == "southern"


def test_gutenberg_richter_below_min():
    assert gutenberg_richter_scaling(3.0, b=0.85, Mmin=4.0) > 1.0


def test_gutenberg_richter_at_min():
    assert gutenberg_richter_scaling(4.0, b=0.85, Mmin=4.0) == 1.0


def test_gutenberg_richter_above_min():
    scaling = gutenberg_richter_scaling(5.0, b=0.85, Mmin=4.0)
    expected = 10 ** (-0.85 * (5.0 - 4.0))
    assert math.isclose(scaling, expected, rel_tol=1e-9)


def test_omori_utsu_rate_day_zero():
    rate = omori_utsu_rate(0, k=45.0, c=0.4, p=1.25)
    assert rate > 0


def test_omori_utsu_rate_decays():
    rate_0 = omori_utsu_rate(0, k=45.0, c=0.4, p=1.25)
    rate_30 = omori_utsu_rate(30, k=45.0, c=0.4, p=1.25)
    assert rate_0 > rate_30


def test_aftershock_prob_between_0_and_100():
    for region_key, params in REGION_PARAMS.items():
        prob, rate = aftershock_prob_per_day(0, 4.0, params)
        assert 0 <= prob <= 100
        assert rate > 0


def test_prob_increases_with_target_mag():
    params = REGION_PARAMS["northern"]
    prob_4, _ = aftershock_prob_per_day(1, 4.0, params)
    prob_7, _ = aftershock_prob_per_day(1, 7.0, params)
    assert prob_4 >= prob_7


def test_prob_decays_with_time():
    params = REGION_PARAMS["northern"]
    prob_0, _ = aftershock_prob_per_day(0, 5.0, params)
    prob_30, _ = aftershock_prob_per_day(30, 5.0, params)
    assert prob_0 >= prob_30


def test_compute_table_all_regions():
    for region_key in REGION_PARAMS:
        result = compute_table(7.0, region_key)
        assert result["main_mag"] == 7.0
        assert result["region"] == region_key
        assert len(result["probabilities"]) == len(result["days"]) * len(result["target_mags"])
        for r in result["probabilities"]:
            assert "DaysSince" in r
            assert "Mtarget" in r
            assert "AftershockProb" in r
            assert "OmoriRate" in r
            assert 0 <= r["AftershockProb"] <= 100


def test_compute_table_custom_days_and_mags():
    result = compute_table(6.0, "central", days=[0, 7], target_mags=[4, 5])
    assert result["days"] == [0, 7]
    assert result["target_mags"] == [4, 5]
    assert len(result["probabilities"]) == 4
    assert result["params"]["k"] > REGION_PARAMS["central"]["k"]
    assert result["params"]["Mref"] == REGION_PARAMS["central"]["Mref"]
    assert result["params"]["b"] == REGION_PARAMS["central"]["b"]


def test_northern_params_match_colab():
    p = REGION_PARAMS["northern"]
    assert p["k"] == 45.0
    assert p["c"] == 0.4
    assert p["p"] == 1.25
    assert p["b"] == 0.85
    assert p["Mmin"] == 4.0


def test_central_params_match_colab():
    p = REGION_PARAMS["central"]
    assert p["k"] == 40.0
    assert p["c"] == 0.3
    assert p["p"] == 1.1
    assert p["b"] == 0.9
    assert p["Mmin"] == 4.0


def test_southern_params_match_colab():
    p = REGION_PARAMS["southern"]
    assert p["k"] == 60.0
    assert p["c"] == 0.3
    assert p["p"] == 1.15
    assert p["b"] == 1.0
    assert p["Mmin"] == 4.0


def test_target_mags_capped_below_main():
    result = compute_table(5.5, "central")
    for t in result["target_mags"]:
        assert t < 5.5
    # M6 and M7 should be excluded; M3 is included as an extrapolated aid.
    assert 3 in result["target_mags"]
    assert 4 in result["target_mags"]
    assert 5 in result["target_mags"]
    assert 6 not in result["target_mags"]
    assert 7 not in result["target_mags"]


def test_all_mags_excluded_when_main_too_small():
    result = compute_table(3.0, "central")
    assert result["probabilities"] == []
    assert "note" in result
    assert result["target_mags"] == []


def test_only_mag3_remains_for_mag3_point_5():
    result = compute_table(3.5, "central")
    assert result["target_mags"] == [3]
    assert len(result["probabilities"]) == len(result["days"])


def test_mags_excluded_when_equal():
    """A magnitude equal to main_mag should be excluded."""
    result = compute_table(7.0, "northern")
    assert 7 not in result["target_mags"]


def test_publication_order_target_mags():
    """Smoke: M4.4 events report M3 extrapolated and M4 calibrated."""
    result = compute_table(4.4, "central")
    assert result["target_mags"] == [3, 4]
    assert len(result["probabilities"]) == len(result["days"]) * 2
    assert result["days"][0] == 1
    day_1 = {r["Mtarget"]: r["AftershockProb"] for r in result["probabilities"]
             if r["DaysSince"] == 1}
    assert day_1[3] > day_1[4]
