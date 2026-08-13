"""LM Studio client behaviour, driven entirely by mocked transports.

These tests never contact a live LM Studio: the point is that the client's
handling of *measured* local-model quirks is pinned in CI, on a machine with no
GPU. The quirks are real and were observed on this project's own models —
see ai_implementation.md section 2.
"""
from __future__ import annotations

import httpx
import pytest

from eqmon.ai import client as ai
from eqmon.ai.client import LMStudioError, Message, extract_text


def _completion(content=None, reasoning=None, tool_calls=None) -> dict:
    """A /v1/chat/completions body shaped like LM Studio's."""
    message: dict = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "model": "test-model"}


def _client(handler) -> ai.LMStudio:
    """An LMStudio bound to a mock transport, with the breaker reset."""
    transport = httpx.MockTransport(handler)
    return ai.LMStudio(http_client=httpx.Client(transport=transport,
                                                base_url="http://test/v1"))


# --- extract_text: the silent-failure guard -------------------------------
# qwen3.5-9b and deepseek-v4-flash return an EMPTY content with the real answer
# in `reasoning_content`. A client reading only `content` gets "" and no error.

def test_extract_text_prefers_content():
    assert extract_text(_completion(content="hello")["choices"][0]) == "hello"


def test_extract_text_falls_back_to_reasoning_content():
    choice = _completion(content="", reasoning="the real answer")["choices"][0]
    assert extract_text(choice) == "the real answer"


def test_extract_text_falls_back_when_content_absent_entirely():
    choice = _completion(reasoning="the real answer")["choices"][0]
    assert extract_text(choice) == "the real answer"


def test_extract_text_prefers_content_when_both_present():
    choice = _completion(content="real", reasoning="scratch")["choices"][0]
    assert extract_text(choice) == "real"


def test_extract_text_empty_when_neither_present():
    assert extract_text(_completion(content="  ")["choices"][0]) == ""


# --- chat ------------------------------------------------------------------

def test_chat_returns_text():
    def handler(request):
        return httpx.Response(200, json=_completion(content="Paris"))
    assert _client(handler).chat([Message.user("capital of France?")]).text == "Paris"


def test_chat_sends_model_and_messages():
    seen = {}

    def handler(request):
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_completion(content="ok"))

    _client(handler).chat([Message.system("sys"), Message.user("hi")], model="m1")
    assert seen["model"] == "m1"
    assert seen["messages"] == [{"role": "system", "content": "sys"},
                                {"role": "user", "content": "hi"}]
    # Deterministic by default: sampling is opt-in, not opt-out.
    assert seen["temperature"] == 0


def test_chat_never_sends_response_format():
    """Grammar-constrained JSON is measured broken on gemma-4-26b-a4b: it emits
    schema-valid output with destroyed values (place: "},{"). The client must
    make that mistake unavailable rather than merely discouraged."""
    seen = {}

    def handler(request):
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_completion(content="ok"))

    _client(handler).chat([Message.user("hi")])
    assert "response_format" not in seen


# --- tool calling: the structured-output mechanism -------------------------

def test_chat_parses_tool_calls():
    calls = [{"id": "c1", "type": "function",
              "function": {"name": "search_events",
                           "arguments": '{"min_magnitude": 5, "place": "Quetta"}'}}]

    def handler(request):
        return httpx.Response(200, json=_completion(content="", tool_calls=calls))

    result = _client(handler).chat([Message.user("q")], tools=[{"type": "function"}])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "search_events"
    assert result.tool_calls[0].arguments == {"min_magnitude": 5, "place": "Quetta"}


def test_chat_reports_no_tool_calls_when_model_abstains():
    """Correct abstention is a measured strength of both models; the client must
    represent it as an empty list, never as an error."""
    def handler(request):
        return httpx.Response(200, json=_completion(content="The capital is Paris."))

    result = _client(handler).chat([Message.user("q")], tools=[{"type": "function"}])
    assert result.tool_calls == []
    assert result.text == "The capital is Paris."


def test_malformed_tool_arguments_raise_lmstudio_error():
    """Small models occasionally emit unparseable argument JSON. That must be a
    typed failure the caller can retry, not a ValueError from deep inside."""
    calls = [{"id": "c1", "type": "function",
              "function": {"name": "f", "arguments": "{not json"}}]

    def handler(request):
        return httpx.Response(200, json=_completion(tool_calls=calls))

    with pytest.raises(LMStudioError, match="arguments"):
        _client(handler).chat([Message.user("q")], tools=[{"type": "function"}])


# --- failure modes ---------------------------------------------------------

def test_unreachable_server_raises_lmstudio_error():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    with pytest.raises(LMStudioError, match="unreachable"):
        _client(handler).chat([Message.user("q")])


def test_http_error_raises_lmstudio_error():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(LMStudioError):
        _client(handler).chat([Message.user("q")])


def test_empty_choices_raises_lmstudio_error():
    def handler(request):
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(LMStudioError, match="no choices"):
        _client(handler).chat([Message.user("q")])


# --- circuit breaker: keep the platform up when the GPU is not -------------

def test_breaker_opens_after_consecutive_failures():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("down")

    c = _client(handler)
    c.breaker.threshold = 3
    for _ in range(3):
        with pytest.raises(LMStudioError):
            c.chat([Message.user("q")])
    assert calls["n"] == 3

    # Fourth call must fail fast without touching the network.
    with pytest.raises(LMStudioError, match="circuit open"):
        c.chat([Message.user("q")])
    assert calls["n"] == 3


def test_breaker_resets_after_success():
    state = {"fail": True, "n": 0}

    def handler(request):
        state["n"] += 1
        if state["fail"]:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=_completion(content="ok"))

    c = _client(handler)
    c.breaker.threshold = 3
    for _ in range(2):
        with pytest.raises(LMStudioError):
            c.chat([Message.user("q")])
    state["fail"] = False
    assert c.chat([Message.user("q")]).text == "ok"
    assert c.breaker.failures == 0


def test_is_available_reports_breaker_state():
    def handler(request):
        raise httpx.ConnectError("down")

    c = _client(handler)
    c.breaker.threshold = 1
    assert c.is_available() is True
    with pytest.raises(LMStudioError):
        c.chat([Message.user("q")])
    assert c.is_available() is False


# --- embeddings ------------------------------------------------------------

def test_embed_returns_vectors_in_input_order():
    def handler(request):
        import json
        n = len(json.loads(request.content)["input"])
        return httpx.Response(200, json={
            "data": [{"index": i, "embedding": [float(i), 0.5]} for i in range(n)]})

    assert _client(handler).embed(["a", "b"]) == [[0.0, 0.5], [1.0, 0.5]]


def test_embed_reorders_by_index():
    """The API is documented to return `index`; do not trust arrival order."""
    def handler(request):
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [1.0]}, {"index": 0, "embedding": [0.0]}]})

    assert _client(handler).embed(["a", "b"]) == [[0.0], [1.0]]


def test_embed_empty_input_makes_no_request():
    def handler(request):
        raise AssertionError("should not have been called")

    assert _client(handler).embed([]) == []
