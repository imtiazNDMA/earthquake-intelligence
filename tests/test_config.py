from eqmon import config


def test_default_site_condition_is_760():
    # CONTEXT.md: Default Site Condition uses fixed Vs30 760 m/s
    assert config.DEFAULT_VS30 == 760.0


def test_coverage_region_bbox_contains_pakistan_center():
    lon, lat = 69.3, 30.4  # roughly central Pakistan
    minx, miny, maxx, maxy = config.COVERAGE_BBOX
    assert minx <= lon <= maxx
    assert miny <= lat <= maxy


def test_mmi_band_levels_are_increasing():
    assert config.MMI_BAND_LEVELS == sorted(config.MMI_BAND_LEVELS)
    assert config.MMI_BAND_LEVELS[0] >= 1
    assert config.MMI_BAND_LEVELS[-1] <= 10
