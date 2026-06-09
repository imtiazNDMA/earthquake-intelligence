import os
from datetime import datetime, timedelta, timezone

import pytest

from eqmon.events.ingest import ingest, IngestResult
from eqmon.events.sources import RawEvent
from eqmon.events.repo import list_events

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _FakeSource:
    name = "USGS"
    def __init__(self, events): self._events = events
    def fetch(self, since=None): return list(self._events)


def test_ingest_inserts_and_is_idempotent(db_conn):
    src = _FakeSource([RawEvent("USGS", "a1", T0, 5.5, 10, 72.5, 34.0)])
    r1 = ingest(db_conn, src)
    assert isinstance(r1, IngestResult) and r1.inserted == 1
    r2 = ingest(db_conn, src)  # same event again
    assert r2.inserted == 0  # ON CONFLICT, no duplicate
    assert len(list_events(db_conn)) == 1


def test_dedup_clusters_close_events_and_prefers_met(db_conn):
    usgs = _FakeSource([RawEvent("USGS", "u1", T0, 5.5, 10, 72.50, 34.00)])
    met = _FakeSource([RawEvent("MET", "m1", T0 + timedelta(seconds=30), 5.6, 10, 72.55, 34.02)])
    ingest(db_conn, usgs)
    ingest(db_conn, met)
    canonical = list_events(db_conn)
    # one cluster -> one canonical event, and MET (Primary) wins
    assert len(canonical) == 1
    assert canonical[0]["source"] == "MET"


def test_far_apart_events_are_separate_clusters(db_conn):
    a = _FakeSource([RawEvent("USGS", "u1", T0, 5.5, 10, 72.5, 34.0)])
    b = _FakeSource([RawEvent("USGS", "u2", T0, 5.5, 10, 80.0, 40.0)])  # ~900 km away
    ingest(db_conn, a)
    ingest(db_conn, b)
    assert len(list_events(db_conn)) == 2
