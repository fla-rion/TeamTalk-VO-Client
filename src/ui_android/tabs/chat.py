from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, List, Optional

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import set_description, set_live_region, announce, LIVE_ASSERTIVE

if TYPE_CHECKING:
    pass


# Markdown-Muster die für TalkBack bereinigt werden (nur Marker entfernen)
_MD_PATTERNS = [
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),   # **fett**
    (re.compile(r'\*(.+?)\*'),     r'\1'),   # *kursiv*
    (re.compile(r'`(.+?)`'),       r'\1'),   # `code`
]

# Emoji-Shortcode-Tabelle (identisch mit chat.py der wx-Variante)
_EMOJI_SHORTCODES = {
    ":+1:": "👍", ":-1:": "👎", ":smile:": "😊", ":laughing:": "😂",
    ":wink:": "😉", ":heart:": "❤️", ":fire:": "🔥", ":wave:": "👋",
    ":ok:": "✅", ":x:": "❌", ":warning:": "⚠️", ":info:": "ℹ️",
    ":mic:": "🎤", ":headphones:": "🎧", ":speaker:": "🔊",
    ":mute:": "🔇", ":clap:": "👏", ":star:": "⭐", ":check:": "✔️",
    ":question:": "❓", ":exclamation:": "❗", ":thumbsup:": "👍",
    ":thumbsdown:": "👎", ":tada:": "🎉", ":eyes:": "👀",
}


def _strip_markdown(text: str) -> str:
    """Entfernt einfache Markdown-Marker (**, *, `) aus dem Text."""
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def expand_emoji_shortcodes(text: str) -> str:
    """Ersetzt :shortcode: durch Unicode-Emojis."""
    for code, emoji in _EMOJI_SHORTCODES.items():
        text = text.replace(code, emoji)
    return text


