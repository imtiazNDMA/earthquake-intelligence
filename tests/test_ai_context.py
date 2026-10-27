from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eqmon.ai.context import AnalystContextV1, context_fingerprint


def _context(**overrides):
    payload = {
        "schema_version": "1.0",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "map": {
            "mode": "2d", "center": [73.47, 34.37], "zoom": 11.0,
            "bearing": 0.0, "pitch": 0.0, "basemap": "OpenStreetMap",
        },
        "selection": {"event_id": "evt-123", "mmi_level": 7,
                      "sidebar_section": "event"},
        "layers": {
            "reference": [{"id": "national", "visible": True, "opacity": 1}],
            "landslides": [{"id": "GB", "visible": True, "opacity": 0.62}],
            "pga": {"visible": False, "return_period": 475, "opacity": 0.55},
            "buildings": {"visible": True, "selected_district": None,
                          "opacity": 0.68},
            "mmi": {"visible": True, "opacity": 0.45},
        },
        "event_filters": {"sources": ["USGS"], "minimum_magnitude": 4,
                          "time_window_indices": [0, 24]},
        "display": {"theme": "dark", "reduced_motion": False},
    }
    payload.update(overrides)
    return payload


def test_analyst_context_accepts_bounded_renderer_neutral_snapshot():
    context = AnalystContextV1.model_validate(_context())

    assert context.map.center == (73.47, 34.37)
    assert context.selection.event_id == "evt-123"
    assert context.layers.reference[0].id == "national"


@pytest.mark.parametrize("field,value", [
    ("map", {"mode": "2d", "center": [200, 34], "zoom": 11,
             "bearing": 0, "pitch": 0}),
    ("captured_at", (datetime.now(timezone.utc) - timedelta(seconds=31)).isoformat()),
])
def test_analyst_context_rejects_invalid_coordinates_and_stale_snapshots(field, value):
    with pytest.raises(ValidationError):
        AnalystContextV1.model_validate(_context(**{field: value}))


def test_analyst_context_rejects_unknown_fields_and_nonfinite_numbers():
    payload = _context()
    payload["renderer"] = {"private": "handle"}
    with pytest.raises(ValidationError):
        AnalystContextV1.model_validate(payload)

    payload = _context()
    payload["map"]["zoom"] = True
    with pytest.raises(ValidationError):
        AnalystContextV1.model_validate(payload)

    payload = _context()
    payload["map"]["zoom"] = float("nan")
    with pytest.raises(ValidationError):
        AnalystContextV1.model_validate(payload)


def test_context_fingerprint_does_not_retain_event_or_layer_values():
    fingerprint = context_fingerprint(AnalystContextV1.model_validate(_context()))

    assert fingerprint["context_present"] is True
    assert len(fingerprint["context_sha256"]) == 64
    assert fingerprint["context_bytes"] > 0
    assert "evt-123" not in str(fingerprint)
    assert "national" not in str(fingerprint)


def test_analyst_context_rejects_future_timestamp_and_oversized_layer_group():
    with pytest.raises(ValidationError):
        AnalystContextV1.model_validate(_context(
            captured_at=(datetime.now(timezone.utc) + timedelta(seconds=6)).isoformat()))

    payload = _context()
    payload["layers"]["reference"] = [
        {"id": f"layer-{index}", "visible": True} for index in range(65)
    ]
    with pytest.raises(ValidationError):
        AnalystContextV1.model_validate(payload)
