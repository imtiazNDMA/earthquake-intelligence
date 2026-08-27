"""Event tool adapters: what the model is allowed to see.

`list_events` returns 28 columns and `get_event` returns the raw `usgs_detail`
product tree. Neither belongs in a model context — partly for size, mostly
because every field handed to a model is a field it can quote back as fact. The
adapters exist to make that allowlist explicit and testable rather than leaving
it to whoever writes the prompt.
"""
import os
from datetime import datetime, timezone

import pytest

from eqmon.ai.contracts import MAX_EVENTS_IN_CONTEXT, EventSummary
from eqmon.ai.tools.events import get_event_summary, search_events
from eqmon.events.search import EventSearchSpec

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)

_ALLOWED = {"id", "magnitude", "mag_type", "depth_km", "lat", "lon", "place",
            "occurred_at", "source", "is_mainshock"}


def _seed(conn, count: int = 40):
    for i in range(count):
        conn.execute(
            "INSERT INTO seismic_event (source, source_event_id, occurred_at,"
            " magnitude, depth_km, geom, is_canonical, is_mainshock, place,"
            " url, detail_url, usgs_detail)"
            " VALUES ('USGS', %s, %s, %s, 12, ST_SetSRID(ST_MakePoint(72,34),4326),"
            " TRUE, TRUE, %s, 'http://example/u', 'http://example/d', %s)",
            (f"t{i}", datetime(2026, 5, 1, tzinfo=timezone.utc), 4.0 + i * 0.05,
             f"Quetta area {i}", '{"products": {"shakemap": ["huge"]}}'))


def test_search_returns_only_allowlisted_fields(db_conn):
    _seed(db_conn)
    result = search_events(db_conn, EventSearchSpec(min_magnitude=4.0))
    assert result.returned > 0
    assert set(result.events[0].model_dump()) == _ALLOWED


def test_search_never_exposes_urls_or_raw_usgs_detail(db_conn):
    """A model that can see `usgs_detail` can quote from an unvalidated product
    tree; a model that can see a URL can present it as a citation."""
    _seed(db_conn)
    payload = search_events(db_conn, EventSearchSpec(min_magnitude=4.0)).model_dump_json()
    for leaked in ("usgs_detail", "detail_url", "shakemap", "example"):
        assert leaked not in payload


def test_result_count_is_capped_below_the_spec_limit(db_conn):
    """`EventSearchSpec` admits limit=200, which is fine for a UI table and far
    too much for a context window. The adapter caps independently."""
    _seed(db_conn, count=40)
    result = search_events(db_conn, EventSearchSpec(min_magnitude=0.0, limit=200))
    assert result.returned == MAX_EVENTS_IN_CONTEXT
    assert result.truncated is True


def test_total_reports_the_full_match_count_even_when_capped(db_conn):
    """Truncating the list must not make the model believe the catalog is
    smaller than it is."""
    _seed(db_conn, count=40)
    result = search_events(db_conn, EventSearchSpec(min_magnitude=0.0, limit=200))
    assert result.total == 40
    assert result.total > result.returned


def test_untruncated_result_says_so(db_conn):
    _seed(db_conn, count=3)
    result = search_events(db_conn, EventSearchSpec(min_magnitude=0.0))
    assert result.truncated is False
    assert result.returned == result.total == 3


def test_search_reports_catalog_coverage(db_conn):
    """Coverage is what stops "no events found" being read as "no events
    occurred"."""
    _seed(db_conn)
    result = search_events(db_conn, EventSearchSpec(min_magnitude=4.0))
    assert result.catalog_coverage.earliest_occurred_at is not None
    assert result.catalog_coverage.completeness == "not_asserted"


# --- get_event_summary -----------------------------------------------------

def test_event_summary_returns_the_same_allowlist(db_conn):
    _seed(db_conn, count=1)
    event_id = db_conn.execute("SELECT id FROM seismic_event LIMIT 1").fetchone()[0]
    summary = get_event_summary(db_conn, event_id)
    assert isinstance(summary, EventSummary)
    assert set(summary.model_dump()) == _ALLOWED


def test_missing_event_is_a_typed_tool_failure(db_conn):
    from eqmon.ai.contracts import ToolFailure

    with pytest.raises(ToolFailure) as failure:
        get_event_summary(db_conn, 999_999)
    assert failure.value.code == "not_found"
