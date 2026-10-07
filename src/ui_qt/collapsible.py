"""Einklappbare Kategorien und Einstellungssuche für das Einstellungsfenster (Qt).

Gegenstück zu ``ui_wx/collapsible.py``: Vor jede ``QGroupBox`` eines
Einstellungs-Reiters kommt eine Kopfzeilen-Taste, die die Gruppe ein- und
ausblendet; der Zustand liegt in ``AppSettings.collapsed_settings_categories``.
``collect_entries`` liefert die Bedienelemente für ``settings_search``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from PySide6.QtWidgets import (
    QAbstractButton, QAbstractSlider, QAbstractSpinBox, QCheckBox, QComboBox,
    QFormLayout, QGroupBox, QLabel, QLineEdit, QListWidget, QPlainTextEdit,
    QPushButton, QRadioButton, QTextEdit, QToolButton, QWidget,
)
from PySide6.QtCore import Qt

from i18n import _
from settings_search import SettingEntry, clean_label

ARROW_COLLAPSED = "▸"
ARROW_EXPANDED = "▾"

_CONTROLS = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit, QAbstractSlider,
             QListWidget, QTextEdit, QPlainTextEdit)


@dataclass
class Category:
    key: str
    label: str
    header: QToolButton
    group: QGroupBox
    collapsed: bool = False


class CollapsibleCategories:
    def __init__(self, page: QWidget, section_key: str, state: Dict[str, bool],
                 on_change: Optional[Callable[[], None]] = None, default_open: int = 1) -> None:
        self.state = state
        self.on_change = on_change
        self.categories: List[Category] = []
        # Nur Gruppen, die direkt in einem Layout stehen (keine verschachtelten)
        groups = [g for g in page.findChildren(QGroupBox)
                  if g.title() and not isinstance(g.parentWidget(), QGroupBox)]
        for n, group in enumerate(groups):
            parent = group.parentWidget()
            layout = parent.layout() if parent is not None else None
            if layout is None or layout.indexOf(group) < 0 or not hasattr(layout, "insertWidget"):
                continue
            label = clean_label(group.title())
            header = QToolButton(parent)
            header.setToolButtonStyle(Qt.ToolButtonTextOnly)
            header.setAutoRaise(True)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            layout.insertWidget(layout.indexOf(group), header)
            key = f"{section_key}/{label}"
            cat = Category(key, label, header, group, bool(state.get(key, n >= default_open)))
            header.clicked.connect(lambda _c=False, c=cat: self.toggle(c))
            self.categories.append(cat)
            self._apply(cat)

    def _apply(self, cat: Category) -> None:
        cat.group.setVisible(not cat.collapsed)
        arrow = ARROW_COLLAPSED if cat.collapsed else ARROW_EXPANDED
        cat.header.setText(f"{arrow} {cat.label}")
        # Screenreader: Kategorie und Zustand statt Pfeilzeichen
        cat.header.setAccessibleName(
            f"{cat.label}, {_('eingeklappt') if cat.collapsed else _('ausgeklappt')}")

    def set_collapsed(self, cat: Category, collapsed: bool, save: bool = True) -> None:
        if cat.collapsed == collapsed:
            return
        cat.collapsed = collapsed
        self._apply(cat)
        if save:
            self.state[cat.key] = collapsed
            if self.on_change:
                self.on_change()

    def toggle(self, cat: Category) -> None:
        self.set_collapsed(cat, not cat.collapsed)

    def set_all(self, collapsed: bool) -> None:
        for cat in self.categories:
            self.set_collapsed(cat, collapsed)

    def category_of(self, widget: QWidget) -> Optional[Category]:
        for cat in self.categories:
            if cat.group.isAncestorOf(widget):
                return cat
        return None

    def is_header(self, widget: QWidget) -> bool:
        return any(widget is cat.header for cat in self.categories)


def _form_label(widget: QWidget) -> str:
    """Beschriftung aus QFormLayout bzw. QLabel-Buddy."""
    parent = widget.parentWidget()
    while parent is not None:
        layout = parent.layout()
        if isinstance(layout, QFormLayout):
            label = layout.labelForField(widget)
            if isinstance(label, QLabel):
                return clean_label(label.text())
        parent = parent.parentWidget() if not isinstance(parent, QGroupBox) else None
    return ""


def collect_entries(page: QWidget, section_key: str, section_label: str,
                    collapsible: Optional[CollapsibleCategories] = None) -> List[SettingEntry]:
    buddies = {lbl.buddy(): clean_label(lbl.text()) for lbl in page.findChildren(QLabel) if lbl.buddy()}
    entries: List[SettingEntry] = []
    for w in page.findChildren(QWidget):
        if not isinstance(w, _CONTROLS) or isinstance(w, QToolButton) and collapsible and collapsible.is_header(w):
            continue
        if isinstance(w, QLineEdit) and isinstance(w.parentWidget(), (QComboBox, QAbstractSpinBox)):
            continue  # Editierfeld innerhalb von Kombi-/Zahlenfeld
        own = clean_label(w.text()) if isinstance(w, (QCheckBox, QRadioButton, QPushButton)) else ""
        name = clean_label(w.accessibleName())
        label = own or buddies.get(w, "") or _form_label(w) or name
        if not label:
            continue
        group = None
        p = w.parentWidget()
        while p is not None and p is not page:
            if isinstance(p, QGroupBox):
                group = p
                break
            p = p.parentWidget()
        category = clean_label(group.title()) if group is not None else ""
        aliases = tuple(a for a in (name,) if a and a != label)
        entries.append(SettingEntry(section_key, section_label, category, label, aliases, target=w))
    return entries
