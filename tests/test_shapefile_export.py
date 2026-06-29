import io
import zipfile

import fiona
import pytest

from eqmon.export import featurecollection_to_shapefile_zip


def _polygon_feature(mmi_low, mmi_high, color, x0=70.0, y0=30.0):
    ring = [[x0, y0], [x0 + 1, y0], [x0 + 1, y0 + 1], [x0, y0 + 1], [x0, y0]]
    return {
        "type": "Feature",
        "properties": {"mmi_lower": mmi_low, "mmi_upper": mmi_high, "color": color},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def test_zip_contains_all_shapefile_sidecars():
    data = featurecollection_to_shapefile_zip(
        _fc([_polygon_feature(6, 7, "#ffff00"), _polygon_feature(7, 8, "#ffc800", 71.0, 31.0)])
    )
    assert isinstance(data, bytes) and len(data) > 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        assert any(n.endswith(ext) for n in names), f"missing {ext} in {names}"


def test_roundtrip_preserves_attributes_geometry_and_crs(tmp_path):
    data = featurecollection_to_shapefile_zip(
        _fc([_polygon_feature(6, 7, "#ffff00"), _polygon_feature(7, 8, "#ffc800", 71.0, 31.0)])
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(tmp_path)
    shp = next(tmp_path.glob("*.shp"))
    with fiona.open(str(shp)) as src:
        assert src.crs.to_epsg() == 4326
        recs = list(src)
    assert len(recs) == 2
    props = {r["properties"]["mmi_low"]: r["properties"] for r in recs}
    assert props[6]["mmi_high"] == 7 and props[6]["color"] == "#ffff00"
    for r in recs:
        assert r["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_empty_featurecollection_raises():
    with pytest.raises(ValueError):
        featurecollection_to_shapefile_zip(_fc([]))


def test_non_polygon_features_are_skipped():
    point = {
        "type": "Feature",
        "properties": {"mmi_lower": 5, "mmi_upper": 6, "color": "#7aff93"},
        "geometry": {"type": "Point", "coordinates": [70.0, 30.0]},
    }
    data = featurecollection_to_shapefile_zip(_fc([point, _polygon_feature(6, 7, "#ffff00")]))
    with zipfile.ZipFile(io.BytesIO(data)) as zf, \
         zf.open(next(n for n in zf.namelist() if n.endswith(".shp"))):
        pass  # zip is valid
    # exactly one polygon survived
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(td)
        shp = next(p for p in os.listdir(td) if p.endswith(".shp"))
        with fiona.open(os.path.join(td, shp)) as src:
            assert len(list(src)) == 1


def test_all_points_raises():
    point = {
        "type": "Feature",
        "properties": {"mmi_lower": 5, "mmi_upper": 6, "color": "#7aff93"},
        "geometry": {"type": "Point", "coordinates": [70.0, 30.0]},
    }
    with pytest.raises(ValueError):
        featurecollection_to_shapefile_zip(_fc([point]))
