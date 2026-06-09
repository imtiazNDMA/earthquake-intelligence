"""PostGIS access: a lazily-created connection pool plus schema helpers.

Repository/ingest/impact functions take an explicit psycopg connection so tests
can run inside a rolled-back transaction. The API acquires a pooled connection
via get_conn()."""
from __future__ import annotations
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema.sql"

_pool: ConnectionPool | None = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(_database_url(), min_size=1, max_size=8, open=True)
    return _pool


@contextmanager
def get_conn():
    """Yield a pooled connection (autocommit). For request handlers."""
    with get_pool().connection() as conn:
        yield conn


def apply_schema(conn: psycopg.Connection) -> None:
    """Apply schema.sql on the given connection (idempotent)."""
    conn.execute(SCHEMA_PATH.read_text())


def init_schema() -> None:
    """Apply schema to the configured DATABASE_URL (CLI / startup convenience)."""
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        apply_schema(conn)
