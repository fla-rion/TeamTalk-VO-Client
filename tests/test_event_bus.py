"""Tests für EventBus (v4.1.0)."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from event_bus import EventBus


def test_on_emit_basic():
    bus = EventBus()
    received = []
    bus.on("test_event", lambda **kw: received.append(kw))
    bus.emit("test_event", value=42)
    assert received == [{"value": 42}]


def test_on_off():
    bus = EventBus()
    received = []
    def handler(**kw):
        received.append(kw)
    bus.on("evt", handler)
    bus.off("evt", handler)
    bus.emit("evt", x=1)
    assert received == []


def test_no_duplicate_registration():
    bus = EventBus()
    calls = []
    def h(**kw):
        calls.append(1)
    bus.on("e", h)
    bus.on("e", h)  # doppelt
    bus.emit("e")
    assert len(calls) == 1


def test_on_any_wildcard():
    bus = EventBus()
    seen = []
    bus.on_any(lambda event, **kw: seen.append(event))
    bus.emit("foo")
    bus.emit("bar")
    assert seen == ["foo", "bar"]


def test_off_any():
    bus = EventBus()
    seen = []
    def wc(event, **kw):
        seen.append(event)
    bus.on_any(wc)
    bus.off_any(wc)
    bus.emit("x")
    assert seen == []


def test_handler_exception_does_not_block_others():
    bus = EventBus()
    results = []
    def bad(**kw):
        raise RuntimeError("boom")
    def good(**kw):
        results.append(True)
    bus.on("e", bad)
    bus.on("e", good)
    bus.emit("e")
    assert results == [True]


def test_clear_all():
    bus = EventBus()
    calls = []
    bus.on("x", lambda **kw: calls.append(1))
    bus.on_any(lambda e, **kw: calls.append(2))
    bus.clear()
    bus.emit("x")
    assert calls == []


def test_clear_specific_event():
    bus = EventBus()
    calls = []
    bus.on("a", lambda **kw: calls.append("a"))
    bus.on("b", lambda **kw: calls.append("b"))
    bus.clear("a")
    bus.emit("a")
    bus.emit("b")
    assert calls == ["b"]


def test_emit_unknown_event():
    bus = EventBus()
    # Kein Fehler bei unbekanntem Event
    bus.emit("unknown_event", foo="bar")


def test_off_nonexistent_handler():
    bus = EventBus()
    # Kein Fehler beim Entfernen eines nicht registrierten Handlers
    bus.off("x", lambda **kw: None)
