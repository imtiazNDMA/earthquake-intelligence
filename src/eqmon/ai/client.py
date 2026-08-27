"""LM Studio client.

Talks to LM Studio's OpenAI-compatible server over httpx — the same transport
`exposure.py` and `buildings.py` already use for outbound calls, so this adds no
dependency. The OpenAI SDK is deliberately not used: the response field this
client most depends on (`reasoning_content`) is a non-standard extension the SDK
does not model, so we would be reading raw dicts through it anyway.

Three measured behaviours of local models shape this module. All three are
silent failures — none of them raises on its own — so each is handled here once
rather than at every call site:

1. Thinking models strand their answer. `qwen3.5-9b` and `deepseek-v4-flash`
   return an EMPTY `content` with the real answer in `reasoning_content`. A
   client reading only `content` gets "" and no error. See `extract_text`.

2. Grammar-constrained JSON destroys values. `response_format={"type":
   "json_schema"}` on `gemma-4-26b-a4b` emits schema-valid output with the
   semantics gone (`{"min_magnitude": 0, "place": "},{"}`) — a JSON validator
   passes every one of those. This client offers no way to send that parameter;
   structured extraction goes through tool calling, which measured exact.

3. One GPU means one request. Concurrent generations thrash rather than
   parallelise, so calls are serialised on a lock. This is a throughput
   decision, not a correctness one.

Sync on purpose: single-flight serialisation removes any concurrency benefit
from async, and the first consumer (place resolution during ingest) is sync.
Async callers should use `asyncio.to_thread`.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import httpx

from . import config

logger = logging.getLogger("uvicorn.error")


class LMStudioError(RuntimeError):
    """Any failure reaching or parsing a response from LM Studio.

    Callers get one exception type to catch, so an AI route can degrade to a
    503 without the caller distinguishing a refused connection from a malformed
    tool-call argument.
    """


class TruncatedResponseError(LMStudioError):
    """Generation stopped at the token ceiling instead of finishing.

    The fourth silent failure: LM Studio returns 200 with a partial body and
    `finish_reason: "length"`. A truncated tool call has malformed arguments; a
    truncated sentence reads as a complete one. Neither is safe to consume, so
    the ceiling becomes a typed failure rather than a quiet quality drop.
    """


class UnofferedToolError(LMStudioError):
    """The model named a tool that was not offered in the request.

    A subclass rather than a flag because the distinction is scored, not just
    logged: this is a model false-call, whereas its siblings are infrastructure
    failures. Benchmarks that lump the two together understate model error
    exactly when the GPU is also flaky.
    """


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Message:
    """One turn in the conversation, including the two tool-threading shapes.

    A bounded agent loop replays the whole exchange on every step, so the
    assistant turn that requested tools and the results answering it both have
    to survive a round trip. The wire format is asymmetric — the assistant turn
    carries `tool_calls` with arguments re-encoded as a JSON string, while each
    result is its own `role: "tool"` turn keyed by `tool_call_id`.
    """
    role: str
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    @staticmethod
    def system(content: str) -> "Message":
        return Message("system", content)

    @staticmethod
    def user(content: str) -> "Message":
        return Message("user", content)

    @staticmethod
    def assistant(content: str) -> "Message":
        return Message("assistant", content)

    @staticmethod
    def assistant_tool_calls(calls: Iterable[ToolCall]) -> "Message":
        """The assistant turn that requested tools, replayed back to the model."""
        return Message("assistant", None, tool_calls=tuple(calls))

    @staticmethod
    def tool_result(tool_call_id: str, content: str) -> "Message":
        """One tool's result, bound to the call it answers."""
        return Message("tool", content, tool_call_id=tool_call_id)

    def as_dict(self) -> dict:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [{
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    # Re-encoded as a string: the API models arguments as JSON
                    # text on the way in as well as on the way out.
                    "arguments": json.dumps(call.arguments),
                },
            } for call in self.tool_calls]
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        return payload


