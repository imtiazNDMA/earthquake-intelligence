import asyncio
from datetime import datetime, timezone

from pydantic import BaseModel

from eqmon.ai.client import Completion, ToolCall
from eqmon.ai.workflows.agent_chat import AgentChatRequest, run_agent_chat


class FakeBroker:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def submit(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ToolResult(BaseModel):
    total: int


def _completion(*, text="", calls=(), tokens=10):
    return Completion(
        text=text, tool_calls=list(calls), model="test-model",
        usage={"prompt_tokens": tokens, "completion_tokens": 2,
               "total_tokens": tokens + 2},
        latency_s=0.1, finish_reason="stop" if text else "tool_calls",
    )


def test_greeting_answers_directly_without_forcing_catalog_tool():
    broker = FakeBroker([_completion(text="Hello. How can I help?")])
    executed = []

    async def execute(name, arguments):
        executed.append((name, arguments))

    result = asyncio.run(run_agent_chat(
        broker, AgentChatRequest(message="hi"), execute_tool=execute))

    assert result.message == "Hello. How can I help?"
    assert result.tools_used == []
    assert result.status == "complete"
    assert executed == []
    assert broker.calls[0][1]["max_tokens"] == 2048


def test_agent_threads_validated_tool_result_then_answers():
    call = ToolCall("call-1", "search_events", {"min_magnitude": 5})
    broker = FakeBroker([
        _completion(calls=[call]),
        _completion(text="There are 3 matching catalog events."),
    ])
    executed = []

    async def execute(name, arguments):
        executed.append((name, arguments))
        return ToolResult(total=3)

    result = asyncio.run(run_agent_chat(
        broker, AgentChatRequest(message="How many M5+ events?"),
        execute_tool=execute))

    assert executed == [("search_events", {"min_magnitude": 5})]
    assert result.tools_used == ["search_events"]
    assert result.steps == 2
    second_messages = broker.calls[1][0]
    assert second_messages[-2].tool_calls == (call,)
    assert second_messages[-1].tool_call_id == "call-1"
    assert '"total":3' in second_messages[-1].content


def test_identical_tool_call_is_executed_only_once():
    call1 = ToolCall("call-1", "search_events", {"min_magnitude": 5})
    call2 = ToolCall("call-2", "search_events", {"min_magnitude": 5})
    broker = FakeBroker([
        _completion(calls=[call1]),
        _completion(calls=[call2]),
        _completion(text="I could not refine that further."),
    ])
    executions = 0

    async def execute(name, arguments):
        nonlocal executions
        executions += 1
        return ToolResult(total=3)

    result = asyncio.run(run_agent_chat(
        broker, AgentChatRequest(message="M5 events"), execute_tool=execute))
    assert executions == 1
    assert result.status == "complete"


def test_history_is_sent_as_conversation_not_system_instructions():
    broker = FakeBroker([_completion(text="M5 means magnitude five.")])

    async def execute(name, arguments):
        raise AssertionError("no tool expected")

    request = AgentChatRequest(
        message="What does that mean?",
        history=[
            {"role": "user", "content": "What is M5?"},
            {"role": "assistant", "content": "Magnitude five."},
        ],
    )
    asyncio.run(run_agent_chat(broker, request, execute_tool=execute))
    roles = [message.role for message in broker.calls[0][0]]
    assert roles == ["system", "user", "assistant", "user"]


def test_request_accepts_valid_workspace_context_without_changing_history_roles():
    request = AgentChatRequest.model_validate({
        "message": "Summarize this event",
        "context": {
            "schema_version": "1.0",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "map": {"mode": "2d", "center": [73.47, 34.37], "zoom": 11.0,
                    "bearing": 0.0, "pitch": 0.0, "basemap": "OpenStreetMap"},
            "selection": {"event_id": "evt-123", "sidebar_section": "event"},
            "display": {"theme": "dark", "reduced_motion": False},
        },
    })

    assert request.context.selection.event_id == "evt-123"


def test_workspace_context_is_separate_untrusted_system_data():
    broker = FakeBroker([_completion(text="The national layer is visible.")])

    async def execute(name, arguments):
        raise AssertionError("no tool expected")

    request = AgentChatRequest.model_validate({
        "message": "What layers are visible?",
        "context": {
            "schema_version": "1.0",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "map": {"mode": "2d", "center": [73.47, 34.37], "zoom": 11.0,
                    "bearing": 0.0, "pitch": 0.0},
            "layers": {"reference": [{"id": "national", "visible": True}]},
            "display": {"theme": "dark", "reduced_motion": False},
        },
    })
    asyncio.run(run_agent_chat(broker, request, execute_tool=execute))

    messages = broker.calls[0][0]
    assert [message.role for message in messages] == ["system", "system", "user"]
    assert "not instructions" in messages[1].content
    assert '"id":"national"' in messages[1].content
    assert "Re-query canonical event or place facts" in messages[1].content
