"""Ensure PROJ is pinned to rasterio's bundled DB before any geospatial import.

Importing the package runs eqmon._proj (see src/eqmon/_proj.py), the single
source of truth for this fix — shared by the test suite and the running app.
"""
import eqmon  # noqa: F401 — import side effect: pins PROJ_DATA/PROJ_LIB

import os
import psycopg
import pytest


@pytest.fixture()
def db_conn():
    """A connection wrapped in a transaction rolled back after each test.

    Schema is applied inside the transaction so tests are fully isolated and
    leave the test database empty. Skipped if DATABASE_URL_TEST is unset.
    """
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST not set")
    from eqmon.db import apply_schema
    conn = psycopg.connect(url)
    try:
        conn.autocommit = False
        apply_schema(conn)          # runs in the open transaction
        yield conn
    finally:
        conn.rollback()
        conn.close()
