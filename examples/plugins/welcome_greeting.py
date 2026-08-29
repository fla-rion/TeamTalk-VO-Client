"""Willkommens-Plugin – Beispiel-/Demo-Plugin für den Plugin-Marketplace.

Sagt beim Verbinden mit einem Server eine kurze Begrüßung an, die den
Servernamen enthält. Dient als minimales, funktionierendes Beispiel für die
`register(bus, api)`-Schnittstelle (siehe plugin_api.py).
"""
from __future__ import annotations

metadata = {
    "name": "Willkommens-Plugin",
    "version": "1.0.0",
    "description": "Sagt beim Verbinden eine kurze Begrüßung mit Servername an.",
    "author": "TeamTalk VO Client Team",
    "requires": [],
}


def register(bus, api) -> None:
    def _on_connection_state_changed(connected: bool = False, reason: str = "", **_kwargs) -> None:
        if not connected:
            return
        server_name = api.get_server_name() or ""
        if server_name:
            api.speak(f"Willkommen auf {server_name}!", kind="system")
        else:
            api.speak("Willkommen!", kind="system")

    bus.on("connection_state_changed", _on_connection_state_changed)
