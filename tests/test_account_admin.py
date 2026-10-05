"""Tests für die Admin-Kontoliste: letzte Anmeldung + Server-Rückmeldung zu Befehlen."""
import os
import sys
import threading
from collections import OrderedDict
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from i18n import set_language  # noqa: E402
from ui.account_format import format_last_login, last_login_sort_key  # noqa: E402


def test_never_logged_in_is_shown_as_never():
    set_language("de")
    assert format_last_login("") == "Nie"
    assert format_last_login("1970/01/01 01:00") == "Nie"
    assert format_last_login("1969/12/31 19:00") == "Nie"


def test_last_login_is_localised():
    set_language("de")
    assert format_last_login("2026/10/05 14:23") == "05.10.2026 14:23"
    set_language("en")
    assert format_last_login("2026/10/05 14:23") == "2026-10-05 14:23"
    assert format_last_login("") == "Never"
    set_language("de")


def test_unknown_format_is_kept():
    assert format_last_login("gestern") == "gestern"


def test_sort_key_newest_first_never_last():
    raws = ["2025/01/01 10:00", "", "2026/10/05 14:23"]
    assert sorted(raws, key=last_login_sort_key) == ["2026/10/05 14:23", "2025/01/01 10:00", ""]


def _fake_client():
    """TeamTalkClient ohne SDK-Instanz – nur die Befehlsrückmeldungs-Logik."""
    from teamtalk_client.client import TeamTalkClient

    c = TeamTalkClient.__new__(TeamTalkClient)
    events = SimpleNamespace(CLIENTEVENT_CMD_SUCCESS=1, CLIENTEVENT_CMD_ERROR=2, CLIENTEVENT_NONE=0)
    c.tt = SimpleNamespace(ClientEvent=events, ttstr=lambda v: v)
    c._cmd_lock = threading.Lock()
    c._cmd_callbacks = {}
    c._cmd_unclaimed = OrderedDict()
    return c


def _msg(event, source, err=""):
    return SimpleNamespace(nClientEvent=event, nSource=source,
                           clienterrormsg=SimpleNamespace(szErrorMsg=err))


def test_success_reported_only_after_server_confirms():
    c = _fake_client()
    results = []
    c.on_cmd_result(7, lambda ok, err: results.append((ok, err)))
    assert results == []
    assert c._resolve_cmd_result(_msg(1, 7)) is False  # Erfolg: Handler läuft weiter
    assert results == [(True, "")]


def test_error_carries_server_reason_and_is_consumed():
    c = _fake_client()
    results = []
    c.on_cmd_result(8, lambda ok, err: results.append((ok, err)))
    assert c._resolve_cmd_result(_msg(2, 8, "Not authorized")) is True
    assert results == [(False, "Not authorized")]


def test_answer_before_registration_is_not_lost():
    c = _fake_client()
    assert c._resolve_cmd_result(_msg(2, 9, "Account exists")) is False
    results = []
    c.on_cmd_result(9, lambda ok, err: results.append((ok, err)))
    assert results == [(False, "Account exists")]


def test_unrelated_commands_are_ignored():
    c = _fake_client()
    results = []
    c.on_cmd_result(10, lambda ok, err: results.append((ok, err)))
    c._resolve_cmd_result(_msg(1, 11))
    c._resolve_cmd_result(_msg(5, 10))
    assert results == []
