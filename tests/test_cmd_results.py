"""Tests für TeamTalkClient.on_cmds_result (mehrere Befehle gemeinsam abwarten)."""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from teamtalk_client.client import TeamTalkClient


def _client():
    c = TeamTalkClient.__new__(TeamTalkClient)
    c._cmd_lock = threading.Lock()
    c._cmd_callbacks = {}
    c._cmd_unclaimed = {}
    return c


def _answer(c, cmdid, ok, err=""):
    cb = c._cmd_callbacks.pop(cmdid)
    cb(ok, err)


def test_all_succeed_reports_once_at_end():
    c, got = _client(), []
    c.on_cmds_result([5, 6], lambda ok, err: got.append((ok, err)))
    _answer(c, 5, True)
    assert got == []
    _answer(c, 6, True)
    assert got == [(True, "")]


def test_first_error_reports_once():
    c, got = _client(), []
    c.on_cmds_result([5, 6], lambda ok, err: got.append((ok, err)))
    _answer(c, 5, False, "Zugriff verweigert")
    _answer(c, 6, True)
    assert got == [(False, "Zugriff verweigert")]


def test_unsent_command_counts_as_failure():
    c, got = _client(), []
    c.on_cmds_result([0], lambda ok, err: got.append((ok, err)))
    assert got == [(False, "")]


def test_result_before_registration():
    c, got = _client(), []
    c._cmd_unclaimed[7] = (True, "")
    c.on_cmds_result([7], lambda ok, err: got.append((ok, err)))
    assert got == [(True, "")]
