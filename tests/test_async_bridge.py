"""Tests für AsyncBusBridge (v4.1.0)."""
import sys
import os
import asyncio
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from event_bus import EventBus
from async_bridge import AsyncBusBridge


def _make_bridge():
    bus = EventBus()
    bridge = AsyncBusBridge(bus)
    return bus, bridge


def test_start_stop():
    bus, bridge = _make_bridge()
    bridge.start()
    assert bridge._running is True
    bridge.stop()
    assert bridge._running is False


def test_async_handler_receives_event():
    bus, bridge = _make_bridge()
    received = []

    async def handler(**kw):
        received.append(kw)

    bridge.on("test", handler)
    bridge.start()
    bus.emit("test", value=99)
    time.sleep(0.15)
    bridge.stop()
    assert received == [{"value": 99}]


def test_sync_handler_in_bridge():
    bus, bridge = _make_bridge()
    received = []

    def handler(**kw):
        received.append(kw)

    bridge.on("sync_evt", handler)
    bridge.start()
    bus.emit("sync_evt", x="hello")
    time.sleep(0.15)
    bridge.stop()
    assert received == [{"x": "hello"}]


def test_wildcard_handler():
    bus, bridge = _make_bridge()
    seen = []

    async def wc(event, **kw):
        seen.append(event)

    bridge.on_any(wc)
    bridge.start()
    bus.emit("alpha")
    bus.emit("beta")
    time.sleep(0.2)
    bridge.stop()
    assert "alpha" in seen and "beta" in seen


def test_dropped_events_counter_initial():
    bus, bridge = _make_bridge()
    assert bridge.dropped_events == 0


def test_run_coro():
    bus, bridge = _make_bridge()
    results = []

    async def task():
        results.append(42)

    bridge.start()
    fut = bridge.run_coro(task())
    if fut:
        fut.result(timeout=2)
    bridge.stop()
    assert results == [42]


def test_double_start_is_noop():
    bus, bridge = _make_bridge()
    bridge.start()
    thread_id = id(bridge._loop_thread)
    bridge.start()  # zweiter Aufruf darf nichts tun
    assert id(bridge._loop_thread) == thread_id
    bridge.stop()


def test_off_removes_handler():
    bus, bridge = _make_bridge()
    calls = []

    async def h(**kw):
        calls.append(1)

    bridge.on("ev", h)
    bridge.off("ev", h)
    bridge.start()
    bus.emit("ev")
    time.sleep(0.1)
    bridge.stop()
    assert calls == []
