"""Basisklasse für alle Android-Tabs."""
from __future__ import annotations

from typing import TYPE_CHECKING

import toga

if TYPE_CHECKING:
    from app_android import TeamTalkAndroid


class BaseTab:
    title: str = "Tab"

    def __init__(self, app: "TeamTalkAndroid") -> None:
        self.app = app
        self.client = app.client
        self.bus = app.bus
        self.settings = app.settings_store.settings

    def build(self) -> toga.Widget:
        raise NotImplementedError
