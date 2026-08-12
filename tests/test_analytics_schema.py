import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)


def test_analytics_columns_and_zone_table_exist(db_conn):
    cols = {r[0] for r in db_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'seismic_event'"
    ).fetchall()}
    assert {"is_mainshock", "sequence_id", "zone_id"} <= cols

    zcols = {r[0] for r in db_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'tectonic_zone'"
    ).fetchall()}
    assert {"id", "name", "geom"} <= zcols
