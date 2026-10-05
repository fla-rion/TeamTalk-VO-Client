from __future__ import annotations

import html
import re
import threading
import time
from typing import TYPE_CHECKING, List, Optional, Set

from i18n import _, current_language

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QCheckBox, QComboBox, QTextEdit, QLineEdit,
    QPushButton, QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QEvent, QObject
from PySide6.QtGui import QAction, QKeySequence, QShortcut

from ui.chat_helpers import ChatEntry, ChatEntryIndex, apply_reply_prefix, make_reply_prefix

if TYPE_CHECKING:
    from app_qt import MainWindow

_MD_PATTERNS = [
    (re.compile(r'\*\*(.+?)\*\*'), r'\1'),
    (re.compile(r'\*(.+?)\*'),     r'\1'),
    (re.compile(r'`(.+?)`'),       r'\1'),
]

_EMOJI_SHORTCODES = {
    ":+1:": "👍", ":-1:": "👎", ":smile:": "😊", ":laughing:": "😂",
    ":wink:": "😉", ":heart:": "❤️", ":fire:": "🔥", ":wave:": "👋",
    ":ok:": "✅", ":x:": "❌", ":warning:": "⚠️", ":info:": "ℹ️",
    ":mic:": "🎤", ":headphones:": "🎧", ":speaker:": "🔊",
    ":mute:": "🔇", ":clap:": "👏", ":star:": "⭐", ":check:": "✔️",
    ":question:": "❓", ":exclamation:": "❗", ":tada:": "🎉", ":eyes:": "👀",
}


def _strip_markdown(text: str) -> str:
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def expand_emoji_shortcodes(text: str) -> str:
    for code, emoji in _EMOJI_SHORTCODES.items():
        text = text.replace(code, emoji)
    return text


