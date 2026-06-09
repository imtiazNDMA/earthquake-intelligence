import numpy as np
from rasterio.transform import from_origin

from eqmon.contours import mmi_to_geojson


def test_filled_bands_produce_valid_featurecollection():
    # synthetic 50x50 MMI surface: a radial gradient high in the center
    n = 50
    yy, xx = np.mgrid[0:n, 0:n]
    cx = cy = n / 2
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    mmi = np.clip(9.0 - dist * 0.25, 1.0, 10.0).astype("float32")
    transform = from_origin(70.0, 32.0, 0.1, 0.1)

    fc = mmi_to_geojson(mmi, transform, levels=[3, 5, 7])

    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) >= 1
    for feat in fc["features"]:
        assert feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
        assert "mmi_lower" in feat["properties"]
        assert "color" in feat["properties"]


def test_higher_band_is_nested_inside_lower_band_area():
    n = 50
    yy, xx = np.mgrid[0:n, 0:n]
    dist = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2)
    mmi = np.clip(9.0 - dist * 0.25, 1.0, 10.0).astype("float32")
    transform = from_origin(70.0, 32.0, 0.1, 0.1)

    fc = mmi_to_geojson(mmi, transform, levels=[3, 5, 7])
    lowers = sorted(f["properties"]["mmi_lower"] for f in fc["features"])
    # the lowest band present should be the lowest requested level it reaches
    assert lowers[0] == 3


def test_levels_above_data_max_do_not_crash():
    # Regression: when the MMI surface peaks below the highest requested level,
    # the open top band's sentinel must stay above the last level so contourpy
    # never sees an upper bound below its lower bound.
    n = 30
    yy, xx = np.mgrid[0:n, 0:n]
    dist = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2)
    mmi = np.clip(6.0 - dist * 0.1, 1.0, 10.0).astype("float32")  # peaks at ~6
    transform = from_origin(70.0, 32.0, 0.1, 0.1)

    fc = mmi_to_geojson(mmi, transform, levels=[2, 3, 4, 5, 6, 7, 8, 9, 10])

    assert fc["type"] == "FeatureCollection"
    # no band should start at or above the data maximum (~6)
    assert all(f["properties"]["mmi_lower"] < 6 for f in fc["features"])
