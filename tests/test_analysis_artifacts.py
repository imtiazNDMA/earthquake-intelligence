"""Versioned, immutable deterministic analysis artifacts."""
from __future__ import annotations

import math
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg import sql

from eqmon.analysis_artifacts import (AnalysisKind, artifact_input_hash,
                                      get_or_compute_artifact)
from eqmon.db import apply_schema


def test_input_hash_is_canonical_for_key_order_numbers_and_utc_time():
    instant = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    first = artifact_input_hash(
        AnalysisKind.IMPACT,
        {"magnitude": 6.0, "event_id": 7, "at": instant},
        {"boundaries": "b", "vs30": "a"},
    )
    second = artifact_input_hash(
        AnalysisKind.IMPACT,
        {"at": instant.astimezone(timezone(timedelta(hours=5))),
         "event_id": 7, "magnitude": 6},
        {"vs30": "a", "boundaries": "b"},
    )

    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_input_hash_rejects_non_finite_numbers(value):
    with pytest.raises(ValueError, match="finite"):
        artifact_input_hash(
            AnalysisKind.ANALYTICS, {"magnitude": value}, {"catalog": "v1"})


pytest_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set")


def _resolve(db_conn, *, calculation_version="impact-1.0",
             data_fingerprint=None, compute=None):
    return get_or_compute_artifact(
        db_conn,
        kind=AnalysisKind.IMPACT,
        calculation_version=calculation_version,
        computation_input={"event_id": 7, "magnitude": 6.2},
        data_fingerprint=data_fingerprint or {"vs30": "a", "boundaries": "b"},
        provenance={"source": "USGS"},
        compute=compute or (lambda: {"bands": {}, "rollups": {}}),
    )


@pytest_db
def test_same_artifact_key_computes_once_and_reuses_id(db_conn):
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"bands": {}, "rollups": {}}

    first = _resolve(db_conn, compute=compute)
    second = _resolve(db_conn, compute=compute)

    assert first.created is True
    assert second.created is False
    assert first.artifact.id == second.artifact.id
    assert calls == 1


@pytest_db
def test_data_or_calculation_change_creates_a_new_artifact(db_conn):
    first = _resolve(db_conn)
    changed_data = _resolve(
        db_conn, data_fingerprint={"vs30": "changed", "boundaries": "b"})
    changed_calculation = _resolve(db_conn, calculation_version="impact-2.0")

    assert len({first.artifact.id, changed_data.artifact.id,
                changed_calculation.artifact.id}) == 3


@pytest_db
def test_failed_computation_stores_no_artifact(db_conn):
    def fail():
        raise RuntimeError("calculation failed")

    with pytest.raises(RuntimeError, match="calculation failed"):
        _resolve(db_conn, compute=fail)

    count = db_conn.execute("SELECT count(*) FROM analysis_artifact").fetchone()[0]
    assert count == 0


@pytest_db
@pytest.mark.parametrize("statement", [
    "UPDATE analysis_artifact SET payload = '{}'::jsonb WHERE id = %s",
    "DELETE FROM analysis_artifact WHERE id = %s",
])
def test_artifacts_are_immutable_in_the_database(db_conn, statement):
    artifact_id = _resolve(db_conn).artifact.id

    with pytest.raises(psycopg.Error, match="immutable"):
        with db_conn.transaction():
            db_conn.execute(statement, (artifact_id,))

    assert db_conn.execute(
        "SELECT count(*) FROM analysis_artifact WHERE id = %s", (artifact_id,)
    ).fetchone()[0] == 1


@pytest_db
def test_concurrent_same_key_computes_once_across_connections():
    url = os.environ["DATABASE_URL_TEST"]
    schema = f"artifact_test_{uuid.uuid4().hex}"
    create_schema = sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
    drop_schema = sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
    set_path = sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema))

    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(create_schema)
    try:
        with psycopg.connect(url) as setup:
            setup.execute(set_path)
            apply_schema(setup)

        calls = 0
        calls_lock = threading.Lock()

        def worker():
            nonlocal calls

            def compute():
                nonlocal calls
                with calls_lock:
                    calls += 1
                time.sleep(0.1)
                return {"bands": {}, "rollups": {}}

            with psycopg.connect(url) as conn:
                conn.execute(set_path)
                resolution = _resolve(conn, compute=compute)
                return resolution.artifact.id, resolution.created

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))

        assert calls == 1
        assert len({artifact_id for artifact_id, _ in results}) == 1
        assert sorted(created for _, created in results) == [False, True]
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(drop_schema)
