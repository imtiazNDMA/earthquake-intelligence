"""Scheduler ingest-tick orchestration (no DB / network — fakes injected)."""
from types import SimpleNamespace
from datetime import datetime, timezone

from eqmon import api
from eqmon.events.ingest import IngestResult


class _FakeCur:
    def fetchone(self):
        return None


class _FakeConn:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        return _FakeCur()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeConnCtx:
    def __enter__(self):
        return _FakeConn()

    def __exit__(self, *exc):
        return False


def _fake_result():
    return SimpleNamespace(inserted=0, fetched=0, errors=[])


def test_ingest_tick_ingests_pmd_before_usgs(monkeypatch):
    api._pmd_tick_counter = 4  # after pre-increment → 5, a multiple → PMD runs
    order = []

    def fake_ingest(conn, source, updatedafter=None):
        order.append(source.name)
        return _fake_result()

    monkeypatch.setattr(api.db, "get_conn", lambda: _FakeConnCtx())
    monkeypatch.setattr(api, "ingest", fake_ingest)
    api._ingest_tick()
    # Primary (PMD) ingested before Secondary (USGS) so it wins as canonical.
    assert order == ["PMD", "USGS"]


def test_ingest_tick_continues_when_one_source_raises(monkeypatch):
    api._pmd_tick_counter = 4  # after pre-increment → 5, a multiple → PMD runs
    seen = []

    def fake_ingest(conn, source, updatedafter=None):
        seen.append(source.name)
        if source.name == "PMD":
            raise RuntimeError("PMD boom")
        return _fake_result()

    monkeypatch.setattr(api.db, "get_conn", lambda: _FakeConnCtx())
    monkeypatch.setattr(api, "ingest", fake_ingest)
    api._ingest_tick()
    # USGS still ingested despite PMD failing.
    assert "USGS" in seen


def test_ingest_tick_skips_pmd_on_non_multiple(monkeypatch):
    api._pmd_tick_counter = 0  # after pre-increment → 1, not a multiple → PMD skipped
    seen = []

    def fake_ingest(conn, source, updatedafter=None):
        seen.append(source.name)
        return _fake_result()

    monkeypatch.setattr(api.db, "get_conn", lambda: _FakeConnCtx())
    monkeypatch.setattr(api, "ingest", fake_ingest)
    api._ingest_tick()
    assert seen == ["USGS"]


def test_ingest_tick_skips_when_another_ingest_is_running(monkeypatch):
    seen = []

    def fake_ingest(conn, source, updatedafter=None):
        seen.append(source.name)
        return _fake_result()

    monkeypatch.setattr(api.db, "get_conn", lambda: _FakeConnCtx())
    monkeypatch.setattr(api, "ingest", fake_ingest)
    assert api._INGEST_LOCK.acquire(blocking=False)
    try:
        api._ingest_tick()
    finally:
        api._INGEST_LOCK.release()

    assert seen == []


def test_commit_successful_ingest_uses_upstream_watermark():
    conn = _FakeConn()
    watermark = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)

    api._commit_successful_ingest(
        conn,
        "usgs_last_sync",
        IngestResult("USGS", fetched=1, inserted=1, errors=[], watermark=watermark),
    )

    assert conn.commits == 1
    assert conn.rollbacks == 0
    params = conn.executed[-1][0][1]
    assert params == ("usgs_last_sync", watermark.isoformat(), watermark.isoformat())


def test_commit_successful_ingest_rolls_back_and_does_not_sync_on_errors():
    conn = _FakeConn()

    try:
        api._commit_successful_ingest(
            conn,
            "usgs_last_sync",
            IngestResult("USGS", fetched=1, inserted=0, errors=["row failed"]),
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    assert conn.rollbacks == 1
    assert conn.commits == 0
    assert conn.executed == []
