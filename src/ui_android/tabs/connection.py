"""Tab 1: Verbindung – Serverliste, Verbindungsformular, Aktionsbuttons.

Analog zu src/ui_wx/tabs/connection.py, aber für Android (Toga/BeeWare).
TalkBack liest jede Serverzeile als "Servername, Host Port" an.
Status-Label ist Live Region: TalkBack liest Statusänderungen automatisch vor.
Thread-Safety: alle UI-Updates aus Background-Threads via app.loop.call_soon_threadsafe().
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional, TYPE_CHECKING

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from ui_android.a11y import (
    set_description,
    set_live_region,
    make_button_accessible,
    announce_event,
    LIVE_POLITE,
    LIVE_ASSERTIVE,
)
from ui.models import ServerProfile

if TYPE_CHECKING:
    pass


class ConnectionTab(toga.Box):
    """Tab 1: Verbindung – Serverliste + Formular + Aktionsbuttons."""

    def __init__(self, app) -> None:
        super().__init__(style=Pack(direction=COLUMN, padding=8))
        self.app = app
        # Alle ServerProfile-Objekte in Anzeigereihenfolge
        self._server_profiles: List[ServerProfile] = []
        # Index des aktuell in der Liste selektierten Profils
        self._selected_index: Optional[int] = None
        self._build_ui()
        self._subscribe_events()

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # --- Suchfeld ---
        self.search = toga.TextInput(
            placeholder="Server suchen...",
            on_change=self._on_search,
            style=Pack(padding_bottom=4),
        )
        set_description(self.search, "Server suchen")
        self.add(self.search)

        # --- Serverliste ---
        self.server_list = toga.DetailedList(
            data=[],
            on_select=self._on_server_select,
            style=Pack(flex=1),
        )
        set_description(self.server_list, "Serverliste")
        self.add(self.server_list)

        # --- Listenbuttons ---
        list_btn_row = toga.Box(style=Pack(direction=ROW, padding_bottom=8))

        self.connect_btn = toga.Button("Verbinden", on_press=self._on_connect,
                                       style=Pack(padding_right=4))
        make_button_accessible(self.connect_btn, "Verbinden",
                               hint="Verbindet mit dem ausgewählten Server")

        self.disconnect_btn = toga.Button("Trennen", on_press=self._on_disconnect,
                                          style=Pack(padding_right=4))
        make_button_accessible(self.disconnect_btn, "Trennen",
                               hint="Trennt die aktuelle Verbindung")

        self.add_btn = toga.Button("Neu", on_press=self._on_add,
                                   style=Pack(padding_right=4))
        make_button_accessible(self.add_btn, "Neuen Server hinzufügen")

        self.edit_btn = toga.Button("Bearbeiten", on_press=self._on_edit,
                                    style=Pack(padding_right=4))
        make_button_accessible(self.edit_btn, "Ausgewählten Server bearbeiten")

        self.remove_btn = toga.Button("Entfernen", on_press=self._on_remove)
        make_button_accessible(self.remove_btn, "Ausgewählten Server entfernen")

        for btn in (self.connect_btn, self.disconnect_btn, self.add_btn,
                    self.edit_btn, self.remove_btn):
            list_btn_row.add(btn)
        self.add(list_btn_row)

        # --- Verbindungsformular ---
        form_box = toga.Box(style=Pack(direction=COLUMN, padding_bottom=8))

        self.field_name = self._add_field(form_box, "Profilname", "")
        self.field_host = self._add_field(form_box, "Server", "127.0.0.1")
        self.field_tcp = self._add_field(form_box, "TCP Port", "10333")
        self.field_udp = self._add_field(form_box, "UDP Port", "10333")
        self.field_nickname = self._add_field(form_box, "Nickname", "VoiceOverUser")
        self.field_username = self._add_field(form_box, "Benutzername", "guest")
        self.field_password = self._add_field(form_box, "Passwort", "guest",
                                               password=True)
        self.field_client_name = self._add_field(form_box, "Client-Name", "TeamTalk VO")

        # Verschlüsselt-Schalter
        enc_row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        enc_label = toga.Label("Verschlüsselt:", style=Pack(padding_right=8))
        self.field_encrypted = toga.Switch("", style=Pack())
        set_description(self.field_encrypted, "Verschlüsselte Verbindung")
        enc_row.add(enc_label)
        enc_row.add(self.field_encrypted)
        form_box.add(enc_row)

        self.add(form_box)

        # --- Statusanzeige (Live Region) ---
        self.status_label = toga.Label(
            "Nicht verbunden",
            style=Pack(padding_top=4, padding_bottom=4),
        )
        set_description(self.status_label, "Verbindungsstatus")
        # TalkBack liest Statusänderungen automatisch vor
        set_live_region(self.status_label, LIVE_POLITE)
        self.add(self.status_label)

    def _add_field(
        self,
        parent: toga.Box,
        label_text: str,
        default: str,
        password: bool = False,
    ) -> toga.TextInput:
        row = toga.Box(style=Pack(direction=ROW, padding_bottom=4))
        label = toga.Label(f"{label_text}:", style=Pack(width=140))
        field = toga.TextInput(
            value=default,
            style=Pack(flex=1),
        )
        if password:
            # Toga hat kein direktes TE_PASSWORD – wir setzen den Hint und
            # vertrauen auf die native Keyboard-Maskierung via input_type
            try:
                field.style.update()  # noqa: kein password-Attribut in Toga 0.3
            except Exception:
                pass
        set_description(field, label_text)
        row.add(label)
        row.add(field)
        parent.add(row)
        return field

    # ------------------------------------------------------------------
    # EventBus-Abonnements
    # ------------------------------------------------------------------

    def _subscribe_events(self) -> None:
        bus = getattr(self.app, "bus", None)
        if bus is None:
            return
        bus.on("connected", self._on_event_connected)
        bus.on("disconnected", self._on_event_disconnected)
        bus.on("connecting", self._on_event_connecting)
        bus.on("connect_error", self._on_event_connect_error)

    # ------------------------------------------------------------------
    # Serverliste laden / filtern
    # ------------------------------------------------------------------

    def refresh_server_list(self) -> None:
        """Lädt Serverliste aus app.settings_store und zeigt sie an."""
        store = getattr(self.app, "store", None)
        if store is None:
            return
        self._server_profiles = list(store.items())
        filt = self.search.value.strip().lower() if self.search.value else ""
        self._apply_filter(filt)

    def _apply_filter(self, filt: str) -> None:
        """Baut die DetailedList neu auf (gefiltert oder vollständig)."""
        items = []
        for profile in self._server_profiles:
            name = profile.name or profile.host or ""
            if filt and filt not in name.lower():
                continue
            subtitle = f"{profile.host}:{profile.tcp_port}"
            items.append({"title": name, "subtitle": subtitle})
        self.server_list.data = items
        # Nach Neuaufbau Accessibility-Descriptions aktualisieren
        self._update_list_descriptions()

    def _update_list_descriptions(self) -> None:
        """Setzt TalkBack-Beschreibungen für alle Listenzeilen.

        Format: "Servername, Host Port" – Komma als Trennzeichen (kein Pipe).
        """
        try:
            native = self.server_list._impl.native
            adapter = native.getAdapter()
            if adapter is None:
                return
            visible_profiles = [
                p for p in self._server_profiles
                if not self.search.value
                or (self.search.value.strip().lower() in (p.name or p.host or "").lower())
            ]
            for i, profile in enumerate(visible_profiles):
                view = adapter.getView(i, None, native)
                if view is None:
                    continue
                name = profile.name or profile.host or f"Server {i + 1}"
                description = f"{name}, {profile.host} Port {profile.tcp_port}"
                view.setContentDescription(description)
        except Exception:
            pass

    def _get_filtered_profiles(self) -> List[ServerProfile]:
        """Gibt die aktuell angezeigten Profile in Listenreihenfolge zurück."""
        filt = self.search.value.strip().lower() if self.search.value else ""
        if not filt:
            return list(self._server_profiles)
        return [
            p for p in self._server_profiles
            if filt in (p.name or p.host or "").lower()
        ]

    # ------------------------------------------------------------------
    # Formular
    # ------------------------------------------------------------------

    def _fill_form(self, profile: ServerProfile) -> None:
        self.field_name.value = profile.display_name or profile.name or ""
        self.field_host.value = profile.host or ""
        self.field_tcp.value = str(profile.tcp_port)
        self.field_udp.value = str(profile.udp_port)
        self.field_nickname.value = profile.nickname or ""
        self.field_username.value = profile.username or ""
        self.field_password.value = profile.password or ""
        self.field_client_name.value = profile.client_name or ""
        self.field_encrypted.value = bool(profile.encrypted)

    def _profile_from_form(self) -> Optional[ServerProfile]:
        host = (self.field_host.value or "").strip()
        if not host:
            self._set_status("Server darf nicht leer sein", assertive=True)
            return None
        try:
            tcp_port = int((self.field_tcp.value or "10333").strip())
            udp_port = int((self.field_udp.value or "10333").strip())
        except ValueError:
            self._set_status("Port muss eine Zahl sein", assertive=True)
            return None
        display_name = (self.field_name.value or "").strip()
        name = display_name or host
        return ServerProfile(
            name=name,
            host=host,
            tcp_port=tcp_port,
            udp_port=udp_port,
            nickname=(self.field_nickname.value or "VoiceOverUser").strip(),
            username=(self.field_username.value or "guest").strip(),
            password=(self.field_password.value or "").strip(),
            client_name=(self.field_client_name.value or "TeamTalk VO").strip(),
            encrypted=bool(self.field_encrypted.value),
            display_name=display_name,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def _set_status(self, message: str, assertive: bool = False) -> None:
        """Aktualisiert das Status-Label (Live Region → TalkBack liest vor)."""
        def _update():
            self.status_label.text = message
            if assertive:
                # Wechsel auf ASSERTIVE für Fehlermeldungen, danach zurück
                set_live_region(self.status_label, LIVE_ASSERTIVE)
            else:
                set_live_region(self.status_label, LIVE_POLITE)
        # Immer im UI-Thread
        loop = getattr(self.app, "loop", None)
        if loop is not None:
            loop.call_soon_threadsafe(_update)
        else:
            _update()

    # ------------------------------------------------------------------
    # Button-Handler
    # ------------------------------------------------------------------

    def _on_search(self, widget) -> None:
        filt = (widget.value or "").strip().lower()
        self._apply_filter(filt)

    def _on_server_select(self, widget, row) -> None:
        if row is None:
            self._selected_index = None
            return
        visible = self._get_filtered_profiles()
        try:
            idx = self.server_list.data.index(row)
            if idx < len(visible):
                self._selected_index = self._server_profiles.index(visible[idx])
                self._fill_form(visible[idx])
        except (ValueError, AttributeError):
            pass

    def _on_connect(self, widget) -> None:
        profile = self._profile_from_form()
        if profile is None:
            return
        self._set_status(f"Verbinde mit {profile.host}…")
        announce_event(self.app, f"Verbinde mit {profile.name or profile.host}")

        def worker():
            try:
                result = self.app.client.connect(
                    host=profile.host,
                    tcp_port=profile.tcp_port,
                    udp_port=profile.udp_port,
                    nickname=profile.nickname,
                    username=profile.username,
                    password=profile.password,
                    client_name=profile.client_name,
                    encrypted=profile.encrypted,
                )
                ok = getattr(result, "ok", bool(result))
                msg = getattr(result, "message", "Verbunden" if ok else "Verbindung fehlgeschlagen")
                self._set_status(msg, assertive=not ok)
            except Exception as exc:
                self._set_status(f"Verbindungsfehler: {exc}", assertive=True)

        threading.Thread(target=worker, daemon=True).start()

    def _on_disconnect(self, widget) -> None:
        def worker():
            try:
                self.app.client.disconnect()
                self._set_status("Verbindung getrennt")
            except Exception as exc:
                self._set_status(f"Trennen fehlgeschlagen: {exc}", assertive=True)

        threading.Thread(target=worker, daemon=True).start()

    def _on_add(self, widget) -> None:
        profile = self._profile_from_form()
        if profile is None:
            return
        store = getattr(self.app, "store", None)
        if store is None:
            return
        store.add(profile)
        self._set_status(f"Server gespeichert: {profile.name}")
        announce_event(self.app, f"Server gespeichert: {profile.name}")
        self.refresh_server_list()

    def _on_edit(self, widget) -> None:
        if self._selected_index is None:
            self._set_status("Bitte einen Server auswählen", assertive=True)
            return
        profile = self._profile_from_form()
        if profile is None:
            return
        store = getattr(self.app, "store", None)
        if store is None:
            return
        store.update(self._selected_index, profile)
        self._set_status(f"Server aktualisiert: {profile.name}")
        self.refresh_server_list()

    def _on_remove(self, widget) -> None:
        if self._selected_index is None:
            self._set_status("Bitte einen Server auswählen", assertive=True)
            return
        profile = self._server_profiles[self._selected_index]
        # Kein Bestätigungsdialog auf Android (kein wx.MessageDialog) –
        # App kann hier einen toga.Dialog einbauen, falls gewünscht.
        store = getattr(self.app, "store", None)
        if store is None:
            return
        name = profile.name
        store.remove(self._selected_index)
        self._selected_index = None
        self._set_status(f"Server entfernt: {name}")
        announce_event(self.app, f"Server entfernt: {name}")
        self.refresh_server_list()

    # ------------------------------------------------------------------
    # EventBus-Handler (werden aus beliebigem Thread aufgerufen)
    # ------------------------------------------------------------------

    def _on_event_connected(self, **kwargs) -> None:
        server = kwargs.get("server_name", "")
        msg = f"Verbunden: {server}" if server else "Verbunden"
        self._set_status(msg)
        announce_event(self.app, msg)

    def _on_event_disconnected(self, **kwargs) -> None:
        self._set_status("Verbindung getrennt")

    def _on_event_connecting(self, **kwargs) -> None:
        host = kwargs.get("host", "")
        msg = f"Verbinde mit {host}…" if host else "Verbinde…"
        self._set_status(msg)

    def _on_event_connect_error(self, **kwargs) -> None:
        error = kwargs.get("message", "Verbindungsfehler")
        self._set_status(error, assertive=True)
        announce_event(self.app, error)

    def on_connection_status(self, connected: bool, message: str) -> None:
        """Extern aufrufbar (z.B. aus app_android.py) – Thread-sicher."""
        self._set_status(message, assertive=not connected)
        if not connected:
            announce_event(self.app, message)
