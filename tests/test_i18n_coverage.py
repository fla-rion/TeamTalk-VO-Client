"""Jedes _("...")-Literal der Oberfläche (wx + Qt) hat eine EN/FR/ES-Übersetzung.

Fehlte bisher als Prüfung: bis v11.1 waren 373 Menü-/Dialogtexte (v. a. Qt)
in allen drei Sprachen unübersetzt, ohne dass es auffiel.
"""
import ast
import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

import i18n  # noqa: E402

_FILES = (
    [os.path.join(ROOT, "src", "app_qt.py"), os.path.join(ROOT, "src", "app_wx.py")]
    + glob.glob(os.path.join(ROOT, "src", "ui_qt", "**", "*.py"), recursive=True)
    + glob.glob(os.path.join(ROOT, "src", "ui_wx", "**", "*.py"), recursive=True)
)


def _literals():
    found = {}
    for f in _FILES:
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                found.setdefault(n.args[0].value, f"{os.path.relpath(f, ROOT)}:{n.lineno}")
    return found


def _translated(table, text):
    if text in table:
        return True
    stripped, _m, _e = i18n._strip_qt_decorations(text)
    return stripped in table


def test_every_ui_literal_is_translated():
    tables = {"en": i18n._TRANSLATIONS, "fr": i18n._TRANSLATIONS_FR, "es": i18n._TRANSLATIONS_ES}
    missing = []
    for text, where in sorted(_literals().items()):
        if not re.search(r"[A-Za-zÄÖÜäöüß]", text):
            continue
        langs = [lang for lang, table in tables.items() if not _translated(table, text)]
        if langs:
            missing.append(f"{where}: {text!r} fehlt in {', '.join(langs)}")
    assert not missing, "Unübersetzte Oberflächentexte:\n" + "\n".join(missing[:50])
