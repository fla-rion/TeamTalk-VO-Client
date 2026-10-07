"""Einklappbare Kategorien + Suchindex an echten Qt-Bedienelementen (offscreen)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_qt_headers_state_and_search(qapp):
    from ui_qt.collapsible import CollapsibleCategories, collect_entries, ARROW_COLLAPSED
    import settings_search

    page = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(page)
    dev = QtWidgets.QGroupBox("Geräte")
    form = QtWidgets.QFormLayout(dev)
    indev = QtWidgets.QComboBox()
    form.addRow(QtWidgets.QLabel("Eingabegerät:"), indev)
    lay.addWidget(dev)
    va = QtWidgets.QGroupBox("Sprachaktivierung")
    form2 = QtWidgets.QFormLayout(va)
    delay = QtWidgets.QSpinBox()
    form2.addRow(QtWidgets.QLabel("Nachlauf (ms)"), delay)
    mute = QtWidgets.QCheckBox("&Ausgabe stummschalten")
    form2.addRow(mute)
    lay.addWidget(va)
    page.show()

    state = {}
    coll = CollapsibleCategories(page, "Audio", state, on_change=lambda: None)
    assert [c.label for c in coll.categories] == ["Geräte", "Sprachaktivierung"]
    assert coll.categories[1].collapsed and not va.isVisible()
    assert coll.categories[1].header.text() == f"{ARROW_COLLAPSED} Sprachaktivierung"
    assert coll.categories[1].header.accessibleName().startswith("Sprachaktivierung, ")
    assert lay.indexOf(coll.categories[0].header) == lay.indexOf(dev) - 1

    entries = collect_entries(page, "Audio", "Audio", coll)
    got = {(e.category, e.label) for e in entries}
    assert {("Geräte", "Eingabegerät"), ("Sprachaktivierung", "Nachlauf (ms)"),
            ("Sprachaktivierung", "Ausgabe stummschalten")} <= got
    hit = settings_search.search(entries, "nachlauf")[0]
    assert hit.target is delay and coll.category_of(delay) is coll.categories[1]

    coll.toggle(coll.categories[1])
    assert va.isVisible() and state["Audio/Sprachaktivierung"] is False