@dataclass(frozen=True)
class Completion:
    text: str
    tool_calls: list[ToolCall]
    model: str
    usage: dict
    latency_s: float
    finish_reason: str = ""

    @property
    def called_tools(self) -> bool:
        return bool(self.tool_calls)


def extract_text(choice: dict) -> str:
    """The assistant's answer, wherever the model happened to put it.

    Prefers `content`; falls back to `reasoning_content` when content is empty
    or absent. Measured: `qwen3.5-9b` and `deepseek-v4-flash` return an empty
    `content` with the real answer in `reasoning_content`, so reading only
    `content` yields an empty string and no error — the failure is invisible
    without this fallback.
    """
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    if content:
        return content
    return (message.get("reasoning_content") or "").strip()


@dataclass
class _Breaker:
    """Consecutive-failure breaker.

    Deliberately simple: this exists so a down GPU fails AI routes fast instead
    of making every request wait out a full timeout. It is not a general
    resilience framework.
    """
    threshold: int = config.BREAKER_THRESHOLD
    reset_after_s: float = config.BREAKER_RESET_S
    failures: int = 0
    opened_at: float | None = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.reset_after_s:
            # Half-open: let one request through to test the waters.
            self.opened_at = None
            self.failures = 0
            return False
        return True

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.monotonic()
            logger.warning("LM Studio circuit opened after %d consecutive failures",
                           self.failures)


class LMStudio:
    """A serialised client for one LM Studio server."""

    def __init__(self, base_url: str | None = None,
                 http_client: httpx.Client | None = None) -> None:
        self._base_url = (base_url or config.LMSTUDIO_BASE_URL).rstrip("/")
        self._client = http_client or httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(config.CHAT_TIMEOUT_S, connect=5.0),
            headers={"Authorization": f"Bearer {config.LMSTUDIO_API_KEY}"},
        )
        # One GPU: serialise. Concurrent generations contend for VRAM and make
        # every caller slower rather than any caller faster.
        self._lock = threading.Lock()
        self.breaker = _Breaker()

    # -- transport ---------------------------------------------------------

    def _post(self, path: str, payload: dict, timeout: float) -> dict:
        if self.breaker.is_open():
            raise LMStudioError("LM Studio circuit open — inference disabled")
        with self._lock:
            try:
                response = self._client.post(path, json=payload, timeout=timeout)
                response.raise_for_status()
                body = response.json()
            except httpx.HTTPStatusError as exc:
                self.breaker.record_failure()
                raise LMStudioError(
                    f"LM Studio returned {exc.response.status_code}: "
                    f"{exc.response.text[:200]}") from exc
            except httpx.RequestError as exc:
                self.breaker.record_failure()
                raise LMStudioError(f"LM Studio unreachable: {exc}") from exc
            except ValueError as exc:  # non-JSON body
                self.breaker.record_failure()
                raise LMStudioError(f"LM Studio returned non-JSON: {exc}") from exc
            self.breaker.record_success()
            return body

    def close(self) -> None:
        """Close the underlying transport and its connection pool."""
        self._client.close()

    def is_available(self) -> bool:
        """False when the breaker is open. Callers use this to skip AI work
        entirely rather than to decide whether to catch an exception."""
        return not self.breaker.is_open()

    # -- chat --------------------------------------------------------------

    def chat(self, messages: Sequence[Message], *, model: str | None = None,
             tools: list[dict] | None = None, temperature: float | None = None,
             max_tokens: int | None = None, timeout: float | None = None) -> Completion:
        """One chat completion.

        There is intentionally no `response_format` parameter. Grammar-
        constrained JSON is measured to destroy semantic content on the primary
        model while still emitting schema-valid output, so the mistake is made
        unavailable rather than merely discouraged. For structured extraction,
        pass `tools` and read `Completion.tool_calls`.
        """
        payload: dict[str, Any] = {
            "model": model or config.MODEL_PRIMARY,
            "messages": [m.as_dict() for m in messages],
            "temperature": config.DEFAULT_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens or config.DEFAULT_MAX_TOKENS,
        }
        if tools:
            payload["tools"] = tools

        started = time.monotonic()
        body = self._post("/chat/completions", payload,
                          timeout or config.CHAT_TIMEOUT_S)
        latency = time.monotonic() - started

        choices = body.get("choices") or []
        if not choices:
            raise LMStudioError("LM Studio returned no choices")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise LMStudioError(f"LM Studio returned a non-object choice: {choice!r}")

        finish_reason = choice.get("finish_reason") or ""
        if finish_reason == "length":
            raise TruncatedResponseError(
                f"response truncated at the {payload['max_tokens']} token ceiling")

        return Completion(
            text=extract_text(choice),
            tool_calls=_parse_tool_calls(choice, _offered_names(tools)),
            model=body.get("model", payload["model"]),
            usage=body.get("usage") or {},
            latency_s=round(latency, 3),
            finish_reason=finish_reason,
        )

    # -- embeddings --------------------------------------------------------

    def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        """Embeddings for `texts`, returned in input order.

        Retained for controlled capability experiments. Production place
        resolution is deterministic and does not call this endpoint.
        """
        if not texts:
            return []
        body = self._post("/embeddings",
                          {"model": model or config.MODEL_EMBED, "input": list(texts)},
                          config.EMBED_TIMEOUT_S)
        data = body.get("data") or []
        if len(data) != len(texts):
            raise LMStudioError(
                f"embeddings returned {len(data)} vectors for {len(texts)} inputs")
        # Sort by the documented `index` rather than trusting arrival order.
        ordered = sorted(data, key=lambda d: d.get("index", 0))
        return [list(d["embedding"]) for d in ordered]


