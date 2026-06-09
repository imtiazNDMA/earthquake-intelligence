import os
import psycopg
import pytest

from eqmon.db import apply_schema

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"),
    reason="DATABASE_URL_TEST not set",
)


def test_apply_schema_creates_tables(db_conn):
    rows = db_conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name IN ('seismic_event','district')"
    ).fetchall()
    names = {r[0] for r in rows}
    assert names == {"seismic_event", "district"}


def test_postgis_available(db_conn):
    version = db_conn.execute("SELECT PostGIS_Lib_Version()").fetchone()[0]
    assert version  # non-empty version string
