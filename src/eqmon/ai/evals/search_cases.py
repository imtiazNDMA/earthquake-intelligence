"""Development cases for live `search_events` capability probing."""

CASESET_VERSION = "1.0"

SEARCH_CASES = (
    {
        "id": "minimum-magnitude-date",
        "query": "Find earthquakes of magnitude 5 or above since January 1, 2025 UTC.",
        "expected": {"min_magnitude": 5.0,
                     "occurred_after": "2025-01-01T00:00:00Z"},
    },
    {
        "id": "magnitude-range-source",
        "query": "Show USGS earthquakes from magnitude 4 through 6.",
        "expected": {"min_magnitude": 4.0, "max_magnitude": 6.0,
                     "source": "USGS"},
    },
    {
        "id": "radius-mainshocks",
        "query": (
            "Find mainshocks within 100 km of longitude 66.9 east, latitude "
            "30.2 north, with magnitude at least 5."
        ),
        "expected": {"min_magnitude": 5.0, "center_lon": 66.9,
                     "center_lat": 30.2, "radius_km": 100.0,
                     "event_kind": "mainshocks"},
    },
    {
        "id": "aftershocks-window",
        "query": (
            "List aftershocks between 2026-01-01 00:00 UTC and "
            "2026-02-01 00:00 UTC."
        ),
        "expected": {"occurred_after": "2026-01-01T00:00:00Z",
                     "occurred_before": "2026-02-01T00:00:00Z",
                     "event_kind": "aftershocks"},
    },
    {
        "id": "largest-limit",
        "query": "Return the 25 largest earthquakes in the catalog.",
        "expected": {"limit": 25, "orderby": "magnitude"},
    },
    {
        "id": "oldest-manual",
        "query": "Show the oldest 10 manually entered earthquake events.",
        "expected": {"source": "MANUAL", "limit": 10,
                     "orderby": "time-asc"},
    },
    {
        "id": "place-substring",
        "query": "Search the earthquake catalog for events whose place contains Quetta.",
        "expected": {"search": "Quetta"},
    },
    {
        "id": "abstain-general-knowledge",
        "query": "What is the capital of France?",
        "expected": None,
    },
    {
        "id": "abstain-writing",
        "query": "Write a short poem about mountains.",
        "expected": None,
    },
    {
        "id": "abstain-weather",
        "query": "Will it rain in Islamabad tomorrow?",
        "expected": None,
    },
)
