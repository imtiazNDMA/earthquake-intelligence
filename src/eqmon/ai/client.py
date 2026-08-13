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


@dataclass(frozen=True)
class Message:
    role: str
    content: str

    @staticmethod
    def system(content: str) -> "Message":
        return Message("system", content)

    @staticmethod
    def user(content: str) -> "Message":
        return Message("user", content)

    @staticmethod
    def assistant(content: str) -> "Message":
        return Message("assistant", content)

    def as_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Completion:
    text: str
    tool_calls: list[ToolCall]
    model: str
    usage: dict
    latency_s: float

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
        return Completion(
            text=extract_text(choice),
            tool_calls=_parse_tool_calls(choice),
            model=body.get("model", payload["model"]),
            usage=body.get("usage") or {},
            latency_s=round(latency, 3),
        )

    # -- embeddings --------------------------------------------------------

    def embed(self, texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
        """Embeddings for `texts`, returned in input order.

        Used for place-name resolution against admin_boundary, which needs no
        generation at all — and therefore has no hallucination surface.
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


def _parse_tool_calls(choice: dict) -> list[ToolCall]:
    """Tool calls from one choice, with arguments decoded.

    Small models occasionally emit unparseable argument JSON. That surfaces as
    an LMStudioError so the caller can retry — retries are free locally — rather
    than as a ValueError escaping from json.loads.
    """
    raw = (choice.get("message") or {}).get("tool_calls") or []
    parsed: list[ToolCall] = []
    for call in raw:
        function = call.get("function") or {}
        name = function.get("name") or ""
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
