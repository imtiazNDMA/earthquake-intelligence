import math
import os
from datetime import datetime, timezone

import pytest

from eqmon.events.ingest import ingest
from eqmon.events.repo import get_event_stats
from eqmon.events.sources import RawEvent

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL_TEST"), reason="DATABASE_URL_TEST not set"
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _FakeSource:
    name = "USGS"

    def __init__(self, events):
        self._events = events

    def fetch(self, since=None, updatedafter=None):
        return list(self._events)


def test_event_stats_survives_out_of_range_magnitude(db_conn):
    # Regression: PMD occasionally emits a mag/depth swap (e.g. magnitude="317"),
    # and such a row could linger in the DB. The daily moment proxy 10^(1.5*M)
    # overflows double precision for M317, which used to 500 the whole dashboard.
    # get_event_stats must clamp the exponent and return finite numbers instead.
    ingest(db_conn, _FakeSource([
        RawEvent("USGS", "ok", T0, 5.5, 10, 72.5, 34.0),
        RawEvent("USGS", "bad", T0, 317.0, 4.4, 73.0, 35.0),
    ]))

    stats = get_event_stats(db_conn)  # must not raise NumericValueOutOfRange

    assert stats["total_events"] == 2
    for day in stats["daily_cumulative"]:
        assert math.isfinite(day["moment_proxy"])
        assert math.isfinite(day["cum_moment"])
