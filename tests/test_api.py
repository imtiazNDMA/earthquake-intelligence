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


def test_intensity_does_not_persist_to_catalog_by_default(tmp_path, monkeypatch):
    tif = tmp_path / "Vs30.tif"
    _make_grid_tif(tif)
    monkeypatch.setenv("EQMON_VS30_TIF", str(tif))
    from eqmon import api
    api.reset_grid_cache()

    calls = []
    monkeypatch.setattr(api, "create_manual_event",
                        lambda *a, **k: calls.append(1) or {"id": 1})
    # If the gate ever opened, this connection would be used:
    import contextlib

    class _FakeConn:
        def commit(self):
            pass

    @contextlib.contextmanager
    def _fake_get_conn():
        yield _FakeConn()

    monkeypatch.setattr(api.db, "get_conn", _fake_get_conn)

    client = TestClient(api.app)
    resp = client.post("/intensity", json={
        "magnitude": 6.5, "depth_km": 10.0, "lat": 30.0, "lon": 70.0,
    })
    assert resp.status_code == 200
    assert "event_id" not in resp.json()  # not saved
    assert calls == []  # create_manual_event never called


def test_intensity_persists_when_save_to_catalog_true(tmp_path, monkeypatch):
    tif = tmp_path / "Vs30.tif"
    _make_grid_tif(tif)
    monkeypatch.setenv("EQMON_VS30_TIF", str(tif))
    from eqmon import api
    api.reset_grid_cache()

    import contextlib

    class _FakeConn:
        def commit(self):
            pass

    @contextlib.contextmanager
    def _fake_get_conn():
        yield _FakeConn()

    monkeypatch.setattr(api.db, "get_conn", _fake_get_conn)
    monkeypatch.setattr(api, "create_manual_event", lambda conn, **k: {"id": 999})

    client = TestClient(api.app)
    resp = client.post("/intensity", json={
        "magnitude": 6.5, "depth_km": 10.0, "lat": 30.0, "lon": 70.0,
        "save_to_catalog": True,
    })
    assert resp.status_code == 200
    assert resp.json().get("event_id") == 999  # saved


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
