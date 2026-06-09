import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient


def _make_grid_tif(path):
    # 60x60 grid of uniform Vs30 covering ~6deg around an epicenter region
    arr = np.full((60, 60), 600.0, dtype="float32")
    transform = from_origin(67.0, 33.0, 0.1, 0.1)  # NW origin
    profile = dict(driver="GTiff", height=60, width=60, count=1,
                   dtype="float32", crs="EPSG:4326", transform=transform,
                   nodata=-9999.0)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)


def test_intensity_endpoint_returns_bands(tmp_path, monkeypatch):
    tif = tmp_path / "Vs30.tif"
    _make_grid_tif(tif)
    monkeypatch.setenv("EQMON_VS30_TIF", str(tif))

    from eqmon import api
    api.reset_grid_cache()  # ensure the env override is picked up
    client = TestClient(api.app)

    resp = client.post("/intensity", json={
        "magnitude": 6.5, "depth_km": 10.0, "lat": 30.0, "lon": 70.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 1


def test_intensity_rejects_out_of_region(tmp_path, monkeypatch):
    tif = tmp_path / "Vs30.tif"
    _make_grid_tif(tif)
    monkeypatch.setenv("EQMON_VS30_TIF", str(tif))
    from eqmon import api
    api.reset_grid_cache()
    client = TestClient(api.app)
    resp = client.post("/intensity", json={
        "magnitude": 6.5, "depth_km": 10.0, "lat": 0.0, "lon": 0.0,
    })
    assert resp.status_code == 422
