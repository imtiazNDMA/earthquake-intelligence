from pathlib import Path

import fiona
import rasterio
from fiona.crs import CRS
from shapely.geometry import Polygon, mapping


def _load_script(name: str):
    import importlib.util
    import sys

    path = Path(__file__).parents[1] / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_region_restores_class_mask_and_nodata(tmp_path):
    script = _load_script("prepare_landslide_data.py")
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()
    schema = {"geometry": "Polygon", "properties": {"gridcode": "int"}}
    path = source_dir / "Test.shp"
    with fiona.open(path, "w", driver="ESRI Shapefile", schema=schema,
                    crs=CRS.from_epsg(32643)) as sink:
        sink.write({
            "geometry": mapping(Polygon([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)])),
            "properties": {"gridcode": 5},
        })
        # Self-intersection exercises deterministic geometry repair.
        sink.write({
            "geometry": mapping(Polygon([(20, 0), (40, 20), (20, 20), (40, 0), (20, 0)])),
            "properties": {"gridcode": 5},
        })

    region = script.Region("Test", "Test region", "Test", 32643, 10.0)
    result = script.build_region(region, source_dir, output_dir)

    assert result["feature_count"] == 2
    assert result["repaired_count"] == 1
    with rasterio.open(output_dir / "test.tif") as dataset:
        values = dataset.read(1)
        assert dataset.nodata == 255
        assert set(values.ravel()) <= {5, 255}
        assert (values == 5).any()


def test_build_region_rejects_unexpected_class(tmp_path):
    script = _load_script("prepare_landslide_data.py")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    path = source_dir / "Test.shp"
    schema = {"geometry": "Polygon", "properties": {"gridcode": "int"}}
    with fiona.open(path, "w", driver="ESRI Shapefile", schema=schema,
                    crs=CRS.from_epsg(32643)) as sink:
        sink.write({
            "geometry": mapping(Polygon([(0, 0), (10, 0), (10, 10), (0, 0)])),
            "properties": {"gridcode": 4},
        })

    region = script.Region("Test", "Test region", "Test", 32643, 10.0)
    try:
        script.build_region(region, source_dir, tmp_path / "output")
    except ValueError as error:
        assert "expected 5" in str(error)
    else:
        raise AssertionError("unexpected class was accepted")