def _offered_names(tools: list[dict] | None) -> frozenset[str]:
    """Names of the tools actually sent in the request."""
    return frozenset(
        name for tool in (tools or [])
        if (name := ((tool.get("function") or {}).get("name")))
    )


def _parse_tool_calls(choice: dict, offered: frozenset[str]) -> list[ToolCall]:
    """Tool calls from one choice, with arguments decoded and names checked.

    Small models occasionally emit unparseable argument JSON. That surfaces as
    an LMStudioError so the caller can retry — retries are free locally — rather
    than as a ValueError escaping from json.loads.

    A name that was never offered is rejected here too. Offering a tool is what
    authorizes it, so a hallucinated name is a malformed response rather than a
    dispatch decision to make further downstream.
    """
    raw = (choice.get("message") or {}).get("tool_calls") or []
    parsed: list[ToolCall] = []
    for call in raw:
        function = call.get("function") or {}
        name = function.get("name") or ""
        if name not in offered:
            raise UnofferedToolError(
                f"tool call {name!r} was not offered; offered: {sorted(offered)}")
        arguments = function.get("arguments") or "{}"
        try:
            decoded = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError as exc:
            raise LMStudioError(
                f"tool call {name!r} had unparseable arguments: {arguments[:200]!r}") from exc
        if not isinstance(decoded, dict):
            raise LMStudioError(
                f"tool call {name!r} arguments were not an object: {decoded!r}")
        parsed.append(ToolCall(id=call.get("id", ""), name=name, arguments=decoded))
    return parsed


_default: LMStudio | None = None


def get_client() -> LMStudio:
    """Process-wide client. Lazily built so importing the package never opens a
    socket — the test suite and any non-AI code path stay unaffected."""
    global _default
    if _default is None:
        _default = LMStudio()
    return _default


def close() -> None:
    """Release the process-wide client at application shutdown.

    Clears the global as well as closing the transport, so a later `get_client`
    builds a fresh one rather than handing back a client whose pool is shut.
    """
    global _default
    if _default is not None:
        _default.close()
        _default = None
