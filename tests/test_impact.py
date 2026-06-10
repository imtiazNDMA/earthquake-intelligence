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
def test_compute_event_impact_reports_rollups_per_level(db_conn):
    from eqmon.vs30 import load_grid
    from eqmon.config import VS30_TIF
    from eqmon.events.repo import create_manual_event
    from eqmon.impact import compute_event_impact

    # one district + its enclosing province, both over the epicenter
    for level, name in [("province", "TestProv"), ("district", "Epi")]:
        db_conn.execute(
            "INSERT INTO admin_boundary (level, name, parent, geom) VALUES "
            "(%s, %s, 'TestProv', ST_Multi(ST_SetSRID("
            "ST_MakeEnvelope(72.0, 33.5, 73.0, 34.5), 4326)))",
            (level, name),
        )
    grid = load_grid(VS30_TIF)
    ev = create_manual_event(db_conn, magnitude=6.5, depth_km=10, lon=72.5, lat=34.0)
    impact = compute_event_impact(db_conn, ev, grid)

    assert impact["bands"]["type"] == "FeatureCollection"
    assert set(impact["rollups"]) == {"province", "district", "tehsil"}
    assert impact["rollups"]["tehsil"] == []          # none loaded
    epi = next(d for d in impact["rollups"]["district"] if d["name"] == "Epi")
    assert epi["parent"] == "TestProv"
    # worst-case band >= floored precise reading at the representative point
    assert epi["mmi_max"] >= int(epi["mmi_repr"])
    assert epi["mmi_repr"] >= 1.0
    assert isinstance(epi["mmi_repr"], float)
