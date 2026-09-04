"""Briefcase/Toga-Einstiegspunkt für Android.

Startet die App als toga.App mit einem OptionContainer (Tabs).
Alle Tabs liegen in src/ui_android/tabs/.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from event_bus import EventBus
from ui.models import SettingsStore
from teamtalk_client_android import TeamTalkClientAndroid


class TeamTalkAndroid(toga.App):
    def startup(self) -> None:
        # Einstellungen laden (Android-Pfad: app_data)
        settings_path = self.paths.data / "settings.json"
        self.settings_store = SettingsStore(Path(settings_path))

        # TeamTalk-Client und EventBus initialisieren
        self.client: TeamTalkClientAndroid = TeamTalkClientAndroid()
        self.bus: EventBus = EventBus()

        # Event-Loop starten: SDK-Events → EventBus weiterleiten
        self.client.start_event_loop(self._on_tt_event)

        # Tabs importieren und aufbauen
        from ui_android.tabs.connection import ConnectionTab
        from ui_android.tabs.channels import ChannelsTab
        from ui_android.tabs.chat import ChatTab
        from ui_android.tabs.audio import AudioTab
        from ui_android.tabs.settings import SettingsTab

        tabs = [
            ConnectionTab(app=self),
            ChannelsTab(app=self),
            ChatTab(app=self),
            AudioTab(app=self),
            SettingsTab(app=self),
        ]

        container = toga.OptionContainer(
            content=[(tab.title, tab.build()) for tab in tabs],
            style=Pack(flex=1),
        )

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = container
        self.main_window.show()

    def _on_tt_event(self, event_name: str, **kwargs) -> None:
        """Leitet SDK-Events thread-sicher an den EventBus weiter."""
        self.loop.call_soon_threadsafe(self.bus.emit, event_name, **kwargs)

    def connect(
        self,
        host: str,
        tcp_port: int,
        udp_port: int,
        nickname: str,
        username: str,
        password: str,
        client_name: str = "TeamTalk VO Android",
        encrypted: bool = False,
    ) -> None:
        """Startet den Verbindungsaufbau in einem Hintergrund-Thread."""
        def _run():
            result = self.client.connect_and_login(
                host=host,
                tcp_port=tcp_port,
                udp_port=udp_port,
                nickname=nickname,
                username=username,
                password=password,
                client_name=client_name,
                encrypted=encrypted,
            )
            self.loop.call_soon_threadsafe(
                self.bus.emit,
                "connect_result",
                ok=result.ok,
                message=result.message,
            )

        threading.Thread(target=_run, daemon=True).start()

    def disconnect(self) -> None:
        self.client.disconnect()
        self.bus.emit("disconnected")


def main() -> toga.App:
    return TeamTalkAndroid(
        "TeamTalk VO Client",
        "cc.leons.teamtalk-vo",
    )
