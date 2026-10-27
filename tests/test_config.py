from eqmon import config


def test_default_site_condition_is_760():
    # docs/reference/CONTEXT.md: Default Site Condition uses fixed Vs30 760 m/s
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


def test_analytics_tunables_present():
    from eqmon import config as c
    assert c.GRID_CELL_DEG == 0.25
    assert c.MC_MIN_N == 50 and c.BVALUE_MIN_N == 50
    assert c.DEPTH_CRUSTAL_MAX_KM == 35.0
    assert c.DEPTH_INTERMEDIATE_MAX_KM == 70.0
    assert c.MC_CORRECTION == 0.2 and c.MAG_BIN_WIDTH == 0.1


def test_ingest_cadence_defaults_and_env_overrides(monkeypatch):
    import importlib
    monkeypatch.delenv("EQMON_INGEST_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("EQMON_PMD_INTERVAL_MULTIPLIER", raising=False)
    importlib.reload(config)
    assert (config.INGEST_INTERVAL_MINUTES, config.PMD_INTERVAL_MULTIPLIER) == (1, 5)

    monkeypatch.setenv("EQMON_INGEST_INTERVAL_MINUTES", "10")
    monkeypatch.setenv("EQMON_PMD_INTERVAL_MULTIPLIER", "1")
    importlib.reload(config)
    assert (config.INGEST_INTERVAL_MINUTES, config.PMD_INTERVAL_MULTIPLIER) == (10, 1)

    monkeypatch.delenv("EQMON_INGEST_INTERVAL_MINUTES")
    monkeypatch.delenv("EQMON_PMD_INTERVAL_MULTIPLIER")
    importlib.reload(config)


def test_arc_url_gains_http_scheme_when_given_bare_hostport(monkeypatch):
    # Render's private-service `hostport` reference has no scheme.
    import importlib
    monkeypatch.setenv("ARC_URL", "eqmon-arc-x1y2:5000/")
    importlib.reload(config)
    assert config.ARC_URL == "http://eqmon-arc-x1y2:5000"

    monkeypatch.setenv("ARC_URL", "https://arc.example.org")
    importlib.reload(config)
    assert config.ARC_URL == "https://arc.example.org"

    monkeypatch.delenv("ARC_URL")
    importlib.reload(config)
