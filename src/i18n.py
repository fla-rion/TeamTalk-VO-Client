"""i18n – Internationalisierung für TeamTalk VoiceOver Client (v3.6.0).

Verwendung:
    from i18n import _, set_language, current_language

    set_language("en")
    label = _("Verbinden")          # → "Connect"
    label = _("Verbinden", "de")    # → "Verbinden" (explizit Deutsch)
"""
from __future__ import annotations

_LANG = "de"  # Standard: Deutsch

# ---------------------------------------------------------------------------
# Übersetzungstabelle  DE → EN
# ---------------------------------------------------------------------------
# Schlüssel = deutscher Originaltext, Wert = englische Übersetzung
_TRANSLATIONS: dict[str, str] = {
    # Menü: Datei
    "Datei": "File",
    "Verbinden...": "Connect...",
    "Trennen": "Disconnect",
    "Server hinzufügen...": "Add server...",
    "Server entfernen": "Remove server",
    "Server bearbeiten...": "Edit server...",
    "Konversationen aufzeichnen...": "Record conversations...",
    "Automatisch neu verbinden": "Auto-reconnect",
    "Beenden": "Quit",
    # Menü: Kanal
    "Kanal": "Channel",
    "Kanal beitreten": "Join channel",
    "Kanal verlassen": "Leave channel",
    "Kanal erstellen...": "Create channel...",
    "Kanal entfernen": "Remove channel",
    "Kanalpasswort eingeben...": "Enter channel password...",
    "Audio-Datei in Kanal streamen...": "Stream audio file to channel...",
    # Menü: Benutzer
    "Benutzer": "User",
    "Privatnachricht senden...": "Send private message...",
    "Benutzer info": "User info",
    "Stummschalten": "Mute",
    "Stummschaltung aufheben": "Unmute",
    "Benutzer kicken": "Kick user",
    "Benutzer bannen": "Ban user",
    "Abonnements...": "Subscriptions...",
    "Notiz bearbeiten...": "Edit note...",
    # Menü: Server
    "Server": "Server",
    "Server-Eigenschaften...": "Server properties...",
    "Statistiken": "Statistics",
    "Statistiken vorlesen": "Announce statistics",
    "Verbindungsstatistiken...": "Connection statistics...",
    "Benutzer online...": "Users online...",
    "Ban-Liste...": "Ban list...",
    # Menü: Profil
    "Profil": "Profile",
    "Status ändern...": "Change status...",
    "Profilbild ändern...": "Change avatar...",
    # Menü: Audio
    "Audio": "Audio",
    "Push-to-Talk": "Push-to-Talk",
    "Sprachaktivierung": "Voice activation",
    "Audio-Einstellungen...": "Audio settings...",
    "AGC": "AGC",
    "Rauschunterdrückung": "Noise suppression",
    "Echounterdrückung": "Echo cancellation",
    "Effekte anwenden": "Apply effects",
    "Audio anwenden": "Apply audio",
    "Geräte aktualisieren": "Refresh devices",
    "Mikrofontest": "Microphone test",
    "Alles stummschalten": "Mute all",
    "Equalizer-Voreinstellungen...": "Equalizer presets...",
    # Menü: Video
    "Video": "Video",
    "Video senden": "Send video",
    "Video-Einstellungen...": "Video settings...",
    "Video-Geräte aktualisieren": "Refresh video devices",
    # Menü: Aufnahmen
    "Aufnahmen": "Recordings",
    "Aufnahme starten...": "Start recording...",
    "Aufnahme stoppen": "Stop recording",
    "Geplante Aufnahmen...": "Scheduled recordings...",
    "Aufnahmen durchsuchen...": "Browse recordings...",
    # Menü: Automation
    "Automation": "Automation",
    "Makro-Editor...": "Macro editor...",
    "Geplante Makros...": "Scheduled macros...",
    "Trigger-Regeln...": "Trigger rules...",
    # Menü: Hilfe
    "Hilfe": "Help",
    "Einstellungen...": "Settings...",
    "Logs exportieren...": "Export logs...",
    "Handbuch": "Manual",
    "Tastenkürzel-Referenz...": "Shortcut reference...",
    "Changelog": "Changelog",
    "Über": "About",
    # Tabs
    "Verbindung": "Connection",
    "Kanäle und Chat": "Channels & Chat",
    "Chat": "Chat",
    "Audio": "Audio",
    "Medien": "Media",
    "Dateien": "Files",
    "Administration": "Administration",
    "ElevenLabs TTS": "ElevenLabs TTS",
    "Desktopfreigabe": "Desktop sharing",
    "Einstellungen": "Settings",
    "Tastenkürzel": "Shortcuts",
    "System-Log": "System log",
    "Video": "Video",
    # Einstellungsbereich
    "Allgemein": "General",
    "Sound-Ereignisse": "Sound events",
    "Audio & Aufnahme": "Audio & Recording",
    "TTS": "TTS",
    "Chat & Automation": "Chat & Automation",
    "KI & Integration": "AI & Integration",
    # Status-Meldungen
    "Verbunden": "Connected",
    "Getrennt": "Disconnected",
    "Aufnahme gestartet": "Recording started",
    "Aufnahme beendet": "Recording stopped",
    "Aufnahme läuft bereits": "Recording already running",
    "Keine laufende Aufnahme": "No active recording",
    "Ausgabe stummgeschaltet": "Output muted",
    "Ausgabe aktiv": "Output active",
    "PTT aktiv": "PTT active",
    "PTT deaktiviert": "PTT deactivated",
    "Hotkey gespeichert": "Hotkey saved",
    "TTS abgebrochen": "TTS cancelled",
    "Nicht verbunden": "Not connected",
    "Sprechen aktiv": "Speaking active",
    "Stummgeschaltet": "Muted",
    "Stummschaltung aufgehoben": "Unmuted",
    "Kein letzter Absender": "No last sender",
    "Privatantwort bereit": "Private reply ready",
    "Ping nicht verfügbar": "Ping unavailable",
    "Nutzerinfo nicht verfügbar": "User info unavailable",
    "Pegel nicht verfügbar": "Level unavailable",
    # Dialoge
    "Aufnahmen-Browser": "Recording browser",
    "Makro-Editor": "Macro editor",
    "Geplante Makros": "Scheduled macros",
    "Trigger-Regeln": "Trigger rules",
    "Equalizer-Voreinstellungen": "Equalizer presets",
    "Tastenkürzel-Referenz": "Shortcut reference",
    "Über TeamTalk VoiceOver Client": "About TeamTalk VoiceOver Client",
    # Buttons
    "Verbinden": "Connect",
    "Trennen": "Disconnect",
    "Speichern": "Save",
    "Abbrechen": "Cancel",
    "Schließen": "Close",
    "Hinzufügen": "Add",
    "Entfernen": "Remove",
    "Löschen": "Delete",
    "Bearbeiten": "Edit",
    "Neu": "New",
    "Exportieren": "Export",
    "Importieren": "Import",
    "Abspielen": "Play",
    # Einstellungen Labels
    "Sprache": "Language",
    "Deutsch": "German",
    "Englisch": "English",
}


def set_language(lang: str) -> None:
    """Setzt die aktive Sprache ('de' oder 'en')."""
    global _LANG
    _LANG = lang if lang in ("de", "en") else "de"


def current_language() -> str:
    return _LANG


def _(text: str, lang: str | None = None) -> str:
    """Gibt den übersetzten Text zurück (oder Original wenn keine Übersetzung)."""
    effective = lang if lang is not None else _LANG
    if effective == "de":
        return text
    return _TRANSLATIONS.get(text, text)
