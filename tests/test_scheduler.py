"""Scheduler ingest-tick orchestration (no DB / network — fakes injected)."""
from types import SimpleNamespace

from eqmon import api


class _FakeCur:
    def fetchone(self):
        return None


class _FakeConn:
    def execute(self, *args, **kwargs):
        return _FakeCur()

    def commit(self):
        pass


class _FakeConnCtx:
    def __enter__(self):
        return _FakeConn()

    def __exit__(self, *exc):
        return False


def _fake_result():
    return SimpleNamespace(inserted=0, fetched=0, errors=[])


def test_ingest_tick_ingests_met_before_usgs(monkeypatch):
    order = []

    def fake_ingest(conn, source, updatedafter=None):
        order.append(source.name)
        return _fake_result()

    monkeypatch.setattr(api.db, "get_conn", lambda: _FakeConnCtx())
    monkeypatch.setattr(api, "ingest", fake_ingest)
    api._ingest_tick()
    # Primary (MET) ingested before Secondary (USGS) so it wins as canonical.
    assert order == ["MET", "USGS"]


def test_ingest_tick_continues_when_one_source_raises(monkeypatch):
    seen = []

    def fake_ingest(conn, source, updatedafter=None):
        seen.append(source.name)
        if source.name == "MET":
            raise RuntimeError("MET boom")
        return _fake_result()

    monkeypatch.setattr(api.db, "get_conn", lambda: _FakeConnCtx())
    monkeypatch.setattr(api, "ingest", fake_ingest)
    api._ingest_tick()
    # USGS still ingested despite MET failing.
    assert "USGS" in seen
