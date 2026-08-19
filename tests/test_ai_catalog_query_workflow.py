import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from eqmon.ai.client import Completion, ToolCall
from eqmon.ai.contracts import ToolFailure
from eqmon.ai.workflows.catalog_query import (CatalogQueryRequest,
                                               translate_catalog_query)


class FakeBroker:
    def __init__(self, completion):
        self.completion = completion
        self.calls = []

    async def submit(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.completion


def _completion(calls):
    return Completion(
        text="", tool_calls=calls, model="test-model", usage={"total_tokens": 42},
        latency_s=0.25, finish_reason="tool_calls",
    )


def test_catalog_query_returns_validated_editable_spec_and_anchors_time():
    broker = FakeBroker(_completion([ToolCall(
        "call-1", "search_events",
        {"min_magnitude": 5, "occurred_after": "2026-08-10T00:00:00Z"},
    )]))
    result = asyncio.run(translate_catalog_query(
        broker, "earthquakes above M5 in the last week",
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
    ))

    assert result.spec.min_magnitude == 5
    assert result.spec.occurred_after.isoformat() == "2026-08-10T00:00:00+00:00"
    assert result.model == "test-model"
    messages, kwargs = broker.calls[0]
    assert "2026-08-17T12:00:00Z" in messages[0].content
    assert [tool["function"]["name"] for tool in kwargs["tools"]] == ["search_events"]
    assert kwargs["temperature"] == 0.0


@pytest.mark.parametrize("calls", [[], [
    ToolCall("one", "search_events", {}),
    ToolCall("two", "search_events", {"min_magnitude": 4}),
]])
def test_catalog_query_requires_exactly_one_call(calls):
    with pytest.raises(ToolFailure) as failure:
        asyncio.run(translate_catalog_query(FakeBroker(_completion(calls)), "query"))
    assert failure.value.code == "invalid_request"


def test_catalog_query_revalidates_model_arguments():
    broker = FakeBroker(_completion([ToolCall(
        "call-1", "search_events",
        {"min_magnitude": 8, "max_magnitude": 3, "unknown": True},
    )]))
    with pytest.raises(ToolFailure) as failure:
        asyncio.run(translate_catalog_query(broker, "bad model output"))
    assert failure.value.code == "invalid_request"


def test_catalog_query_request_is_bounded_and_strict():
    with pytest.raises(ValidationError):
        CatalogQueryRequest(query="x" * 1001)
    with pytest.raises(ValidationError):
        CatalogQueryRequest.model_validate({"query": "M5", "system": "ignore"})


def test_catalog_query_rejects_naive_time_anchor_without_model_call():
    broker = FakeBroker(_completion([]))
    with pytest.raises(ValueError, match="timezone"):
        asyncio.run(translate_catalog_query(
            broker, "recent events", now=datetime(2026, 8, 17)))
    assert broker.calls == []