class ChatTab(QWidget):
    """Tab 3: Chat."""

    def __init__(self, parent: QWidget, window: "MainWindow") -> None:
        super().__init__(parent)
        self.window = window
        self._search_positions: List[int] = []
        self._private_user_ids: List[int] = []
        # Parallele Metadaten zu den Zeilen im Chatverlauf (für "Antworten")
        self._entries = ChatEntryIndex()
        self._reply_prefix = ""
        # Tipp-Anzeige: an wen ich gerade tippe / wer mir gerade tippt
        self._typing_target: int = 0
        self._remote_typing_ids: Set[int] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # --- Search bar at top ---
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(_("Suchen:")))
        self.search_input = QLineEdit()
        self.search_input.setAccessibleName(_("Verlauf durchsuchen"))
        self.search_input.setPlaceholderText(_("Im Verlauf suchen …"))
        self.search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self.search_input, 1)
        self.search_btn = QPushButton(_("&Suchen"))
        self.search_btn.clicked.connect(self._on_search)
        search_row.addWidget(self.search_btn)
        self.search_count = QLabel(_("0 Treffer"))
        self.search_count.setAccessibleName(_("Suchergebnis"))
        search_row.addWidget(self.search_count)
        root.addLayout(search_row)

        # --- Chat target group ---
        target_group = QGroupBox(_("Chat-Ziel"))
        target_layout = QVBoxLayout(target_group)
        self.chat_target = QLabel(_("Ziel: (kein)"))
        self.chat_target.setAccessibleName(_("Chat-Ziel"))
        target_layout.addWidget(self.chat_target)

        target_row = QHBoxLayout()
        self.private_chat = QCheckBox(_("&Privat"))
        self.private_chat.setAccessibleName(_("Privat senden"))
        self.private_chat.stateChanged.connect(lambda _: self.update_chat_target())
        lbl_private = QLabel(_("Privat an:"))
        self.private_user = QComboBox()
        self.private_user.setAccessibleName(_("Privat an"))
        self.private_user.currentIndexChanged.connect(self._on_private_user_changed)
        target_row.addWidget(self.private_chat)
        target_row.addWidget(lbl_private)
        target_row.addWidget(self.private_user, 1)
        target_layout.addLayout(target_row)
        root.addWidget(target_group)

        # --- Chat log ---
        root.addWidget(QLabel(_("Chatverlauf")))
        self.chat_log = QTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setAccessibleName(_("Chatverlauf"))
        self.chat_log.setAccessibleDescription(
            _(
                "Lese-only Bereich. Strg+C kopiert markierten Text. "
                "F6 wechselt zur Eingabe."
            )
        )
        self.chat_log.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_log.customContextMenuRequested.connect(self._on_log_context_menu)
        # Strg+R im Verlauf = Antworten (hat dort Vorrang vor "Nickname ändern")
        self.chat_log.installEventFilter(self)
        root.addWidget(self.chat_log, 1)

        # --- History action buttons ---
        history_row = QHBoxLayout()
        self.export_btn = QPushButton(_("Verlauf &exportieren"))
        self.export_btn.clicked.connect(self._on_export_history)
        self.export_html_btn = QPushButton(_("Als &HTML"))
        self.export_html_btn.clicked.connect(self._on_export_html)
        self.clear_btn = QPushButton(_("Verlauf &leeren"))
        self.clear_btn.clicked.connect(self._on_clear_history)
        self.reply_btn = QPushButton(_("&Antworten"))
        self.reply_btn.setAccessibleName(_("Auf Nachricht antworten"))
        self.reply_btn.clicked.connect(lambda: self._on_reply())
        self.quote_btn = QPushButton(_("&Zitieren"))
        self.quote_btn.clicked.connect(self._on_quote)
        self.copy_btn = QPushButton(_("&Kopieren"))
        self.copy_btn.clicked.connect(self._on_copy)
        self.save_msg_btn = QPushButton(_("&Speichern"))
        self.save_msg_btn.clicked.connect(self._on_save_msg)
        for btn in (self.export_btn, self.export_html_btn, self.clear_btn,
                    self.reply_btn, self.quote_btn, self.copy_btn, self.save_msg_btn):
            history_row.addWidget(btn)
        history_row.addStretch()
        root.addLayout(history_row)

        # --- Message input ---
        root.addWidget(QLabel(_("Nachricht")))
        self.chat_input = QLineEdit()
        self.chat_input.setAccessibleName(_("Nachricht eingeben"))
        self.chat_input.setAccessibleDescription(
            _(
                "Nachricht tippen und Enter drücken oder Senden klicken. "
                "F6 springt zum Chatverlauf."
            )
        )
        self.chat_input.setPlaceholderText(_("Nachricht eingeben …"))
        self.chat_input.returnPressed.connect(self._on_send)
        root.addWidget(self.chat_input)

        # F6 toggles focus between chat log and input
        f6 = QShortcut(QKeySequence("F6"), self)
        f6.activated.connect(self._toggle_focus)

        send_row = QHBoxLayout()
        self.send_btn = QPushButton(_("&Senden"))
        self.send_btn.setAccessibleName(_("Nachricht senden"))
        self.send_btn.clicked.connect(self._on_send)
        self.improve_btn = QPushButton(_("&Verbessern"))
        self.improve_btn.setAccessibleName(_("Text verbessern"))
        self.improve_btn.clicked.connect(self._on_improve_text)
        self.char_count_label = QLabel(_("0 Zeichen"))
        self.char_count_label.setAccessibleName(_("Zeichenanzahl"))
        send_row.addWidget(self.send_btn)
        send_row.addWidget(self.improve_btn)
        send_row.addWidget(self.char_count_label)
        send_row.addStretch()
        root.addLayout(send_row)
        self.chat_input.textChanged.connect(self._on_input_changed)

        # Ctrl+C shortcut to copy selected text from chat log
        copy_sc = QShortcut(QKeySequence("Ctrl+C"), self.chat_log)
        copy_sc.activated.connect(self._on_copy)

    # ------------------------------------------------------------------
    # Input helpers
    # ------------------------------------------------------------------

    def _toggle_focus(self) -> None:
        if self.chat_input.hasFocus():
            self.chat_log.setFocus()
        else:
            self.chat_input.setFocus()

    def _on_input_changed(self, text: str) -> None:
        self.char_count_label.setText(_("{} Zeichen").format(len(text)))
        try:
            if not self.window.client.is_connected():
                return
        except Exception:
            return
        target = self._sync_typing_target()
        if target:
            self.window._typing_sender.text_changed(target, text)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.chat_log and event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            if (event.key() == Qt.Key.Key_R
                    and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
                if event.type() == QEvent.Type.ShortcutOverride:
                    event.accept()
                    return True
                self._on_reply()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Chat target
    # ------------------------------------------------------------------

    def _on_private_user_changed(self, _idx: int) -> None:
        self.update_chat_target()

    def update_chat_target(self) -> None:
        if hasattr(self.window, "_typing_sender"):
            self._sync_typing_target()
        is_private = self.private_chat.isChecked()
        if is_private:
            idx = self.private_user.currentIndex()
            if idx >= 0 and idx < len(self._private_user_ids):
                name = self.private_user.currentText()
                label = _("Ziel: {} (privat)").format(name)
                if self._private_user_ids[idx] in self._remote_typing_ids:
                    label += _(" – schreibt …")
                self.chat_target.setText(label)
            else:
                self.chat_target.setText(_("Ziel: (kein Nutzer)"))
        else:
            ch_name = getattr(self.window, "_current_channel_name", _("(kein Kanal)"))
            self.chat_target.setText(_("Ziel: {} (Kanal)").format(ch_name))

    def refresh_private_user_choice(self, users) -> None:
        current_id = (
            self._private_user_ids[self.private_user.currentIndex()]
            if self._private_user_ids and self.private_user.currentIndex() >= 0
            else None
        )
        self.private_user.blockSignals(True)
        self.private_user.clear()
        self._private_user_ids = []
        tt_str = self.window.tt_str
        items = []
        for u in users:
            try:
                uid = int(u.nUserID)
                my_id = self.window.client.get_my_user_id()
                if uid == my_id:
                    continue
                nickname = tt_str(u.szNickname)
                username = tt_str(u.szUsername)
                name = nickname or username or f"User#{uid}"
                if nickname and username and nickname != username:
                    name = f"{nickname} ({username})"
                items.append((name, uid))
            except Exception:
                pass
        items.sort(key=lambda x: x[0].lower())
        for name, uid in items:
            self.private_user.addItem(name)
            self._private_user_ids.append(uid)
        if current_id and current_id in self._private_user_ids:
            self.private_user.setCurrentIndex(self._private_user_ids.index(current_id))
        self.private_user.blockSignals(False)
        self.update_chat_target()

    def select_private_recipient(self, user_id: int) -> None:
        """Select a user in the private chat combo (for reply hotkey)."""
        if user_id in self._private_user_ids:
            self.private_chat.setChecked(True)
            self.private_user.setCurrentIndex(self._private_user_ids.index(user_id))
            self.update_chat_target()

    # ------------------------------------------------------------------
    # Tipp-Anzeige bei Privatnachrichten
    # ------------------------------------------------------------------

    def _current_private_target(self) -> int:
        if not self.private_chat.isChecked():
            return 0
        idx = self.private_user.currentIndex()
        if 0 <= idx < len(self._private_user_ids):
            return int(self._private_user_ids[idx])
        return 0

    def _sync_typing_target(self) -> int:
        """Beendet das Tipp-Signal an ein altes Ziel, wenn das Ziel wechselt."""
        target = self._current_private_target()
        if self._typing_target and self._typing_target != target:
            self.window._typing_sender.stop(self._typing_target)
        self._typing_target = target
        return target

    def set_remote_typing(self, user_id: int, active: bool) -> None:
        if active:
            self._remote_typing_ids.add(user_id)
        else:
            self._remote_typing_ids.discard(user_id)
        if user_id == self._current_private_target():
            self.update_chat_target()

    def clear_remote_typing(self) -> None:
        self._remote_typing_ids.clear()
        self._typing_target = 0
        self.update_chat_target()

    # ------------------------------------------------------------------
    # Antworten auf eine Nachricht aus dem Verlauf (Strg+R)
    # ------------------------------------------------------------------

    def _record_entry(self, kind: str, sender: str, content: str, private: bool,
                      sender_id: int, reply_user_id: int) -> None:
        block = self.chat_log.document().lastBlock()
        start = block.position()
        self._entries.add(ChatEntry(
            start=start,
            end=start + max(0, block.length() - 1),
            kind=kind,
            sender=sender,
            content=content,
            reply_user_id=reply_user_id,
            private=private,
            sender_id=sender_id,
        ))

    def _on_log_context_menu(self, pos) -> None:
        self.chat_log.setTextCursor(self.chat_log.cursorForPosition(pos))
        menu = self.chat_log.createStandardContextMenu(pos)
        first = menu.actions()[0] if menu.actions() else None
        reply_act = QAction(_("&Antworten") + "\tCtrl+R", menu)
        reply_act.setEnabled(len(self._entries) > 0)
        reply_act.triggered.connect(lambda: self._on_reply())
        if first is not None:
            menu.insertAction(first, reply_act)
            menu.insertSeparator(first)
        else:
            menu.addAction(reply_act)
        menu.exec(self.chat_log.viewport().mapToGlobal(pos))
        menu.deleteLater()

    def _entry_display_name(self, entry: ChatEntry) -> str:
        if entry.sender_id:
            try:
                u = self.window.client.get_user(entry.sender_id)
                if u:
                    nick = self.window.tt_str(u.szNickname)
                    if nick:
                        return nick
            except Exception:
                pass
        return entry.sender or _("Unbekannt")

    def _announce(self, text: str) -> None:
        try:
            self.window._sr_announce(text)
        except Exception:
            pass

    def _on_reply(self, pos: Optional[int] = None) -> None:
        """Antwortet auf die Nachricht an der Cursorposition im Verlauf.

        Kanal-/Rundnachricht → Kanal-Chat mit Präfix "> Absender: Inhalt | "
        (Format des offiziellen Clients); Privatnachricht → Privat-Chat mit dem
        Gesprächspartner. Steht der Cursor auf keiner Nachricht, gilt die neueste.
        """
        if pos is None:
            pos = self.chat_log.textCursor().position()
        entry = self._entries.at(pos) or self._entries.last()
        if entry is None:
            self.window.set_status(_("Keine Nachricht zum Antworten"))
            self._announce(_("Keine Nachricht zum Antworten"))
            return
        sender = self._entry_display_name(entry)
        if entry.private and entry.reply_user_id:
            if entry.reply_user_id not in self._private_user_ids:
                msg = _("Privat-Antwort nicht möglich: Benutzer ist nicht mehr online")
                self.window.set_status(msg)
                self._announce(msg)
                return
            self.select_private_recipient(entry.reply_user_id)
            announce = _("Privat-Antwort an {}").format(self.private_user.currentText())
        else:
            if self.private_chat.isChecked():
                self.private_chat.setChecked(False)
            announce = _("Antwort an {}").format(sender)
        prefix = make_reply_prefix(sender, entry.content)
        new_text = apply_reply_prefix(self.chat_input.text(), self._reply_prefix, prefix)
        self._reply_prefix = prefix
        self.chat_input.setText(new_text)
        self.chat_input.setFocus()
        self.chat_input.setCursorPosition(len(new_text))
        self._announce(announce)

    # ------------------------------------------------------------------
    # Message display
    # ------------------------------------------------------------------

    def append_message(self, sender: str, text: str, ts: str = "", private: bool = False,
                       own: bool = False, kind: str = "channel", sender_id: int = 0,
                       reply_user_id: int = 0) -> None:
        """Append a formatted chat message with timestamp to the log."""
        text = expand_emoji_shortcodes(_strip_markdown(text))
        ts_str = ts or time.strftime("%H:%M:%S")
        prefix = _("[Privat] ") if private else ""
        line = f"[{ts_str}] {prefix}{sender}: {text}"

        # Color by message kind
        if own:
            color = "#27ae60"
        elif private:
            color = "#2980b9"
        elif kind == "system":
            color = "#888888"
        else:
            color = "#000000"

        self.chat_log.append(
            f'<span style="color:{color}">{html.escape(line)}</span>'
        )
        if kind != "system":
            self._record_entry(kind, sender, str(text or ""), private, sender_id, reply_user_id)

        # Persist to chat history if available
        try:
            key = getattr(self.window, "_current_server_key", "")
            if key and hasattr(self.window, "_chat_history"):
                self.window._chat_history.append(key, line, kind)
        except Exception:
            pass

    def append_system_message(self, text: str, ts: str = "") -> None:
        ts_str = ts or time.strftime("%H:%M:%S")
        line = f"[{ts_str}] *** {text}"
        self.chat_log.append(
            f'<span style="color:#888888">{html.escape(line)}</span>'
        )

    # alias used by some callers
    def append_chat(self, text: str, kind: str = "chat", speak: bool = True) -> None:
        """wx-compat alias: appends a pre-formatted line to the chat log."""
        if getattr(self.window.settings_store.settings, "chat_relative_timestamps", False):
            ts_str = _("gerade eben")
        elif getattr(self.window.settings_store.settings, "chat_show_timestamps", True):
            ts_str = time.strftime("%H:%M")
        else:
            ts_str = time.strftime("%H:%M")
        color_map = {
            "system": "#888888",
            "broadcast": "#8B4513",
            "private": "#2980b9",
            "own": "#27ae60",
        }
        color = color_map.get(kind, "#000000")
        line = f"[{ts_str}] {text}"
        self.chat_log.append(
            f'<span style="color:{color}">{html.escape(line)}</span>'
        )
        if speak:
            try:
                self.window.tts.speak(text, kind=kind)
            except Exception:
                pass
        try:
            key = getattr(self.window, "_current_server_key", "")
            if key and hasattr(self.window, "_chat_history"):
                self.window._chat_history.append(key, line, kind)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Improve text
    # ------------------------------------------------------------------

    def _on_improve_text(self) -> None:
        """Verbessert den aktuellen Eingabetext via KI."""
        text = self.chat_input.text()
        if not text.strip():
            return
        self.improve_btn.setEnabled(False)

        def _worker():
            try:
                result = self.window._ai_reply.improve_text(text)
            except Exception:
                result = None

            def _done():
                self.improve_btn.setEnabled(True)
                if result:
                    self.chat_input.setText(result)
                    self.chat_input.setCursorPosition(len(result))
                    try:
                        self.window._sr_announce(_("Text verbessert"))
                    except Exception:
                        pass

            QTimer.singleShot(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        text = expand_emoji_shortcodes(text)
        is_private = self.private_chat.isChecked()
        target_id = 0
        if is_private and self._private_user_ids:
            idx = self.private_user.currentIndex()
            if 0 <= idx < len(self._private_user_ids):
                target_id = self._private_user_ids[idx]
        self.window.send_chat_message(text, private=is_private, target_id=target_id)
        self._reply_prefix = ""
        self.chat_input.clear()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        """Search the chat history and highlight matches."""
        query = self.search_input.text().strip().lower()
        self._search_positions = []
        if not query:
            self.search_count.setText(_("0 Treffer"))
            return
        text = self.chat_log.toPlainText()
        lines = text.split("\n")
        hits = []
        pos = 0
        for line in lines:
            if query in line.lower():
                hits.append((line, pos))
            pos += len(line) + 1
        total = len(hits)
        shown = min(total, 100)
        self._search_positions = [p for _, p in hits[:shown]]
        label = (
            _("{} Treffer").format(total) if total <= shown
            else _("{} Treffer (zeige {})").format(total, shown)
        )
        self.search_count.setText(label)
        # Scroll to first hit
        if self._search_positions:
            cursor = self.chat_log.textCursor()
            cursor.setPosition(self._search_positions[0])
            self.chat_log.setTextCursor(cursor)
            self.chat_log.ensureCursorVisible()
        try:
            self.window._sr_announce(label)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # History buttons
    # ------------------------------------------------------------------

    def _on_export_history(self) -> None:
        content = self.chat_log.toPlainText()
        if not content.strip():
            self.window.set_status(_("Kein Chat-Verlauf zum Exportieren"))
            return
        default_name = f"chatverlauf_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _fmt = QFileDialog.getSaveFileName(
            self, _("Chatverlauf exportieren"), default_name,
            _("Textdateien (*.txt);;Alle Dateien (*.*)")
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.window.set_status(_("Verlauf exportiert: {}").format(path))
            except Exception as exc:
                self.window.set_status(_("Export fehlgeschlagen: {}").format(exc))

    def _on_export_html(self) -> None:
        content = self.chat_log.toPlainText()
        if not content.strip():
            self.window.set_status(_("Kein Chat-Verlauf zum Exportieren"))
            return
        server_name = getattr(self.window, "_current_server_key", "TeamTalk")
        default_name = f"chatverlauf_{time.strftime('%Y%m%d_%H%M%S')}.html"
        path, _fmt = QFileDialog.getSaveFileName(
            self, _("Chatverlauf als HTML"), default_name,
            _("HTML-Dateien (*.html);;Alle Dateien (*.*)")
        )
        if path:
            try:
                lines = content.splitlines()
                rows = []
                for line in lines:
                    if not line.strip():
                        continue
                    escaped = html.escape(line)
                    if line.startswith("Ich:") or line.startswith("An "):
                        css_class = "own"
                    elif "[Privat]" in line[:30]:
                        css_class = "private"
                    elif line.startswith("***") or line.startswith("["):
                        css_class = "system"
                    else:
                        css_class = "chat"
                    rows.append(f'<div class="{css_class}">{escaped}</div>')
                html_lang = current_language() or "de"
                title_text = _("Chat-Verlauf – {}").format(html.escape(server_name))
                exported_text = _("Exportiert: {}").format(time.strftime("%Y-%m-%d %H:%M:%S"))
                html_content = (
                    f'<!DOCTYPE html><html lang="{html_lang}"><head>'
                    f'<meta charset="UTF-8"><title>{title_text}</title>'
                    f'<style>'
                    f'body{{font-family:monospace;max-width:900px;margin:1em auto;background:#fafafa;padding:0 1em}}'
                    f'.chat{{color:#222;margin:.15em 0}}.own{{color:#27ae60}}.private{{color:#2980b9}}'
                    f'.system{{color:#888;font-style:italic}}'
                    f'h1{{font-size:1.1em;color:#555}}'
                    f'</style></head><body>'
                    f'<h1>{title_text} – {exported_text}</h1>'
                    + "".join(rows)
                    + "</body></html>"
                )
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                self.window.set_status(_("HTML exportiert: {}").format(path))
            except Exception as exc:
                self.window.set_status(_("HTML-Export fehlgeschlagen: {}").format(exc))

    def _on_clear_history(self) -> None:
        reply = QMessageBox.question(
            self, _("Verlauf leeren"),
            _("Chat-Verlauf wirklich leeren?\n\nDies löscht den angezeigten Verlauf."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.chat_log.clear()
            self._entries.clear()
            # Also clear persisted history if available
            try:
                key = getattr(self.window, "_current_server_key", "")
                if key and hasattr(self.window, "_chat_history"):
                    self.window._chat_history.clear(key)
            except Exception:
                pass
            self.window.set_status(_("Chat-Verlauf geleert"))

    def _on_quote(self) -> None:
        selected = self.chat_log.textCursor().selectedText().strip()
        if not selected:
            # Fallback: last non-empty line
            full = self.chat_log.toPlainText()
            lines = [l for l in full.splitlines() if l.strip()]
            selected = lines[-1] if lines else ""
        if not selected:
            self.window.set_status(_("Kein Text zum Zitieren"))
            return
        quoted = "\n".join(f"> {line}" for line in selected.splitlines())
        current = self.chat_input.text()
        if current:
            self.chat_input.setText(quoted + "\n" + current)
        else:
            self.chat_input.setText(quoted + "\n")
        self.chat_input.setFocus()

    def _on_copy(self) -> None:
        """Copy selected text from the chat log to clipboard."""
        cursor = self.chat_log.textCursor()
        if cursor.hasSelection():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(cursor.selectedText())
        else:
            self.window.set_status(_("Kein Text ausgewählt"))

    def _on_save_msg(self) -> None:
        selected = self.chat_log.textCursor().selectedText().strip()
        if not selected:
            full = self.chat_log.toPlainText()
            lines = [l for l in full.splitlines() if l.strip()]
            selected = lines[-1] if lines else ""
        if not selected:
            self.window.set_status(_("Kein Text zum Speichern"))
            return
        try:
            self.window.save_message(selected)
        except Exception as exc:
            self.window.set_status(_("Speichern fehlgeschlagen: {}").format(exc))
