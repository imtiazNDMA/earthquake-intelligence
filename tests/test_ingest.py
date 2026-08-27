import os
from datetime import datetime, timedelta, timezone

import pytest

from eqmon.events.ingest import ingest, IngestResult
from eqmon.events.sources import (
    FetchBatch, ParserReject, RawEvent, RejectReason,
)
from eqmon.events.repo import list_events

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _FakeSource:
    name = "USGS"
    def __init__(self, events): self._events = events
    def fetch(self, since=None, updatedafter=None): return list(self._events)


class _RejectingSource:
    name = "USGS"

    def __init__(self, events, rejects):
        self._batch = FetchBatch(events, rejects)

    def fetch_batch(self, since=None, updatedafter=None):
        return self._batch


def test_ingest_inserts_and_is_idempotent(db_conn):
    src = _FakeSource([RawEvent("USGS", "a1", T0, 5.5, 10, 72.5, 34.0)])
    r1 = ingest(db_conn, src)
    assert isinstance(r1, IngestResult) and r1.inserted == 1
    r2 = ingest(db_conn, src)  # same event again
    assert r2.inserted == 0  # ON CONFLICT, no duplicate
    assert len(list_events(db_conn)) == 1


def test_ingest_persists_typed_rejects_without_dropping_valid_events(db_conn):
    source_record = {"id": "bad-1", "properties": {"mag": None}}
    reject = ParserReject(
        source="USGS",
        reason_code=RejectReason.MISSING_MAGNITUDE,
        source_event_id="bad-1",
        parser_version="usgs-1",
        payload_sha256="a" * 64,
        source_record=source_record,
        retrieval_metadata={"url": "https://example.test/feed"},
    )
    source = _RejectingSource(
        [RawEvent("USGS", "accepted-1", T0, 5.5, 10, 72.5, 34.0)],
        [reject],
    )

    first = ingest(db_conn, source)
    second = ingest(db_conn, source)

    assert first.fetched == 1
    assert first.inserted == 1
    assert first.rejected == 1
    assert first.errors == []
    assert second.rejected == 1
    row = db_conn.execute(
        "SELECT source, source_event_id, reason_code, parser_version, "
        "payload_sha256, source_record, retrieval_metadata, seen_count "
        "FROM ingest_reject WHERE source_event_id = 'bad-1'"
    ).fetchone()
    assert row == (
        "USGS", "bad-1", "missing_magnitude", "usgs-1", "a" * 64,
        source_record, {"url": "https://example.test/feed"}, 2,
    )


def test_ingest_reports_reject_capture_failure_before_sync_can_advance(db_conn):
    reject = ParserReject(
        source="USGS",
        reason_code=RejectReason.MISSING_MAGNITUDE,
        source_event_id="bad-hash",
        parser_version="usgs-1",
        payload_sha256="not-a-sha256",
        source_record={"id": "bad-hash"},
        retrieval_metadata={},
    )
    source = _RejectingSource(
        [RawEvent("USGS", "accepted-before-error", T0, 5.5, 10, 72.5, 34.0)],
        [reject],
    )

    result = ingest(db_conn, source)

    assert result.inserted == 1
    assert result.rejected == 1
    assert len(result.errors) == 1
    assert result.errors[0].startswith("reject bad-hash:")


def test_ingest_updates_existing_event_when_upstream_revision_is_newer(db_conn):
    original = RawEvent("USGS", "u-revised", T0, 5.0, 20, 72.5, 34.0,
                        place="original", updated_at=T0)
    revised = RawEvent("USGS", "u-revised", T0 + timedelta(seconds=5), 6.2, 12,
                       72.7, 34.2, place="revised",
                       updated_at=T0 + timedelta(minutes=10))

    assert ingest(db_conn, _FakeSource([original])).inserted == 1
    assert ingest(db_conn, _FakeSource([revised])).inserted == 0

    row = db_conn.execute(
        "SELECT magnitude, depth_km, ST_X(geom), ST_Y(geom), place, updated_at "
        "FROM seismic_event WHERE source='USGS' AND source_event_id='u-revised'"
    ).fetchone()
    assert row[0] == 6.2
    assert row[1] == 12
    assert round(row[2], 1) == 72.7
    assert round(row[3], 1) == 34.2
    assert row[4] == "revised"
    assert row[5] == T0 + timedelta(minutes=10)


def test_ingest_does_not_overwrite_with_older_upstream_revision(db_conn):
    newer = RawEvent("USGS", "u-older", T0, 6.0, 10, 72.5, 34.0,
                     place="newer", updated_at=T0 + timedelta(minutes=10))
    older = RawEvent("USGS", "u-older", T0, 5.0, 10, 72.5, 34.0,
                     place="older", updated_at=T0)

    ingest(db_conn, _FakeSource([newer]))
    ingest(db_conn, _FakeSource([older]))

    row = db_conn.execute(
        "SELECT magnitude, place, updated_at FROM seismic_event "
        "WHERE source='USGS' AND source_event_id='u-older'"
    ).fetchone()
    assert row[0] == 6.0
    assert row[1] == "newer"
    assert row[2] == T0 + timedelta(minutes=10)


def test_dedup_clusters_close_events_and_prefers_pmd(db_conn):
    usgs = _FakeSource([RawEvent("USGS", "u1", T0, 5.5, 10, 72.50, 34.00)])
    pmd = _FakeSource([RawEvent("PMD", "m1", T0 + timedelta(seconds=30), 5.6, 10, 72.55, 34.02)])
    ingest(db_conn, usgs)
    ingest(db_conn, pmd)
    canonical = list_events(db_conn)
    # one cluster -> one canonical event, and PMD (Primary) wins
    assert len(canonical) == 1
    assert canonical[0]["source"] == "PMD"


def test_far_apart_events_are_separate_clusters(db_conn):
    a = _FakeSource([RawEvent("USGS", "u1", T0, 5.5, 10, 72.5, 34.0)])
    b = _FakeSource([RawEvent("USGS", "u2", T0, 5.5, 10, 80.0, 40.0)])  # ~900 km away
    ingest(db_conn, a)
    ingest(db_conn, b)
    assert len(list_events(db_conn)) == 2


def test_ingest_sets_mainshock_and_sequence(db_conn):
    from eqmon.events.ingest import ingest
    main = _FakeSource([RawEvent("USGS", "m", T0, 6.0, 10, 72.0, 34.0)])
    after = _FakeSource([RawEvent("USGS", "a", T0 + timedelta(hours=2), 4.0, 10, 72.05, 34.05)])
    ingest(db_conn, main)
    ingest(db_conn, after)
    rows = db_conn.execute(
        "SELECT source_event_id, is_mainshock, sequence_id FROM seismic_event "
        "WHERE source='USGS' ORDER BY magnitude DESC"
    ).fetchall()
    # largest is a mainshock; the smaller one is its aftershock (shares sequence)
    assert rows[0][1] is True
    assert rows[1][1] is False
    assert rows[1][2] == rows[0][2]


def test_ingest_assigns_zone_id(db_conn):
    from eqmon.events.ingest import ingest
    db_conn.execute(
        "INSERT INTO tectonic_zone (name, geom) VALUES ('Z', "
        "ST_SetSRID(ST_GeomFromText('MULTIPOLYGON(((71 33,73 33,73 35,71 35,71 33)))'),4326))"
    )
    ingest(db_conn, _FakeSource([RawEvent("USGS", "z", T0, 5.0, 10, 72.0, 34.0)]))
    zone = db_conn.execute(
        "SELECT zone_id FROM seismic_event WHERE source_event_id='z'"
    ).fetchone()[0]
    assert zone is not None
