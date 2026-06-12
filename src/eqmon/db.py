"""PostGIS access: a lazily-created connection pool plus schema helpers +
migration runner.

Repository/ingest/impact functions take an explicit psycopg connection so tests
can run inside a rolled-back transaction. The API acquires a pooled connection
via get_conn().

Migrations live in `migrations/*.sql` and are applied in filename order. The
tracking table `_schema_migrations` records what's been applied, making the
system idempotent across environments."""
from __future__ import annotations
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

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
    """Yield a pooled connection for a request handler.

    The connection is transactional (autocommit is OFF); psycopg's pool commits
    on clean block exit and rolls back if the block raises. Write handlers may
    also commit explicitly mid-block when they need the effect visible before
    returning.
    """
    with get_pool().connection() as conn:
        yield conn


def apply_schema(conn: psycopg.Connection) -> None:
    """Apply all pending migrations from `migrations/*.sql` in filename order.

    Idempotent: the tracking table `_schema_migrations` records every applied
    migration. Works inside a transaction (used by the test fixture).
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_migrations ("
        "  name TEXT PRIMARY KEY,"
        "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")"
    )
    applied = {r[0] for r in conn.execute(
        "SELECT name FROM _schema_migrations"
    ).fetchall()}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.stem not in applied:
            conn.execute(path.read_text())
            conn.execute(
                "INSERT INTO _schema_migrations (name) VALUES (%s)",
                (path.stem,),
            )


def init_schema() -> None:
    """Apply PostGIS extension + all pending migrations to the configured
    DATABASE_URL (CLI / startup convenience)."""
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        apply_schema(conn)
