from __future__ import annotations

import time
from typing import TYPE_CHECKING

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import set_description, set_live_region, announce, LIVE_POLITE

if TYPE_CHECKING:
    pass


class SystemTab(toga.Box):
    """System-Log-Tab: Ereignisprotokoll, TTS-Einstellungen, Verbindungsinfo."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self.app = app
        self._build_ui()
        # Auf System-Log-Ereignisse aus dem EventBus hören
        app.bus.on("system_log", self._on_system_log)
        app.bus.on("connected", self._on_connected)
        app.bus.on("disconnected", self._on_disconnected)

    def _build_ui(self) -> None:
        # --- System-Log ---
        log_label = toga.Label("System-Log", style=Pack(padding_bottom=4, font_weight="bold"))
        set_description(log_label, "System-Log Abschnitt")
        self.add(log_label)

        # MultilineTextInput mit Live Region POLITE – TalkBack liest neue Einträge vor,
        # wartet aber auf eine Sprechpause (weniger aufdringlich als ASSERTIVE)
        self.log_view = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, padding_bottom=4),
        )
        set_description(self.log_view, "System-Log – zeigt Verbindungs- und Fehlermeldungen")
        set_live_region(self.log_view, LIVE_POLITE)
        self.add(self.log_view)

        # Log-Aktionen
        log_btn_row = toga.Box(style=Pack(direction=ROW, padding_bottom=12))
        clear_btn = toga.Button("Log leeren", on_press=self._on_clear)
        set_description(clear_btn, "System-Log leeren")
        copy_btn = toga.Button("Log kopieren", on_press=self._on_copy)
        set_description(copy_btn, "System-Log in die Zwischenablage kopieren")
        log_btn_row.add(clear_btn)
        log_btn_row.add(copy_btn)
        self.add(log_btn_row)

        # --- TTS-Einstellungen (Schnellzugriff) ---
        tts_label = toga.Label("TTS-Schnelleinstellungen", style=Pack(padding_bottom=4, font_weight="bold"))
        set_description(tts_label, "TTS Schnelleinstellungen Abschnitt")
        self.add(tts_label)

        self.tts_speak_chat = toga.Switch("Chat-Nachrichten vorlesen")
        set_description(self.tts_speak_chat, "Eingehende Chat-Nachrichten via TTS vorlesen")
        self.add(self.tts_speak_chat)

        self.tts_speak_private = toga.Switch("Privatnachrichten vorlesen")
        set_description(self.tts_speak_private, "Eingehende Privatnachrichten via TTS vorlesen")
        self.add(self.tts_speak_private)

        self.tts_speak_user_join = toga.Switch("Nutzer beigetreten vorlesen")
        set_description(self.tts_speak_user_join, "Ankündigung wenn ein Nutzer den Kanal betritt")
        self.add(self.tts_speak_user_join)

        self.tts_speak_user_leave = toga.Switch("Nutzer verlassen vorlesen")
        set_description(self.tts_speak_user_leave, "Ankündigung wenn ein Nutzer den Kanal verlässt")
        self.add(self.tts_speak_user_leave)

        self.tts_speak_who_speaks = toga.Switch("Sprechenden Nutzer ansagen")
        set_description(self.tts_speak_who_speaks, "Ansagen wer gerade im Kanal spricht")
        self.add(self.tts_speak_who_speaks)

        tts_save_btn = toga.Button("TTS-Einstellungen speichern", on_press=self._on_save_tts)
        set_description(tts_save_btn, "TTS-Schnelleinstellungen speichern")
        self.add(tts_save_btn)
        self.add(toga.Box(style=Pack(padding_bottom=12)))

        # --- Verbindungsinfo ---
        conn_label = toga.Label("Verbindungsinfo", style=Pack(padding_bottom=4, font_weight="bold"))
        set_description(conn_label, "Verbindungsinfo Abschnitt")
        self.add(conn_label)

        self.conn_status = toga.Label("Nicht verbunden", style=Pack(padding_bottom=4))
        set_description(self.conn_status, "Aktueller Verbindungsstatus")
        set_live_region(self.conn_status, LIVE_POLITE)
        self.add(self.conn_status)

        ping_btn = toga.Button("Ping ansagen", on_press=self._on_announce_ping)
        set_description(ping_btn, "Aktuellen Ping via TalkBack ansagen")
        self.add(ping_btn)

        # Einstellungen laden
        self._load_tts_settings()

    # ------------------------------------------------------------------
    # Öffentliche Methode: Log-Eintrag hinzufügen (thread-sicher via bus)
    # ------------------------------------------------------------------

    def append(self, text: str) -> None:
        """System-Log-Eintrag hinzufügen – thread-sicher."""
        def update() -> None:
            timestamp = time.strftime("%H:%M:%S")
            entry = f"[{timestamp}] {text}"
            current = self.log_view.value or ""
            self.log_view.value = (current + "\n" if current else "") + entry

        self.app.loop.call_soon_threadsafe(update)

    # ------------------------------------------------------------------
    # EventBus-Handler
    # ------------------------------------------------------------------

    def _on_system_log(self, message: str = "") -> None:
        """System-Log-Event vom EventBus."""
        self.append(message)

    def _on_connected(self, server: str = "", **kwargs) -> None:
        def update() -> None:
            label = f"Verbunden mit {server}" if server else "Verbunden"
            self.conn_status.text = label
            self.append(label)

        self.app.loop.call_soon_threadsafe(update)

    def _on_disconnected(self, reason: str = "", **kwargs) -> None:
        def update() -> None:
            label = f"Getrennt: {reason}" if reason else "Verbindung getrennt"
            self.conn_status.text = "Nicht verbunden"
            self.append(label)

        self.app.loop.call_soon_threadsafe(update)

    # ------------------------------------------------------------------
    # UI-Ereignis-Handler
    # ------------------------------------------------------------------

    def _on_clear(self, widget) -> None:
        self.log_view.value = ""
        announce(self.app, "System-Log geleert")

    def _on_copy(self, widget) -> None:
        content = self.log_view.value or ""
        if not content.strip():
            announce(self.app, "Log ist leer")
            return
        try:
            self.app.clipboard.content = content
            announce(self.app, "System-Log in Zwischenablage kopiert")
        except Exception:
            announce(self.app, "Kopieren nicht verfügbar")

    def _on_announce_ping(self, widget) -> None:
        try:
            ping = self.app.client.get_server_ping()
            announce(self.app, f"Ping: {ping} Millisekunden")
        except Exception:
            announce(self.app, "Ping nicht verfügbar")

    def _on_save_tts(self, widget) -> None:
        self._save_tts_settings()
        announce(self.app, "TTS-Einstellungen gespeichert")

    # ------------------------------------------------------------------
    # TTS-Einstellungen laden/speichern
    # ------------------------------------------------------------------

    def _load_tts_settings(self) -> None:
        s = self.app.settings_store.settings
        self.tts_speak_chat.value = bool(getattr(s, "tts_speak_chat", True))
        self.tts_speak_private.value = bool(getattr(s, "tts_speak_private", True))
        self.tts_speak_user_join.value = bool(getattr(s, "tts_speak_user_join", True))
        self.tts_speak_user_leave.value = bool(getattr(s, "tts_speak_user_leave", True))
        self.tts_speak_who_speaks.value = bool(getattr(s, "tts_speak_who_speaks", False))

    def _save_tts_settings(self) -> None:
        s = self.app.settings_store.settings
        s.tts_speak_chat = bool(self.tts_speak_chat.value)
        s.tts_speak_private = bool(self.tts_speak_private.value)
        s.tts_speak_user_join = bool(self.tts_speak_user_join.value)
        s.tts_speak_user_leave = bool(self.tts_speak_user_leave.value)
        s.tts_speak_who_speaks = bool(self.tts_speak_who_speaks.value)
        self.app.settings_store.save()