class ChatTab(toga.Box):
    """Chat-Tab: Chatverlauf, Empfängerauswahl, Nachrichten senden."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self.app = app
        # Parallele Listen für Empfänger-IDs (nie per String-Split)
        self._user_ids: List[int] = []
        self._user_names: List[str] = []
        # Suchergebnisse-Positionen
        self._search_hits: List[str] = []
        self._build_ui()
        app.bus.on("chat_message", self._on_chat_message)
        app.bus.on("users_updated", self._on_users_updated)

    def _build_ui(self) -> None:
        # --- Ziel-Zeile (Kanal / Privat) ---
        target_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        ziel_label = toga.Label("Chat-Ziel:", style=Pack(padding_right=8))
        set_description(ziel_label, "Chat-Ziel Beschriftung")
        self.target_display = toga.Label("Kanal", style=Pack(flex=1))
        set_description(self.target_display, "Aktuelles Chat-Ziel")
        self.private_switch = toga.Switch(
            "Privat",
            on_change=self._on_private_toggle,
        )
        set_description(self.private_switch, "Privaten Chat aktivieren")
        target_row.add(ziel_label)
        target_row.add(self.target_display)
        target_row.add(self.private_switch)
        self.add(target_row)

        # --- Empfänger-Auswahl (nur bei Privat aktiv) ---
        recipient_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        empfaenger_label = toga.Label("Empfänger:", style=Pack(padding_right=8))
        set_description(empfaenger_label, "Empfänger Beschriftung")
        self.recipient_selection = toga.Selection(
            items=[],
            on_change=self._on_recipient_changed,
            style=Pack(flex=1),
        )
        set_description(self.recipient_selection, "Privaten Empfänger auswählen")
        recipient_row.add(empfaenger_label)
        recipient_row.add(self.recipient_selection)
        self.add(recipient_row)

        # --- Suche ---
        search_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        self.search_input = toga.TextInput(
            placeholder="Chatverlauf durchsuchen...",
            style=Pack(flex=1, padding_right=8),
        )
        set_description(self.search_input, "Suchbegriff im Chatverlauf eingeben")
        self.search_btn = toga.Button("Suchen", on_press=self._on_search)
        set_description(self.search_btn, "Im Chatverlauf suchen")
        search_row.add(self.search_input)
        search_row.add(self.search_btn)
        self.add(search_row)

        # --- Chatverlauf (Live Region ASSERTIVE → TalkBack liest neue Nachrichten sofort) ---
        self.chat_log = toga.MultilineTextInput(
            readonly=True,
            style=Pack(flex=1, padding_bottom=4),
        )
        set_description(self.chat_log, "Chatverlauf")
        set_live_region(self.chat_log, LIVE_ASSERTIVE)
        self.add(self.chat_log)

        # --- Verlauf-Aktionen ---
        history_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        self.export_btn = toga.Button("Exportieren", on_press=self._on_export)
        set_description(self.export_btn, "Chatverlauf als Textdatei exportieren")
        self.clear_btn = toga.Button("Leeren", on_press=self._on_clear)
        set_description(self.clear_btn, "Chatverlauf leeren")
        history_row.add(self.export_btn)
        history_row.add(self.clear_btn)
        self.add(history_row)

        # --- Eingabe-Zeile ---
        input_row = toga.Box(style=Pack(direction=ROW))
        self.msg_input = toga.TextInput(
            placeholder="Nachricht eingeben...",
            style=Pack(flex=1, padding_right=8),
        )
        set_description(self.msg_input, "Nachricht eingeben")
        self.send_btn = toga.Button("Senden", on_press=self._on_send)
        set_description(self.send_btn, "Nachricht senden")
        input_row.add(self.msg_input)
        input_row.add(self.send_btn)
        self.add(input_row)

    # ------------------------------------------------------------------
    # EventBus-Handler
    # ------------------------------------------------------------------

    def _on_chat_message(self, user: str = "", message: str = "", private: bool = False) -> None:
        """Eingehende Chat-Nachricht anzeigen und via TalkBack vorlesen."""
        clean = _strip_markdown(message)
        prefix = "[Privat] " if private else ""
        label = f"{prefix}{user}: {clean}"

        def update() -> None:
            current = self.chat_log.value or ""
            self.chat_log.value = (current + "\n" if current else "") + label
            announce(self.app, label)

        self.app.loop.call_soon_threadsafe(update)

    def _on_users_updated(self, users: list = None) -> None:
        """Nutzerliste aktualisiert – Empfänger-Auswahl neu befüllen."""
        if users is None:
            users = []

        def update() -> None:
            self._user_ids = []
            self._user_names = []
            names = []
            for user in users:
                uid = int(getattr(user, "nUserID", 0))
                nickname = str(getattr(user, "szNickname", "") or "")
                username = str(getattr(user, "szUsername", "") or "")
                label = nickname or username or f"Nutzer {uid}"
                self._user_ids.append(uid)
                self._user_names.append(label)
                names.append(label)
            self.recipient_selection.items = names if names else ["(keine Nutzer)"]

        self.app.loop.call_soon_threadsafe(update)

    # ------------------------------------------------------------------
    # UI-Ereignis-Handler
    # ------------------------------------------------------------------

    def _on_private_toggle(self, widget) -> None:
        is_private = bool(widget.value)
        if is_private:
            self.target_display.text = "Privat"
        else:
            self.target_display.text = "Kanal"
        announce(
            self.app,
            "Privater Chat aktiviert" if is_private else "Kanal-Chat aktiviert",
        )

    def _on_recipient_changed(self, widget) -> None:
        selected = widget.value
        if selected and self.private_switch.value:
            self.target_display.text = f"Privat an {selected}"

    def _on_send(self, widget) -> None:
        msg = (self.msg_input.value or "").strip()
        if not msg:
            return
        msg = expand_emoji_shortcodes(msg)

        client = self.app.client
        if not client.is_connected():
            announce(self.app, "Nicht verbunden – Nachricht kann nicht gesendet werden")
            return

        is_private = bool(self.private_switch.value)
        if is_private:
            # Empfänger-ID über parallele Liste ermitteln (nie per String-Split)
            sel_name = self.recipient_selection.value
            uid = None
            for i, name in enumerate(self._user_names):
                if name == sel_name and i < len(self._user_ids):
                    uid = self._user_ids[i]
                    break
            if uid is None:
                announce(self.app, "Kein Empfänger ausgewählt")
                return
            if client.send_user_message(uid, msg):
                self._append_own(f"An {sel_name}: {msg}")
            else:
                announce(self.app, "Nachricht konnte nicht gesendet werden")
        else:
            channel_id = client.get_my_channel_id()
            if not channel_id:
                announce(self.app, "Nicht in einem Kanal")
                return
            if client.send_channel_message(channel_id, msg):
                self._append_own(f"Ich: {msg}")
            else:
                announce(self.app, "Nachricht konnte nicht gesendet werden")

        self.msg_input.value = ""

    def _append_own(self, text: str) -> None:
        """Eigene gesendete Nachricht in den Verlauf einfügen."""
        def update() -> None:
            current = self.chat_log.value or ""
            self.chat_log.value = (current + "\n" if current else "") + text

        self.app.loop.call_soon_threadsafe(update)

    def _on_export(self, widget) -> None:
        """Chatverlauf in Zwischenablage kopieren (auf Android kein Dateisystem-Picker)."""
        content = self.chat_log.value or ""
        if not content.strip():
            announce(self.app, "Kein Chatverlauf zum Exportieren")
            return
        # Zwischenablage ist der praktikabelste Weg auf Android
        try:
            import toga
            self.app.clipboard.content = content
            announce(self.app, "Chatverlauf in Zwischenablage kopiert")
        except Exception:
            announce(self.app, "Export nicht verfügbar")

    def _on_clear(self, widget) -> None:
        self.chat_log.value = ""
        self._search_hits = []
        announce(self.app, "Chatverlauf geleert")

    def _on_search(self, widget) -> None:
        query = (self.search_input.value or "").strip().lower()
        if not query:
            announce(self.app, "Bitte Suchbegriff eingeben")
            return
        text = self.chat_log.value or ""
        lines = text.splitlines()
        hits = [line for line in lines if query in line.lower()]
        self._search_hits = hits
        if hits:
            anzahl = len(hits)
            announce(self.app, f"{anzahl} Treffer gefunden: {hits[0]}")
        else:
            announce(self.app, "Keine Treffer gefunden")

    # ------------------------------------------------------------------
    # Öffentliche Hilfsmethode für andere Tabs / App-Logik
    # ------------------------------------------------------------------

    def append_system(self, text: str) -> None:
        """System-Nachricht einfügen (z. B. Verbindungshinweise)."""
        label = f"* {text}"

        def update() -> None:
            current = self.chat_log.value or ""
            self.chat_log.value = (current + "\n" if current else "") + label

        self.app.loop.call_soon_threadsafe(update)
