"""Hilfsfunktion: Formularwerte in ein bestehendes ServerProfile übernehmen.

Das Serverformular (macOS-Verbindungstab) zeigt nicht alle Felder eines
ServerProfile – Kanal, Kanalpasswort, Beitrittscode, ElevenLabs-Schlüssel
usw. haben kein eigenes Eingabefeld. Früher baute das Formular beim
Speichern ein komplett neues Profil, und diese Felder gingen verloren.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from .models import ServerProfile


def merge_form_into_profile(base: Optional[ServerProfile], **form_values) -> ServerProfile:
    """Erzeugt ein Profil aus *form_values* und übernimmt die übrigen Felder
    von *base* – aber nur, wenn das Formular noch denselben Server
    (Host + TCP-Port) beschreibt. Tippt der Nutzer einen anderen Server ein,
    um ihn neu anzulegen, wäre z. B. der Kanal des alten Servers falsch.
    """
    if (
        base is not None
        and (base.host or "").strip().lower() == str(form_values.get("host", "")).strip().lower()
        and int(base.tcp_port) == int(form_values.get("tcp_port", 0))
    ):
        return dataclasses.replace(base, **form_values)
    return ServerProfile(**form_values)
