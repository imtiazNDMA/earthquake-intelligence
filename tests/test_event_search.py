from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from eqmon.events.search import EventSearchSpec


def test_default_search_is_bounded_and_includes_all_event_kinds():
    spec = EventSearchSpec()
    assert spec.limit == 20
    assert spec.event_kind == "all"


def test_radius_search_requires_complete_center_and_radius():
    with pytest.raises(ValidationError, match="provided together"):
        EventSearchSpec(center_lon=66.9, center_lat=30.2)


def test_radius_search_accepts_complete_geodesic_query():
    spec = EventSearchSpec(center_lon=66.9, center_lat=30.2, radius_km=100)
    assert spec.radius_km == 100


def test_magnitude_range_must_be_ordered():
    with pytest.raises(ValidationError, match="min_magnitude"):
        EventSearchSpec(min_magnitude=6, max_magnitude=5)


def test_date_range_must_be_ordered():
    with pytest.raises(ValidationError, match="occurred_after"):
        EventSearchSpec(
            occurred_after=datetime(2026, 2, 1, tzinfo=timezone.utc),
            occurred_before=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_dates_require_timezone_offsets():
    with pytest.raises(ValidationError, match="timezone offset"):
        EventSearchSpec(occurred_after=datetime(2026, 1, 1))


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs"):
        EventSearchSpec(min_magnitdue=5)


@pytest.mark.parametrize("kind", ["all", "mainshocks", "aftershocks"])
def test_event_kind_is_explicit(kind):
    assert EventSearchSpec(event_kind=kind).event_kind == kind


def test_unbounded_result_sets_are_rejected():
    with pytest.raises(ValidationError):
        EventSearchSpec(limit=201)
