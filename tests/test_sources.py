import json
from datetime import datetime, timezone
from pathlib import Path

from eqmon.events.sources import parse_usgs, RawEvent

FIXTURE = Path(__file__).parent / "fixtures" / "usgs_sample.json"


def test_parse_usgs_maps_fields_and_filters_region():
    data = json.loads(FIXTURE.read_text())
    events = parse_usgs(data)
    # only the in-region feature survives the Coverage Region filter
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, RawEvent)
    assert ev.source == "USGS"
    assert ev.source_event_id == "us1000abcd"
    assert ev.magnitude == 5.4
    assert ev.depth_km == 15.0
    assert ev.lon == 72.5 and ev.lat == 34.0
    assert ev.occurred_at == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_parse_usgs_skips_features_missing_required_fields():
    data = {"features": [{"id": "x", "properties": {"mag": None, "time": 1767225600000},
                          "geometry": {"type": "Point", "coordinates": [72.5, 34.0, 5.0]}}]}
    assert parse_usgs(data) == []
