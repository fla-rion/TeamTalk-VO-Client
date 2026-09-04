"""Tab 2: Kanäle – flache DetailedList mit Kanal/Nutzer-Einträgen.

Analog zu src/ui_wx/tabs/channels.py, aber für Android (Toga/BeeWare).
Kanaltiefe wird durch Leerzeichen-Einrückung dargestellt (gut für Braillezeile).
Tippen auf Kanal → Kanal beitreten. Tippen auf Nutzer → Kontextmenü.
TalkBack: Kanalzeile sagt "Kanal: Name, X Nutzer"; Nutzerzeile sagt "Nutzer: Name".
Die Liste ist Live Region: neue Nutzer werden automatisch angesagt.
Thread-Safety: alle UI-Updates aus Background-Threads via app.loop.call_soon_threadsafe().
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import (
    set_description,
    set_live_region,
    make_button_accessible,
    announce_event,
    LIVE_POLITE,
)

_NODE_CHANNEL = "channel"
_NODE_USER = "user"


class ChannelsTab(toga.Box):
    """Tab 2: Kanäle – flache DetailedList, TalkBack-zugänglich."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=4))
        self.app = app
        # Flache Liste: [(node_type, node_id, label), ...]
        self._items: List[Tuple[str, int, str]] = []
        self._all_users: List = []
        self._current_users: List = []
        self._selected_channel_id: Optional[int] = None
        self._selected_user_id: Optional[int] = None
        # Diff-Cache: verhindert vollständiges Neuaufbauen bei kleinen Änderungen
        self._displayed_labels: List[str] = []
        self._build_ui()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # --- Suchfeld ---
        search_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        search_label = toga.Label("Suche:", style=Pack(padding_right=8))
        self.search = toga.TextInput(
            placeholder="Kanal suchen...",
            on_change=self._on_search,
            style=Pack(flex=1),
        )
        set_description(self.search, "Kanal suchen")
        search_row.add(search_label)
        search_row.add(self.search)
        self.add(search_row)

        # --- Kanal/Nutzer-Liste ---
        self.channel_list = toga.DetailedList(
            data=[],
            on_select=self._on_list_select,
            style=Pack(flex=1),
        )
        set_description(self.channel_list, "Kanalliste")
        # Live Region: TalkBack sagt neue Nutzer an ohne Fokus-Verlust
        set_live_region(self.channel_list, LIVE_POLITE)
        self.add(self.channel_list)

        # --- Aktionsbuttons ---
        btn_row = toga.Box(style=Pack(direction=ROW, padding_top=4))

        self.join_btn = toga.Button(
            "Kanal beitreten",
            on_press=self._on_join_btn,
            style=Pack(padding_right=4),
        )
        make_button_accessible(
            self.join_btn,
            "Kanal beitreten",
            hint="Tritt dem ausgewählten Kanal bei",
        )
        btn_row.add(self.join_btn)

        self.user_action_btn = toga.Button(
            "Nutzer-Aktionen",
            on_press=self._on_user_action_btn,
            style=Pack(padding_right=4),
        )
        make_button_accessible(
            self.user_action_btn,
            "Nutzer-Aktionen",
            hint="Öffnet Aktionsmenü für den ausgewählten Nutzer",
        )
        btn_row.add(self.user_action_btn)

        self.add(btn_row)

    # ------------------------------------------------------------------
    # EventBus-Abonnements
    # ------------------------------------------------------------------

    def _subscribe_events(self) -> None:
        bus = getattr(self.app, "bus", None)
        if bus is None:
            return
        bus.on("user_joined", self._on_user_joined)
        bus.on("user_left", self._on_user_left)
        bus.on("channel_list_updated", self._on_channel_list_updated)
        bus.on("connected", self._on_connected)
        bus.on("disconnected", self._on_disconnected)

    # ------------------------------------------------------------------
    # Kanalliste aufbauen
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Kanalliste vollständig neu aufbauen (aus app.client)."""
        client = getattr(self.app, "client", None)
        if client is None:
            return

        try:
            channels = list(client.get_server_channels() or [])
        except Exception:
            channels = []

        try:
            all_users = list(client.get_server_users() or [])
        except Exception:
            all_users = []
        self._all_users = all_users

        users_by_channel: Dict[int, List] = {}
        for u in all_users:
            try:
                cid = int(u.nChannelID)
                users_by_channel.setdefault(cid, []).append(u)
            except Exception:
                pass

        if not channels:
            self._items = []
            self._apply_data([])
            return

        # Root-Kanal ermitteln
        try:
            root_id = int(client.get_root_channel_id() or 0)
        except Exception:
            root_id = 0
        channel_ids = {c.nChannelID for c in channels}
        parent_ids = {c.nParentID for c in channels}
        if root_id <= 0 or root_id not in channel_ids:
            if 1 in parent_ids:
                root_id = 1
            elif parent_ids:
                root_id = min(parent_ids - {0})

        # Servernamen für Root-Kanal
        try:
            server_props = client.get_server_properties()
            server_name = self._tt_str(server_props.szServerName)
        except Exception:
            server_name = ""
        channels_by_id = {c.nChannelID: c for c in channels}
        if not server_name:
            root_ch = channels_by_id.get(root_id)
            server_name = self._tt_str(root_ch.szName) if root_ch else "Server"

        # Flache Liste per DFS aufbauen
        labels, items = self._build_flat_list(
            root_id, server_name, channels_by_id, users_by_channel
        )

        self._items = items
        self._apply_data(labels)
        self._update_list_descriptions()

        # Eigenen Kanal merken
        try:
            my_ch = int(client.get_my_channel_id() or 0)
            if my_ch:
                self._selected_channel_id = my_ch
                self._current_users = users_by_channel.get(my_ch, [])
        except Exception:
            pass

    def _build_flat_list(
        self,
        root_id: int,
        server_name: str,
        channels_by_id: Dict[int, object],
        users_by_channel: Dict[int, List],
    ) -> Tuple[List[str], List[Tuple[str, int, str]]]:
        labels: List[str] = []
        items: List[Tuple[str, int, str]] = []

        def visit(chan_id: int, depth: int) -> None:
            indent = "  " * depth
            chan = channels_by_id.get(chan_id)
            name = server_name if chan_id == root_id else (
                self._tt_str(chan.szName) if chan else str(chan_id)
            )
            users = users_by_channel.get(chan_id, [])
            total = self._count_total_users(chan_id, users_by_channel, channels_by_id)
            channel_label = indent + self._make_channel_label(name, chan if chan_id != root_id else None, users, total)
            labels.append(channel_label)
            items.append((_NODE_CHANNEL, chan_id, channel_label))

            # Nutzer alphabetisch
            for user in sorted(users, key=lambda u: (self._tt_str(u.szNickname) or "").lower()):
                user_indent = "  " * (depth + 1)
                user_label = user_indent + self._format_user_label(user)
                labels.append(user_label)
                items.append((_NODE_USER, int(user.nUserID), user_label))

            # Unterkanäle alphabetisch
            children = sorted(
                [c for c in channels_by_id.values() if c.nParentID == chan_id],
                key=lambda c: (self._tt_str(c.szName) or "").lower(),
            )
            for child in children:
                visit(child.nChannelID, depth + 1)

        visit(root_id, 0)
        return labels, items

    def _count_total_users(
        self,
        chan_id: int,
        users_by_channel: Dict,
        channels_by_id: Dict,
    ) -> int:
        total = len(users_by_channel.get(chan_id, []))
        for child in channels_by_id.values():
            if int(child.nParentID) == chan_id:
                total += self._count_total_users(child.nChannelID, users_by_channel, channels_by_id)
        return total

    def _make_channel_label(self, name: str, chan, users: List, total: int = 0) -> str:
        n = len(users)
        has_pw = chan is not None and bool(getattr(chan, "bPassword", False))
        parts = [name]
        if has_pw:
            parts.append("Passwort")
        if total > n:
            parts.append(f"{n}/{total} Nutzer")
        elif n == 1:
            parts.append("1 Nutzer")
        elif n > 1:
            parts.append(f"{n} Nutzer")
        # Favoriten-Stern
        if chan is not None:
            ch_id = int(getattr(chan, "nChannelID", 0) or 0)
            try:
                favs = list(getattr(self.app.settings_store.settings, "channel_favorites", []) or [])
                if ch_id and ch_id in favs:
                    parts[0] = "★ " + parts[0]
            except Exception:
                pass
        return ", ".join(parts)

    def _format_user_label(self, user) -> str:
        try:
            name = self._tt_str(user.szNickname) or self._tt_str(user.szUsername) or "Benutzer"
        except Exception:
            name = "Benutzer"
        flags = []
        try:
            tt = self.app.client.tt
            if user.uUserType & tt.UserType.USERTYPE_ADMIN:
                flags.append("Admin")
        except Exception:
            pass
        try:
            tt = self.app.client.tt
            if user.uUserState & tt.UserState.USERSTATE_VOICE:
                flags.append("Spricht")
            elif user.uUserState & tt.UserState.USERSTATE_MUTE_VOICE:
                flags.append("Stumm")
        except Exception:
            pass
        return f"{name}, {', '.join(flags)}" if flags else name

    def _tt_str(self, raw) -> str:
        """Wandelt TeamTalk-String (ctypes-Array) in Python-str."""
        try:
            if hasattr(self.app, "tt_str"):
                return self.app.tt_str(raw) or ""
            if isinstance(raw, str):
                return raw
            return bytes(raw).rstrip(b"\x00").decode("utf-8", errors="replace")
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Liste anzeigen / filtern
    # ------------------------------------------------------------------

    def _apply_data(self, labels: List[str]) -> None:
        """Schreibt Labels in die DetailedList (im UI-Thread aufrufen)."""
        def _update():
            data = [{"title": lbl.strip(), "subtitle": ""} for lbl in labels]
            self.channel_list.data = data
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(_update)
        else:
            _update()

    def _update_list_descriptions(self) -> None:
        """Setzt TalkBack-Beschreibungen für alle Listenzeilen.

        Kanalzeilen: "Kanal: Name, X Nutzer"
        Nutzerzeilen: "Nutzer: Name"
        """
        def _update():
            try:
                native = self.channel_list._impl.native
                adapter = native.getAdapter()
                if adapter is None:
                    return
                for i, (node_type, node_id, label) in enumerate(self._items):
                    view = adapter.getView(i, None, native)
                    if view is None:
                        continue
                    stripped = label.strip()
                    if node_type == _NODE_CHANNEL:
                        description = f"Kanal: {stripped}"
                    else:
                        description = f"Nutzer: {stripped}"
                    view.setContentDescription(description)
            except Exception:
                pass
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(_update)
        else:
            _update()

    def _on_search(self, widget) -> None:
        search = (widget.value or "").strip().lower()
        if not search:
            labels = [label for _, _, label in self._items]
            self._apply_data(labels)
            return
        filtered_labels = [
            label for _, _, label in self._items
            if search in label.strip().lower()
        ]
        self._apply_data(filtered_labels)

    # ------------------------------------------------------------------
    # Listen-Events
    # ------------------------------------------------------------------

    def _on_list_select(self, widget, row) -> None:
        if row is None:
            return
        try:
            idx = self.channel_list.data.index(row)
            if idx >= len(self._items):
                return
            node_type, node_id, label = self._items[idx]
            if node_type == _NODE_CHANNEL:
                self._selected_channel_id = node_id
                self._selected_user_id = None
            elif node_type == _NODE_USER:
                self._selected_user_id = node_id
        except (ValueError, AttributeError):
            pass

    def _on_join_btn(self, widget) -> None:
        if self._selected_channel_id is None:
            announce_event(self.app, "Bitte zuerst einen Kanal auswählen")
            return
        channel_id = self._selected_channel_id

        def worker():
            try:
                self.app.client.join_channel(channel_id)
            except Exception as exc:
                announce_event(self.app, f"Kanal beitreten fehlgeschlagen: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_user_action_btn(self, widget) -> None:
        """Öffnet Nutzer-Aktionsmenü (Stummschalten, Volume, Stereo-Position)."""
        if self._selected_user_id is None:
            announce_event(self.app, "Bitte zuerst einen Nutzer auswählen")
            return
        user_id = self._selected_user_id
        user = self._find_user(user_id)
        if user is None:
            announce_event(self.app, "Nutzer nicht gefunden")
            return
        name = self._tt_str(user.szNickname) or self._tt_str(user.szUsername) or f"Nutzer {user_id}"
        # Toga hat keinen nativen Action-Sheet – einfache Sequenz von Buttons
        # als Dialog-Ersatz über announce + direkte Aktion möglich.
        # Hier wird die Privat-Nachricht als primäre Aktion angeboten.
        # Weitere Aktionen (Stummschalten, Volume) können via EventBus ausgelöst werden.
        bus = getattr(self.app, "bus", None)
        if bus is not None:
            bus.emit("open_private_chat_requested", user_id=user_id, user_name=name)
        announce_event(self.app, f"Aktionen für {name}")

    # ------------------------------------------------------------------
    # EventBus-Handler
    # ------------------------------------------------------------------

    def _on_user_joined(self, **kwargs) -> None:
        """Neuer Nutzer → TalkBack-Ansage + Liste aktualisieren."""
        user = kwargs.get("user")
        channel_id = kwargs.get("channel_id", 0)
        if user is not None:
            try:
                name = self._tt_str(user.szNickname) or self._tt_str(user.szUsername) or "Jemand"
            except Exception:
                name = "Jemand"
            announce_event(self.app, f"{name} hat den Kanal betreten")
        # Liste im UI-Thread aktualisieren
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(self.refresh)
        else:
            self.refresh()

    def _on_user_left(self, **kwargs) -> None:
        """Nutzer hat Kanal verlassen → TalkBack-Ansage + Liste aktualisieren."""
        user = kwargs.get("user")
        if user is not None:
            try:
                name = self._tt_str(user.szNickname) or self._tt_str(user.szUsername) or "Jemand"
            except Exception:
                name = "Jemand"
            announce_event(self.app, f"{name} hat den Kanal verlassen")
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(self.refresh)
        else:
            self.refresh()

    def _on_channel_list_updated(self, **kwargs) -> None:
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(self.refresh)
        else:
            self.refresh()

    def _on_connected(self, **kwargs) -> None:
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(self.refresh)
        else:
            self.refresh()

    def _on_disconnected(self, **kwargs) -> None:
        self._items = []
        self._all_users = []
        self._current_users = []
        self._selected_channel_id = None
        self._selected_user_id = None
        self._apply_data([])

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _find_user(self, user_id: int):
        for u in self._all_users:
            if int(u.nUserID) == user_id:
                return u
        for u in self._current_users:
            if int(u.nUserID) == user_id:
                return u
        try:
            return self.app.client.get_user(user_id)
        except Exception:
            return None

    def _find_item_index(self, node_type: str, node_id: int) -> int:
        for i, (t, n, _) in enumerate(self._items):
            if t == node_type and n == node_id:
                return i
        return -1

    def refresh_users_for_channel(self, channel_id: int) -> None:
        """Aktualisiert die Nutzerliste für einen bestimmten Kanal."""
        client = getattr(self.app, "client", None)
        if client is None:
            return
        actual = channel_id or int(client.get_my_channel_id() or 0)
        try:
            users = list(client.get_channel_users(actual))
            self._current_users = users
        except Exception:
            pass
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(self.refresh)
        else:
            self.refresh()
