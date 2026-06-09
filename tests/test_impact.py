import os
import numpy as np
import pytest
from rasterio.transform import from_origin

from eqmon.impact import sample_grid_at

# --- pure helper test (no DB) ---


def test_sample_grid_at_nearest_cell():
    arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype="float32")
    transform = from_origin(70.0, 32.0, 1.0, 1.0)  # cells: cols 70-72, rows 32-30
    # point in the lower-right cell (lon ~71.5, lat ~30.5) -> value 4.0
    vals = sample_grid_at(arr, transform, np.array([71.5]), np.array([30.5]))
    assert vals[0] == 4.0
    # point in the upper-left cell -> value 1.0
    vals2 = sample_grid_at(arr, transform, np.array([70.5]), np.array([31.5]))
    assert vals2[0] == 1.0


# --- impact integration test (DB) ---
pytest_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


@pytest_db
def test_compute_event_impact_reports_max_and_repr(db_conn):
    from eqmon.vs30 import load_grid
    from eqmon.config import VS30_TIF
    from eqmon.events.repo import create_manual_event
    from eqmon.impact import compute_event_impact

    # a small district square right over the epicenter
    db_conn.execute(
        "INSERT INTO district (name, province, geom) VALUES "
        "('Epi', 'Test', ST_Multi(ST_SetSRID("
        "ST_MakeEnvelope(72.0, 33.5, 73.0, 34.5), 4326)))"
    )
    grid = load_grid(VS30_TIF)
    ev = create_manual_event(db_conn, magnitude=6.5, depth_km=10, lon=72.5, lat=34.0)
    impact = compute_event_impact(db_conn, ev, grid)

    assert impact["bands"]["type"] == "FeatureCollection"
    epi = next(d for d in impact["districts"] if d["name"] == "Epi")
    assert epi["mmi_max"] >= epi["mmi_repr"]   # worst-case >= point value
    assert epi["mmi_repr"] >= 1.0
