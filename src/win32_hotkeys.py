"""Systemweite Hotkeys für Windows via GetAsyncKeyState-Polling."""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Optional

_WIN_VK_NAMES: dict[int, str] = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc", 0x20: "Leertaste",
    0x21: "Bild-Auf", 0x22: "Bild-Ab", 0x23: "Ende", 0x24: "Pos1",
    0x25: "Links", 0x26: "Oben", 0x27: "Rechts", 0x28: "Unten",
    0x2E: "Entf", 0x2C: "Druck",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5", 0x75: "F6",
    0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10", 0x7A: "F11", 0x7B: "F12",
    0xA0: "Shift-L", 0xA1: "Shift-R", 0xA2: "Strg-L", 0xA3: "Strg-R",
    0xA4: "Alt-L", 0xA5: "Alt-R",
}


def win32_vk_to_name(vk: int) -> str:
    if not vk:
        return "(nicht gesetzt)"
    if vk in _WIN_VK_NAMES:
        return _WIN_VK_NAMES[vk]
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    return f"VK-{vk:#04x}"


class Win32GlobalHotkeyManager:
    """Überwacht systemweite Tastenanschläge via GetAsyncKeyState (Windows-only).

    Auf anderen Plattformen werden alle Methoden zu No-ops degradiert.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ptt_vk: int = 0
        self._mute_vk: int = 0
        self._on_ptt_down: Optional[Callable] = None
        self._on_ptt_up: Optional[Callable] = None
        self._on_mute: Optional[Callable] = None
        self._call_after: Optional[Callable] = None
        self._ptt_was_down = False
        self._mute_was_down = False

    def start(
        self,
        ptt_vk: int,
        mute_vk: int,
        on_ptt_down: Callable,
        on_ptt_up: Callable,
        on_mute: Callable,
        call_after: Optional[Callable] = None,
    ) -> None:
        if sys.platform != "win32":
            return
        self.stop()
        self._ptt_vk = ptt_vk
        self._mute_vk = mute_vk
        self._on_ptt_down = on_ptt_down
        self._on_ptt_up = on_ptt_up
        self._on_mute = on_mute
        self._call_after = call_after or (lambda fn: fn())
        self._ptt_was_down = False
        self._mute_was_down = False
        self._running = True
        self._thread = threading.Thread(target=self._poll, daemon=True, name="Win32GlobalHotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None

    def _poll(self) -> None:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            while self._running:
                if self._mute_vk:
                    state = user32.GetAsyncKeyState(self._mute_vk)
                    is_down = bool(state & 0x8000)
                    if is_down and not self._mute_was_down:
                        self._mute_was_down = True
                        if self._on_mute:
                            self._call_after(self._on_mute)
                    elif not is_down:
                        self._mute_was_down = False

                if self._ptt_vk:
                    state = user32.GetAsyncKeyState(self._ptt_vk)
                    is_down = bool(state & 0x8000)
                    if is_down and not self._ptt_was_down:
                        self._ptt_was_down = True
                        if self._on_ptt_down:
                            self._call_after(self._on_ptt_down)
                    elif not is_down and self._ptt_was_down:
                        self._ptt_was_down = False
                        if self._on_ptt_up:
                            self._call_after(self._on_ptt_up)

                time.sleep(0.05)
        except Exception:
            pass
