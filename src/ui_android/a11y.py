"""Android-Accessibility-Patches für TalkBack und andere Screen Reader.

Analog zu src/ui/a11y.py (macOS/PyObjC), aber für Android via Rubicon-Java.
Toga auf Android wickelt native Android-Views ein. TalkBack liest diese nativ.
Dieses Modul setzt Content Descriptions, Live Regions und Delegates korrekt.
"""
from __future__ import annotations

from typing import List, Optional

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

try:
    from rubicon.java import JavaClass
    ViewCompat = JavaClass("androidx/core/view/ViewCompat")
    _RUBICON_AVAILABLE = True
except Exception:
    # Rubicon nicht verfügbar (z.B. beim Testen auf Desktop)
    ViewCompat = None
    _RUBICON_AVAILABLE = False

# androidx.view.View Accessibility-Live-Region-Konstanten
LIVE_NONE = 0
LIVE_POLITE = 1
LIVE_ASSERTIVE = 2


def set_description(widget, text: str) -> None:
    """Setzt die TalkBack-Beschreibung eines Toga-Widgets."""
    try:
        widget._impl.native.setContentDescription(text)
    except Exception:
        pass


def set_live_region(widget, mode: int = LIVE_POLITE) -> None:
    """Markiert ein Widget als Live Region (TalkBack liest Änderungen vor)."""
    if not _RUBICON_AVAILABLE:
        return
    try:
        ViewCompat.setAccessibilityLiveRegion(widget._impl.native, mode)
    except Exception:
        pass


def announce(app, text: str) -> None:
    """Sofortige TalkBack-Ansage ohne Fokusänderung."""
    try:
        app.main_window._impl.native.announceForAccessibility(text)
    except Exception:
        pass


def announce_event(app, text: str) -> None:
    """TalkBack-Ansage für TeamTalk-Events (z.B. 'Nutzer X hat den Kanal betreten').

    Alias für announce() mit semantisch klarerem Namen für Event-Handler.
    """
    announce(app, text)


def make_button_accessible(btn: toga.Button, label: str, hint: Optional[str] = None) -> None:
    """Setzt Content Description und optionalen Hint-Text auf einem Button.

    TalkBack liest: "<label>, Schaltfläche" und bei langer Berührung den hint.
    """
    try:
        native = btn._impl.native
        native.setContentDescription(label)
        if hint is not None:
            # TooltipCompat setzt den Hint-Text für lange Berührungen
            if _RUBICON_AVAILABLE:
                try:
                    TooltipCompat = JavaClass("androidx/core/view/TooltipCompat")
                    TooltipCompat.setTooltipText(native, hint)
                except Exception:
                    pass
    except Exception:
        pass


def setup_list_accessible(list_widget, item_labels: Optional[List[str]] = None) -> None:
    """Macht ein Toga-Listen-Widget für TalkBack zugänglich.

    Setzt eine Content Description auf der Liste selbst. Einzelne Zeilen
    werden über AccessibleDetailedList automatisch beschriftet.
    """
    try:
        description = "Liste"
        if item_labels is not None:
            description = f"Liste, {len(item_labels)} Einträge"
        list_widget._impl.native.setContentDescription(description)
    except Exception:
        pass


class AccessibleDetailedList(toga.DetailedList):
    """toga.DetailedList mit automatischen Content Descriptions für Zeilen.

    Format der TalkBack-Ansage: "Titel, Untertitel, Badge"
    (entspricht dem wx-Konvention: Komma als Trennzeichen, kein Pipe).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nach dem Aufbau des nativen Widgets Descriptions setzen
        # (wird erneut aufgerufen wenn data sich ändert)
        self._apply_row_descriptions()

    def _apply_row_descriptions(self) -> None:
        """Setzt Content Descriptions auf allen nativen Listenzeilen."""
        try:
            native_list = self._impl.native
            adapter = native_list.getAdapter()
            if adapter is None:
                return
            count = adapter.getCount()
            for i in range(count):
                view = adapter.getView(i, None, native_list)
                if view is None:
                    continue
                item = self.data[i]
                parts = []
                title = getattr(item, "title", None) or ""
                subtitle = getattr(item, "subtitle", None) or ""
                badge = getattr(item, "badge", None) or ""
                if title:
                    parts.append(str(title))
                if subtitle:
                    parts.append(str(subtitle))
                if badge:
                    parts.append(str(badge))
                description = ", ".join(parts) if parts else f"Eintrag {i + 1}"
                view.setContentDescription(description)
        except Exception:
            pass

    def set_row_description(self, index: int, text: str) -> None:
        """Setzt die Content Description einer einzelnen Zeile direkt."""
        try:
            native_list = self._impl.native
            adapter = native_list.getAdapter()
            if adapter is None:
                return
            view = adapter.getView(index, None, native_list)
            if view is not None:
                view.setContentDescription(text)
        except Exception:
            pass


def patch_all(app) -> None:
    """Einmalig beim App-Start aufrufen.

    Setzt globale Accessibility-Defaults für alle Toga-Widgets dieser App.
    Derzeit ist kein globaler Klassen-Patch notwendig, da TalkBack native
    Android-Views direkt liest. Zukünftige globale Patches kommen hierher.
    """
    pass
