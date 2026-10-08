"""Statische Prüfung bekannter wx-Fallen über das ganze Repo (ohne GUI).

1. ``Bind(wx.EVT_TEXT_ENTER, …)`` auf einem TextCtrl/ComboBox/SearchCtrl ohne
   ``wx.TE_PROCESS_ENTER`` im Konstruktor: wx bricht beim Bau des Dialogs mit
   einer C++-Assertion ab – der Dialog öffnet sich dann lautlos nicht
   (v10.4.5: user_watcher_dialog, chat_search_dialog).
2. ``wx.ListBox`` ohne Namen: VoiceOver sagt nur "Liste" ohne Zweck an.
"""
import ast
import glob
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
_WX_FILES = [os.path.join(ROOT, "src", "app_wx.py")] + glob.glob(
    os.path.join(ROOT, "src", "ui_wx", "**", "*.py"), recursive=True
) + glob.glob(os.path.join(ROOT, "src", "ui", "*.py"))

_ENTER_CTRLS = {"TextCtrl", "ComboBox", "SearchCtrl"}


def _target_key(node):
    """'self.foo' / 'foo' als Schlüssel für Zuweisungsziel bzw. Bind-Empfänger."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return None


def _wx_ctor(call):
    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        if call.func.value.id == "wx":
            return call.func.attr
    return None


def _scopes(tree):
    """Klassen getrennt betrachten (gleichnamige self-Attribute in mehreren
    Klassen einer Datei), Modulebene als eigener Bereich."""
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    rest = ast.Module(body=[n for n in tree.body if not isinstance(n, ast.ClassDef)], type_ignores=[])
    return classes + [rest]


def _scan(path):
    """Liefert je Gültigkeitsbereich (scope, ctors)."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = []
    for scope in _scopes(tree):
        ctors = {}
        for n in ast.walk(scope):
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                key = _target_key(n.targets[0])
                kind = _wx_ctor(n.value)
                if key and kind:
                    ctors.setdefault(key, []).append((kind, n.value, n.lineno))
        out.append((scope, ctors))
    return src, out


def test_no_text_enter_without_process_enter():
    problems = []
    for path in _WX_FILES:
        src, scopes = _scan(path)
        for scope, ctors in scopes:
            for n in ast.walk(scope):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "Bind" and n.args):
                    continue
                ev = n.args[0]
                if not (isinstance(ev, ast.Attribute) and ev.attr == "EVT_TEXT_ENTER"):
                    continue
                key = _target_key(n.func.value)
                for kind, call, line in ctors.get(key, []):
                    if kind in _ENTER_CTRLS and "TE_PROCESS_ENTER" not in (ast.get_source_segment(src, call) or ""):
                        problems.append(f"{os.path.relpath(path, ROOT)}:{line}: {key} ({kind}) ohne "
                                        "wx.TE_PROCESS_ENTER, aber EVT_TEXT_ENTER gebunden")
    assert not problems, "\n".join(problems)


def test_every_listbox_has_a_name():
    problems = []
    for path in _WX_FILES:
        src, scopes = _scan(path)
        for scope, ctors in scopes:
            named = set()
            for n in ast.walk(scope):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "SetName":
                    key = _target_key(n.func.value)
                    if key:
                        named.add(key)
            for key, items in ctors.items():
                for kind, call, line in items:
                    if kind != "ListBox":
                        continue
                    if any(k.arg == "name" for k in call.keywords) or key in named:
                        continue
                    problems.append(f"{os.path.relpath(path, ROOT)}:{line}: wx.ListBox '{key}' ohne SetName()")
    assert not problems, "\n".join(problems)
