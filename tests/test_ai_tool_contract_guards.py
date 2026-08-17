"""Cross-tool safety guards that do not require a database."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from eqmon.ai import contracts
from eqmon.ai.contracts import ToolFailure
from eqmon.ai.tools import analysis as analysis_tools
from eqmon.ai.tools import events as event_tools


def test_single_event_summary_enforces_projection_byte_ceiling(monkeypatch):
    monkeypatch.setattr(event_tools, "get_event", lambda conn, event_id: {
        "id": event_id,
        "magnitude": 6.2,
        "mag_type": "Mw",
        "depth_km": 12.0,
        "lat": 34.0,
        "lon": 72.0,
        "place": "x" * contracts.MAX_PROJECTION_BYTES,
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "source": "USGS",
        "is_mainshock": True,
    })

    with pytest.raises(ToolFailure) as failure:
        event_tools.get_event_summary(None, 7)

    assert failure.value.code == "partial"
    assert failure.value.detail["bytes"] > contracts.MAX_PROJECTION_BYTES


def test_aftershock_summary_preserves_catalog_source(monkeypatch):
    monkeypatch.setattr(analysis_tools, "compute_forecast", lambda *args, **kwargs: {
        "main_mag": 6.2,
        "region": "central",
        "event": {
            "id": 7,
            "magnitude": 6.2,
            "lat": 34.0,
            "lon": 72.0,
            "place": "Quetta area",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "source": "PMD",
        },
        "probabilities": [],
    })

    result = analysis_tools.get_aftershock_summary(None, event_id=7)

    assert result.event is not None
    assert result.event.source == "PMD"
