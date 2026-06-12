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
        "WHERE table_schema='public' AND table_name IN "
        "('seismic_event','admin_boundary','_schema_migrations')"
    ).fetchall()
    names = {r[0] for r in rows}
    assert names == {"seismic_event", "admin_boundary", "_schema_migrations"}


def test_migrations_are_recorded(db_conn):
    rows = db_conn.execute(
        "SELECT name FROM _schema_migrations ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    assert len(names) >= 1
    assert "001_initial_schema" in names


def test_postgis_available(db_conn):
    version = db_conn.execute("SELECT PostGIS_Lib_Version()").fetchone()[0]
    assert version  # non-empty version string
