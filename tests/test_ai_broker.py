"""Inference broker behaviour, driven by a fake client.

The broker exists because one GPU serves the whole platform: work has to queue,
and a queue without bounds, deadlines, and cancellation is just a slower way to
fall over. None of that is observable by hand — an unbounded queue looks fine
until it is full — so every guarantee is pinned here.

Tests drive the coroutines with `asyncio.run` rather than a plugin; the suite
has no other async tests and this needs no event-loop fixtures.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from eqmon.ai.broker import (Broker, BrokerFullError, ExecutionDeadlineError,
                             Lane, QueueDeadlineError)
from eqmon.ai.client import Completion, LMStudioError, Message


def _completion(text: str = "ok") -> Completion:
    return Completion(text=text, tool_calls=[], model="fake", usage={},
                      latency_s=0.0, finish_reason="stop")


class _FakeClient:
    """Stands in for LMStudio. Sync, like the real one."""

    def __init__(self, *, delay_s: float = 0.0, error: Exception | None = None,
                 result: Completion | None = None) -> None:
        self.delay_s = delay_s
        self.error = error
        self.result = result or _completion()
        self.calls: list[dict] = []
        self.started = 0

    def chat(self, messages, **kwargs) -> Completion:
        self.started += 1
        self.calls.append({"messages": list(messages), **kwargs})
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return self.result


async def _broker(client, **kwargs) -> Broker:
    broker = Broker(client, **kwargs)
    await broker.start()
    return broker


# --- the happy path --------------------------------------------------------

def test_submit_returns_the_completion_from_the_client():
    async def scenario():
        client = _FakeClient(result=_completion("3 events"))
        broker = await _broker(client)
        try:
            return await broker.submit([Message.user("q")]), client
        finally:
            await broker.aclose()

    result, client = asyncio.run(scenario())
    assert result.text == "3 events"
    assert client.started == 1


def test_submit_passes_tools_and_model_through():
    async def scenario():
        client = _FakeClient()
        broker = await _broker(client)
        try:
            await broker.submit([Message.user("q")], tools=[{"a": 1}],
                                model="m", max_tokens=64)
        finally:
            await broker.aclose()
        return client

    client = asyncio.run(scenario())
    assert client.calls[0]["tools"] == [{"a": 1}]
    assert client.calls[0]["model"] == "m"
    assert client.calls[0]["max_tokens"] == 64


def test_client_errors_propagate_to_the_caller():
    async def scenario():
        client = _FakeClient(error=LMStudioError("gpu on fire"))
        broker = await _broker(client)
        try:
            with pytest.raises(LMStudioError, match="gpu on fire"):
                await broker.submit([Message.user("q")])
        finally:
            await broker.aclose()

    asyncio.run(scenario())


# --- serialisation: one GPU, one generation --------------------------------

def test_requests_execute_one_at_a_time():
    """Concurrent generations thrash VRAM rather than parallelising, so the
    broker must serialise even when callers arrive together."""
    async def scenario():
        client = _FakeClient(delay_s=0.05)
        overlap = {"max": 0, "current": 0}
        original = client.chat

        def counting_chat(messages, **kwargs):
            overlap["current"] += 1
            overlap["max"] = max(overlap["max"], overlap["current"])
            try:
                return original(messages, **kwargs)
            finally:
                overlap["current"] -= 1

        client.chat = counting_chat
        broker = await _broker(client)
        try:
            await asyncio.gather(*(broker.submit([Message.user(str(i))])
                                   for i in range(4)))
        finally:
            await broker.aclose()
        return overlap["max"], client.started

    peak, started = asyncio.run(scenario())
    assert peak == 1
    assert started == 4


# --- the bound: full means refused, not slower -----------------------------

def test_queue_full_is_refused_rather_than_queued():
    """An unbounded queue turns overload into a pile of stuck requests. The
    caller needs a refusal it can turn into a 429."""
    async def scenario():
        client = _FakeClient(delay_s=0.3)
        broker = await _broker(client, max_queue=2)
        try:
            busy = asyncio.create_task(broker.submit([Message.user("a")]))
            await asyncio.sleep(0.05)          # worker has picked `busy` up
            queued = [asyncio.create_task(broker.submit([Message.user(n)]))
                      for n in ("b", "c")]
            await asyncio.sleep(0.01)          # both are waiting: depth == 2

            with pytest.raises(BrokerFullError, match="queue full"):
                await broker.submit([Message.user("d")])

            rejected = broker.stats.rejected_full
            await asyncio.gather(busy, *queued)
            return rejected
        finally:
            await broker.aclose()

    assert asyncio.run(scenario()) == 1


# --- two deadlines ---------------------------------------------------------

def test_request_that_waited_past_its_queue_deadline_never_runs():
    """Work whose answer arrived too late to matter must not reach the GPU —
    running it would delay the request behind it for nothing."""
    async def scenario():
        client = _FakeClient(delay_s=0.25)
        broker = await _broker(client, queue_deadline_s=0.05)
        try:
            busy = asyncio.create_task(broker.submit([Message.user("a")]))
            await asyncio.sleep(0.02)

            with pytest.raises(QueueDeadlineError, match="deadline"):
                await broker.submit([Message.user("late")])

            await busy
            return client.started, broker.stats.queue_deadline_exceeded
        finally:
            await broker.aclose()

    started, expired = asyncio.run(scenario())
    assert started == 1          # the late request never reached the client
    assert expired == 1


def test_generation_past_its_execution_deadline_stops_the_caller_waiting():
    async def scenario():
        client = _FakeClient(delay_s=0.3)
        broker = await _broker(client, exec_deadline_s=0.05)
        try:
            with pytest.raises(ExecutionDeadlineError, match="execution deadline"):
                await broker.submit([Message.user("q")])
            return broker.stats.execution_deadline_exceeded
        finally:
            await broker.aclose()

    assert asyncio.run(scenario()) == 1


# --- lanes: an overnight job must not block an operator --------------------

def test_interactive_work_overtakes_queued_batch_work():
    async def scenario():
        client = _FakeClient(delay_s=0.05)
        broker = await _broker(client)
        try:
            busy = asyncio.create_task(broker.submit([Message.user("busy")]))
            await asyncio.sleep(0.01)          # worker occupied

            batch = asyncio.create_task(
                broker.submit([Message.user("batch")], lane=Lane.BATCH))
            await asyncio.sleep(0.01)          # batch queued first
            interactive = asyncio.create_task(
                broker.submit([Message.user("interactive")], lane=Lane.INTERACTIVE))

            await asyncio.gather(busy, batch, interactive)
            return [call["messages"][0].content for call in client.calls]
        finally:
            await broker.aclose()

    assert asyncio.run(scenario()) == ["busy", "interactive", "batch"]


# --- cancellation ----------------------------------------------------------

def test_cancelled_caller_releases_its_queue_slot():
    """A disconnected client should free capacity immediately, not after a
    generation nobody is waiting for."""
    async def scenario():
        client = _FakeClient(delay_s=0.2)
        broker = await _broker(client)
        try:
            busy = asyncio.create_task(broker.submit([Message.user("busy")]))
            await asyncio.sleep(0.02)

            abandoned = asyncio.create_task(broker.submit([Message.user("gone")]))
            await asyncio.sleep(0.01)
            assert broker.depth == 1

            abandoned.cancel()
            with pytest.raises(asyncio.CancelledError):
                await abandoned
            depth_after = broker.depth

            await busy
            await asyncio.sleep(0.05)
            return depth_after, client.started, broker.stats.cancelled
        finally:
            await broker.aclose()

    depth_after, started, cancelled = asyncio.run(scenario())
    assert depth_after == 0
    assert started == 1          # the abandoned request never ran
    assert cancelled == 1


# --- telemetry -------------------------------------------------------------

def test_stats_report_the_queue_health_signals():
    async def scenario():
        client = _FakeClient()
        broker = await _broker(client)
        try:
            await broker.submit([Message.user("q")])
            return broker.stats.as_dict()
        finally:
            await broker.aclose()

    stats = asyncio.run(scenario())
    assert stats["submitted"] == 1
    assert stats["completed"] == 1
    assert stats["max_queue_depth"] >= 1
    assert stats["wait_s"]["count"] == 1
    assert stats["execution_s"]["count"] == 1
