from __future__ import annotations

from typing import TYPE_CHECKING

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import set_description, announce

if TYPE_CHECKING:
    pass

# Verfügbare App-Sprachen (Codes und Labels)
_LANG_CODES = ["de", "en", "fr", "es"]
_LANG_LABELS = ["Deutsch", "Englisch", "Französisch", "Spanisch"]

# TTS-Sprachen (espeak-ng Sprachcodes und Anzeigenamen)
_TTS_LANGS = [
    ("de", "Deutsch"),
    ("en", "Englisch"),
    ("fr", "Französisch"),
    ("es", "Spanisch"),
    ("it", "Italienisch"),
    ("nl", "Niederländisch"),
    ("pl", "Polnisch"),
    ("ru", "Russisch"),
]


class SettingsTab(toga.Box):
    """Einstellungen-Tab: TTS, Benachrichtigungen, Geräte-Sync, räumliches Audio, Sprache."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self.app = app
        self._build_ui()
        self.load_settings()

    def _build_ui(self) -> None:
        scroll = toga.ScrollContainer(horizontal=False, style=Pack(flex=1))
        content = toga.Box(style=Pack(direction=COLUMN, padding=8))

        # --- Abschnitt: Sprache ---
        content.add(toga.Label("App-Sprache", style=Pack(padding_bottom=4, font_weight="bold")))
        lang_row = toga.Box(style=Pack(direction=ROW, padding_bottom=12))
        lang_label = toga.Label("Sprache:", style=Pack(padding_right=8))
        set_description(lang_label, "App-Sprache Beschriftung")
        self.app_language = toga.Selection(
            items=_LANG_LABELS,
            style=Pack(flex=1),
        )
        set_description(self.app_language, "App-Sprache auswählen (Neustart erforderlich)")
        lang_row.add(lang_label)
        lang_row.add(self.app_language)
        content.add(lang_row)
        content.add(toga.Label("(Neustart erforderlich)", style=Pack(padding_bottom=12, font_size=11)))

        # --- Abschnitt: Benachrichtigungen ---
        content.add(toga.Label("Benachrichtigungen", style=Pack(padding_bottom=4, font_weight="bold")))
        self.notify_user_join = toga.Switch("Nutzer beigetreten ansagen")
        set_description(self.notify_user_join, "TalkBack sagt an wenn ein Nutzer den Kanal betritt")
        content.add(self.notify_user_join)

        self.notify_user_leave = toga.Switch("Nutzer verlassen ansagen")
        set_description(self.notify_user_leave, "TalkBack sagt an wenn ein Nutzer den Kanal verlässt")
        content.add(self.notify_user_leave)

        self.notify_private_msg = toga.Switch("Privatnachricht ansagen")
        set_description(self.notify_private_msg, "TalkBack sagt an wenn eine Privatnachricht eintrifft")
        content.add(self.notify_private_msg)

        self.notify_channel_msg = toga.Switch("Kanalnachricht ansagen")
        set_description(self.notify_channel_msg, "TalkBack sagt an wenn eine Kanalnachricht eintrifft")
        content.add(self.notify_channel_msg)
        content.add(toga.Box(style=Pack(padding_bottom=12)))  # Abstandhalter

        # --- Abschnitt: TTS ---
        content.add(toga.Label("Text-to-Speech (TTS)", style=Pack(padding_bottom=4, font_weight="bold")))
        self.tts_enabled = toga.Switch("TTS aktivieren")
        set_description(self.tts_enabled, "Text-to-Speech für Nachrichten aktivieren")
        content.add(self.tts_enabled)

        tts_lang_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4, padding_top=4))
        tts_lang_label = toga.Label("TTS-Sprache:", style=Pack(padding_right=8))
        set_description(tts_lang_label, "TTS-Sprache Beschriftung")
        self.tts_language = toga.Selection(
            items=[label for _, label in _TTS_LANGS],
            style=Pack(flex=1),
        )
        set_description(self.tts_language, "TTS-Sprache auswählen")
        tts_lang_row.add(tts_lang_label)
        tts_lang_row.add(self.tts_language)
        content.add(tts_lang_row)

        tts_rate_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        tts_rate_label = toga.Label("Sprechgeschwindigkeit (50–400):", style=Pack(padding_right=8))
        set_description(tts_rate_label, "TTS-Sprechgeschwindigkeit Beschriftung")
        self.tts_rate = toga.NumberInput(
            min=50,
            max=400,
            step=10,
            style=Pack(flex=1),
        )
        set_description(self.tts_rate, "TTS-Sprechgeschwindigkeit in Wörtern pro Minute")
        tts_rate_row.add(tts_rate_label)
        tts_rate_row.add(self.tts_rate)
        content.add(tts_rate_row)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Abschnitt: Räumliches Audio ---
        content.add(toga.Label("Räumliches Audio", style=Pack(padding_bottom=4, font_weight="bold")))
        self.auto_spatial_audio = toga.Switch("Automatisches räumliches Audio")
        set_description(
            self.auto_spatial_audio,
            "Verteilt gleichzeitig sprechende Nutzer automatisch auf links, rechts und Mitte – "
            "damit lassen sie sich akustisch unterscheiden"
        )
        content.add(self.auto_spatial_audio)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Abschnitt: Geräte-Sync (v10.2.0) ---
        content.add(toga.Label("Geräte-Sync", style=Pack(padding_bottom=4, font_weight="bold")))
        content.add(toga.Label(
            "Synchronisiert Einstellungen zwischen diesem und anderen Geräten.",
            style=Pack(padding_bottom=4, font_size=11),
        ))
        self.sync_enabled = toga.Switch("Geräte-Sync aktivieren")
        set_description(
            self.sync_enabled,
            "Geräte-Sync aktivieren – verbindet dieses Gerät mit anderen Geräten"
        )
        content.add(self.sync_enabled)

        self.sync_pair_btn = toga.Button("Neues Gerät koppeln...", on_press=self._on_pair)
        set_description(self.sync_pair_btn, "Neues Gerät zum Sync koppeln")
        content.add(self.sync_pair_btn)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Abschnitt: Chat ---
        content.add(toga.Label("Chat", style=Pack(padding_bottom=4, font_weight="bold")))
        self.save_chat_history = toga.Switch("Chat-Verlauf speichern")
        set_description(self.save_chat_history, "Chat-Verlauf auf dem Gerät speichern")
        content.add(self.save_chat_history)

        self.chat_show_timestamps = toga.Switch("Zeitstempel im Chat anzeigen")
        set_description(self.chat_show_timestamps, "Zeitstempel vor jeder Chat-Nachricht anzeigen")
        content.add(self.chat_show_timestamps)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Verbindung ---
        content.add(toga.Label("Verbindung", style=Pack(padding_bottom=4, font_weight="bold")))
        self.auto_reconnect = toga.Switch("Automatisch neu verbinden")
        set_description(self.auto_reconnect, "Bei Verbindungsabbruch automatisch neu verbinden")
        content.add(self.auto_reconnect)

        self.auto_join_last_channel = toga.Switch("Letzten Kanal automatisch beitreten")
        set_description(self.auto_join_last_channel, "Nach dem Verbinden automatisch den zuletzt besuchten Kanal betreten")
        content.add(self.auto_join_last_channel)
        content.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Speichern ---
        save_btn = toga.Button("Einstellungen speichern", on_press=self._on_save)
        set_description(save_btn, "Alle Einstellungen speichern")
        content.add(save_btn)

        scroll.content = content
        self.add(scroll)

    # ------------------------------------------------------------------
    # Laden / Speichern
    # ------------------------------------------------------------------

    def load_settings(self) -> None:
        """Aktuelle Einstellungen in die UI-Widgets laden."""
        s = self.app.settings_store.settings

        # Sprache
        lang_code = getattr(s, "app_language", "de") or "de"
        if lang_code in _LANG_CODES:
            self.app_language.value = _LANG_LABELS[_LANG_CODES.index(lang_code)]

        # Benachrichtigungen
        self.notify_user_join.value = bool(getattr(s, "tts_speak_user_join", True))
        self.notify_user_leave.value = bool(getattr(s, "tts_speak_user_leave", True))
        self.notify_private_msg.value = bool(getattr(s, "notify_background_private", True))
        self.notify_channel_msg.value = bool(getattr(s, "notify_background_channel", False))

        # TTS
        self.tts_enabled.value = bool(getattr(s, "tts_enabled", False))
        tts_lang = getattr(s, "tts_language", "de") or "de"
        tts_lang_labels = [label for _, label in _TTS_LANGS]
        tts_lang_codes = [code for code, _ in _TTS_LANGS]
        if tts_lang in tts_lang_codes:
            self.tts_language.value = tts_lang_labels[tts_lang_codes.index(tts_lang)]
        self.tts_rate.value = int(getattr(s, "tts_rate", 175) or 175)

        # Räumliches Audio
        self.auto_spatial_audio.value = bool(getattr(s, "auto_spatial_audio", False))

        # Geräte-Sync
        self.sync_enabled.value = bool(getattr(s, "device_sync_enabled", False))

        # Chat
        self.save_chat_history.value = bool(getattr(s, "save_chat_history", False))
        self.chat_show_timestamps.value = bool(getattr(s, "chat_show_timestamps", False))

        # Verbindung
        self.auto_reconnect.value = bool(getattr(s, "auto_reconnect_enabled", True))
        self.auto_join_last_channel.value = bool(getattr(s, "auto_join_last_channel", False))

    def save_settings(self) -> None:
        """UI-Widget-Werte in die Einstellungen schreiben und speichern."""
        s = self.app.settings_store.settings

        # Sprache
        sel_label = self.app_language.value
        if sel_label in _LANG_LABELS:
            s.app_language = _LANG_CODES[_LANG_LABELS.index(sel_label)]

        # Benachrichtigungen
        s.tts_speak_user_join = bool(self.notify_user_join.value)
        s.tts_speak_user_leave = bool(self.notify_user_leave.value)
        s.notify_background_private = bool(self.notify_private_msg.value)
        s.notify_background_channel = bool(self.notify_channel_msg.value)

        # TTS
        s.tts_enabled = bool(self.tts_enabled.value)
        sel_tts_label = self.tts_language.value
        tts_lang_labels = [label for _, label in _TTS_LANGS]
        tts_lang_codes = [code for code, _ in _TTS_LANGS]
        if sel_tts_label in tts_lang_labels:
            s.tts_language = tts_lang_codes[tts_lang_labels.index(sel_tts_label)]
        try:
            s.tts_rate = int(self.tts_rate.value or 175)
        except (TypeError, ValueError):
            s.tts_rate = 175

        # Räumliches Audio
        s.auto_spatial_audio = bool(self.auto_spatial_audio.value)

        # Geräte-Sync
        s.device_sync_enabled = bool(self.sync_enabled.value)

        # Chat
        s.save_chat_history = bool(self.save_chat_history.value)
        s.chat_show_timestamps = bool(self.chat_show_timestamps.value)

        # Verbindung
        s.auto_reconnect_enabled = bool(self.auto_reconnect.value)
        s.auto_join_last_channel = bool(self.auto_join_last_channel.value)

        self.app.settings_store.save()

    # ------------------------------------------------------------------
    # Ereignis-Handler
    # ------------------------------------------------------------------

    def _on_save(self, widget) -> None:
        self.save_settings()
        announce(self.app, "Einstellungen gespeichert")

    def _on_pair(self, widget) -> None:
        """Neues Gerät koppeln – Platzhalter für Companion-Server-Dialog."""
        announce(self.app, "Geräte-Kopplung noch nicht verfügbar")
