"""Formatierung von Benutzerkonto-Feldern für die Admin-Kontoliste (wx + Qt)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from i18n import _, current_language

# Der Server liefert UserAccount.szLastLoginTime in Ortszeit als
# "yyyy/MM/dd hh:mm" (so parst es auch der offizielle Qt-Client).
_LAST_LOGIN_FORMATS = ("%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S")

_DISPLAY_FORMATS = {
    "de": "%d.%m.%Y %H:%M",
    "fr": "%d/%m/%Y %H:%M",
    "es": "%d/%m/%Y %H:%M",
    "en": "%Y-%m-%d %H:%M",
}


def parse_last_login(raw: str) -> Optional[datetime]:
    """Zeitpunkt der letzten Anmeldung oder None, wenn nie angemeldet.

    Ein Konto, das sich nie angemeldet hat, liefert einen leeren Wert oder
    ein Datum um 1970 (Unix-Epoche) – beides gilt als "nie".
    """
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in _LAST_LOGIN_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return dt if dt.year > 1970 else None
    return None


def format_last_login(raw: str) -> str:
    """Lokalisierte Anzeige der letzten Anmeldung, "Nie" bei nie angemeldet.

    Unbekannte Formate werden unverändert angezeigt statt verworfen.
    """
    dt = parse_last_login(raw)
    if dt is not None:
        return dt.strftime(_DISPLAY_FORMATS.get(current_language(), _DISPLAY_FORMATS["en"]))
    text = (raw or "").strip()
    if text and not (text[:4].isdigit() and int(text[:4]) <= 1970):
        return text
    return _("Nie")


def last_login_sort_key(raw: str) -> float:
    """Sortierschlüssel: neueste Anmeldung zuerst, nie angemeldet am Ende."""
    dt = parse_last_login(raw)
    return -dt.timestamp() if dt is not None else float("inf")
