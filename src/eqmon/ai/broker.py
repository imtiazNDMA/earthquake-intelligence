"""Bounded inference broker over a single GPU.

`client.py` serialises with a `threading.Lock`, which is correct but blind: a
caller that arrives while the GPU is busy waits with no bound, no priority, and
no way to give up. That is fine for a script and wrong for a route, because the
failure it produces under load is a pile of stuck requests rather than a refusal
anyone can act on.

This module makes the wait explicit and bounded:

- a **bounded queue** — full means `BrokerFullError` (a 429), not a longer wait;
- **two deadlines** — one for how long a request may sit in the queue, another
  for how long a generation may run, because a request that has already waited
  past its usefulness should never reach the GPU at all;
- **two lanes** — interactive work overtakes batch work, so an overnight job
  cannot make an operator wait behind it;
- **cancellation** — a caller that goes away releases its queue slot.

The client is sync on purpose (see its docstring), so the worker runs it through
`asyncio.to_thread`. That bounds *waiting* precisely but not *running*: once a
generation has started, the execution deadline stops the caller waiting on it
and abandons the result — it cannot reach into LM Studio and stop the GPU. The
slot is released when the generation actually finishes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from . import config
from .client import Completion, LMStudio, Message

logger = logging.getLogger("uvicorn.error")

DEFAULT_MAX_QUEUE = 32
DEFAULT_QUEUE_DEADLINE_S = 30.0
DEFAULT_EXEC_DEADLINE_S = 120.0


class Lane(str, Enum):
    """Interactive work overtakes batch work at the queue head."""
    INTERACTIVE = "interactive"
    BATCH = "batch"


class BrokerError(RuntimeError):
    """Base for refusals that are the broker's decision, not the model's."""


class BrokerFullError(BrokerError):
    """The queue is at capacity. Callers surface this as HTTP 429."""


class QueueDeadlineError(BrokerError):
    """The request waited longer than it was worth and never ran."""


class ExecutionDeadlineError(BrokerError):
    """Generation outlived its deadline; the caller stopped waiting.

    The GPU may still be finishing the abandoned work — a sync transport cannot
    be interrupted mid-request — so the slot frees when it genuinely completes.
    """


class BrokerClosedError(BrokerError):
    """Submitted after shutdown."""


@dataclass
class BrokerStats:
    """Counters for the queue-health signals named in ai.md section 10."""
    submitted: int = 0
    completed: int = 0
    failed: int = 0
    rejected_full: int = 0
    queue_deadline_exceeded: int = 0
    execution_deadline_exceeded: int = 0
    cancelled: int = 0
    max_queue_depth: int = 0
    wait_times_s: list[float] = field(default_factory=list)
    execution_times_s: list[float] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "submitted": self.submitted,
            "completed": self.completed,
            "failed": self.failed,
            "rejected_full": self.rejected_full,
            "queue_deadline_exceeded": self.queue_deadline_exceeded,
            "execution_deadline_exceeded": self.execution_deadline_exceeded,
            "cancelled": self.cancelled,
            "max_queue_depth": self.max_queue_depth,
            "wait_s": _summary(self.wait_times_s),
            "execution_s": _summary(self.execution_times_s),
        }


@dataclass
class _Request:
    messages: Sequence[Message]
    kwargs: dict[str, Any]
    future: asyncio.Future
    lane: Lane
    queued_at: float
    queue_deadline_s: float
    exec_deadline_s: float

    def waited_s(self) -> float:
        return time.monotonic() - self.queued_at

    def expired(self) -> bool:
        return self.waited_s() > self.queue_deadline_s


class Broker:
    """Serialised, bounded access to one LM Studio server."""

    def __init__(self, client: LMStudio | None = None, *,
                 max_queue: int = DEFAULT_MAX_QUEUE,
                 queue_deadline_s: float = DEFAULT_QUEUE_DEADLINE_S,
                 exec_deadline_s: float = DEFAULT_EXEC_DEADLINE_S) -> None:
        self._client = client
        self._max_queue = max_queue
        self._queue_deadline_s = queue_deadline_s
        self._exec_deadline_s = exec_deadline_s
        # One deque per lane rather than a PriorityQueue: lane order is the only
        # priority we want, and FIFO within a lane keeps it predictable.
        self._lanes: dict[Lane, list[_Request]] = {lane: [] for lane in Lane}
        self._wakeup = asyncio.Event()
        self._worker: asyncio.Task | None = None
        self._closed = False
        self.stats = BrokerStats()

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._worker is None:
            self._closed = False
            self._worker = asyncio.create_task(self._run(), name="ai-broker")

    async def aclose(self) -> None:
        """Stop accepting work and drain the worker."""
        self._closed = True
        self._wakeup.set()
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        for queued in self._drain():
            if not queued.future.done():
                queued.future.set_exception(BrokerClosedError("broker shut down"))

    # -- submission --------------------------------------------------------

    @property
    def depth(self) -> int:
        return sum(len(queued) for queued in self._lanes.values())

    async def submit(self, messages: Sequence[Message], *,
                     lane: Lane = Lane.INTERACTIVE,
                     queue_deadline_s: float | None = None,
                     exec_deadline_s: float | None = None,
                     **kwargs: Any) -> Completion:
        """Queue one chat completion and wait for it.

        Raises `BrokerFullError` rather than queueing without bound, and
        `QueueDeadlineError` rather than running work that waited too long.
        """
        if self._closed or self._worker is None:
            raise BrokerClosedError("broker is not running")
        if self.depth >= self._max_queue:
            self.stats.rejected_full += 1
            raise BrokerFullError(
                f"inference queue full ({self._max_queue}); try again shortly")

        loop = asyncio.get_running_loop()
        request = _Request(
            messages=messages, kwargs=kwargs, future=loop.create_future(),
            lane=lane, queued_at=time.monotonic(),
            queue_deadline_s=(self._queue_deadline_s if queue_deadline_s is None
                              else queue_deadline_s),
            exec_deadline_s=(self._exec_deadline_s if exec_deadline_s is None
                             else exec_deadline_s),
        )
        self._lanes[lane].append(request)
        self.stats.submitted += 1
        self.stats.max_queue_depth = max(self.stats.max_queue_depth, self.depth)
        self._wakeup.set()

        try:
            return await request.future
        except asyncio.CancelledError:
            # The caller went away. Drop the request so its slot frees now
            # rather than after a pointless generation.
            self._discard(request)
            self.stats.cancelled += 1
            raise

    # -- worker ------------------------------------------------------------

    def _next(self) -> _Request | None:
        """Highest-priority waiting request; interactive before batch."""
        for lane in (Lane.INTERACTIVE, Lane.BATCH):
            queued = self._lanes[lane]
            while queued:
                request = queued.pop(0)
                if request.future.done():
                    continue  # cancelled while waiting
                return request
        return None

    def _drain(self) -> list[_Request]:
        drained = [request for queued in self._lanes.values() for request in queued]
        for queued in self._lanes.values():
            queued.clear()
        return drained

    def _discard(self, request: _Request) -> None:
        queued = self._lanes[request.lane]
        if request in queued:
            queued.remove(request)

    async def _run(self) -> None:
        while True:
            request = self._next()
            if request is None:
                if self._closed:
                    return
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            await self._execute(request)

    async def _execute(self, request: _Request) -> None:
        waited = request.waited_s()
        self.stats.wait_times_s.append(round(waited, 3))

        if request.expired():
            self.stats.queue_deadline_exceeded += 1
            if not request.future.done():
                request.future.set_exception(QueueDeadlineError(
                    f"waited {waited:.1f}s in the inference queue, over the "
                    f"{request.queue_deadline_s:.0f}s deadline"))
            return

        started = time.monotonic()
        try:
            completion = await asyncio.wait_for(
                asyncio.to_thread(self._chat, request),
                timeout=request.exec_deadline_s,
            )
        except asyncio.TimeoutError:
            self.stats.execution_deadline_exceeded += 1
            if not request.future.done():
                request.future.set_exception(ExecutionDeadlineError(
                    f"generation exceeded its {request.exec_deadline_s:.0f}s "
                    "execution deadline"))
            return
        except Exception as exc:  # model/transport failure belongs to the caller
            self.stats.failed += 1
            if not request.future.done():
                request.future.set_exception(exc)
            return
        finally:
            self.stats.execution_times_s.append(round(time.monotonic() - started, 3))

        self.stats.completed += 1
        if not request.future.done():
            request.future.set_result(completion)

    def _chat(self, request: _Request) -> Completion:
        client = self._client
        if client is None:  # lazy: importing the broker must not open a socket
            from .client import get_client
            client = self._client = get_client()
        return client.chat(request.messages, **request.kwargs)


def _summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {"count": len(values), "min": min(values), "max": max(values),
            "mean": round(sum(values) / len(values), 3)}
