"""Command Palette / Aktionssuche (Qt) – Roadmap Punkt 1.

Sammelt alle Aktionen aus der Menüleiste des Hauptfensters und bietet sie
über ein durchsuchbares Overlay an. Führt Aktionen über `QAction.trigger()`
aus – kein separates Handler-Mapping nötig, da jede Menüaktion bereits mit
ihrem Slot verbunden ist.
"""
from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut

from i18n import _

if TYPE_CHECKING:
    from app_qt import MainWindow


def _clean_label(text: str) -> str:
    """Entfernt Qt-Mnemonik (&) für die Anzeige, behält escaped '&&'."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "&" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "&":
                out.append("&")
                i += 2
                continue
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def collect_actions(window: "MainWindow") -> List[Tuple[str, QAction]]:
    """Sammelt alle ausführbaren Aktionen (keine Separatoren/Untermenüs) aus der Menüleiste."""
    results: List[Tuple[str, QAction]] = []
    mb = window.menuBar()
    if mb is None:
        return results

    def walk(actions) -> None:
        for action in actions:
            if action.isSeparator():
                continue
            sub = action.menu()
            if sub is not None:
                walk(sub.actions())
                continue
            label = _clean_label(action.text()).strip()
            if not label:
                continue
            results.append((label, action))

    walk(mb.actions())
    return results


class CommandPaletteDialog(QDialog):
    """Overlay-Dialog: Tippen filtert Aktionen, Enter führt aus, Escape bricht ab."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window, Qt.WindowType.Dialog)
        self.setWindowTitle(_("Aktionssuche"))
        self._window = window
        self._all_actions = collect_actions(window)
        self._filtered: List[Tuple[str, QAction]] = list(self._all_actions)

        root = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setAccessibleName(_("Aktion suchen"))
        self._search.setPlaceholderText(_("Aktion suchen …"))
        root.addWidget(self._search)

        self._list = QListWidget()
        self._list.setAccessibleName(_("Gefundene Aktionen"))
        self._list.setMinimumSize(420, 320)
        root.addWidget(self._list)

        self._search.textChanged.connect(self._on_search)
        self._search.returnPressed.connect(self._on_activate)
        self._list.itemActivated.connect(lambda _item: self._on_activate())

        esc = QShortcut(QKeySequence("Escape"), self)
        esc.activated.connect(self.reject)

        self._populate(self._all_actions)
        self._search.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt-Namenskonvention)
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up) and self._search.hasFocus():
            row = self._list.currentRow()
            if event.key() == Qt.Key.Key_Down:
                row = min(row + 1, self._list.count() - 1)
            else:
                row = max(row - 1, 0)
            self._list.setCurrentRow(row)
            event.accept()
            return
        super().keyPressEvent(event)

    def _populate(self, items: List[Tuple[str, QAction]]) -> None:
        self._list.clear()
        for label, _action in items:
            self._list.addItem(QListWidgetItem(label))
        if items:
            self._list.setCurrentRow(0)

    def _on_search(self, text: str) -> None:
        query = text.strip().lower()
        if not query:
            self._filtered = list(self._all_actions)
        else:
            self._filtered = [
                (label, action) for label, action in self._all_actions
                if query in label.lower()
            ]
        self._populate(self._filtered)

    def _on_activate(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._filtered):
            return
        _label, action = self._filtered[row]
        self.accept()
        if action.isEnabled():
            action.trigger()
