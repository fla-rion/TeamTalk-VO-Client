"""CoreAudio-Hotplug-Watcher (macOS).

Lauscht per `AudioObjectAddPropertyListener` auf Geräte-Hinzufügung/-Entfernung
und Default-Geräte-Wechsel, analog zu math65/ttaccessibles
`AudioDeviceChangeMonitor.swift` (github.com/math65/ttaccessible). CoreAudio
meldet Änderungen per Push sofort -- kein Polling nötig.

Das TeamTalk-SDK selbst cached seine Geräteliste beim Start und erkennt neue
Hardware erst nach einem expliziten `TT_RestartSoundSystem()`-Zyklus (siehe
`teamtalk_client/client.py:restart_sound_system`). Dieser Watcher ersetzt
nicht die SDK-Audio-Pipeline, sondern liefert nur den zuverlässigen Trigger,
wann ein solcher Zyklus fällig ist.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
import threading
from typing import Callable, List, Optional

_IS_MAC = sys.platform == "darwin"

OSStatus = ctypes.c_int32
AudioObjectID = ctypes.c_uint32


class AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


# FourCC-Konstanten aus AudioHardwareBase.h / AudioHardware.h
_K_SCOPE_GLOBAL = 0x676C6F62          # 'glob'
_K_ELEMENT_MAIN = 0
_K_PROP_DEVICES = 0x64657623          # 'dev#'
_K_PROP_DEFAULT_INPUT = 0x64496E20    # 'dIn '
_K_PROP_DEFAULT_OUTPUT = 0x644F7574   # 'dOut'
_K_SYSTEM_OBJECT = 1

_WATCHED_SELECTORS = (_K_PROP_DEVICES, _K_PROP_DEFAULT_INPUT, _K_PROP_DEFAULT_OUTPUT)

_LISTENER_PROC = ctypes.CFUNCTYPE(
    OSStatus,
    AudioObjectID,
    ctypes.c_uint32,
    ctypes.POINTER(AudioObjectPropertyAddress),
    ctypes.c_void_p,
)


def _load_coreaudio() -> ctypes.CDLL:
    path = ctypes.util.find_library("CoreAudio") or (
        "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
    )
    lib = ctypes.CDLL(path)
    lib.AudioObjectAddPropertyListener.restype = OSStatus
    lib.AudioObjectAddPropertyListener.argtypes = [
        AudioObjectID,
        ctypes.POINTER(AudioObjectPropertyAddress),
        _LISTENER_PROC,
        ctypes.c_void_p,
    ]
    lib.AudioObjectRemovePropertyListener.restype = OSStatus
    lib.AudioObjectRemovePropertyListener.argtypes = [
        AudioObjectID,
        ctypes.POINTER(AudioObjectPropertyAddress),
        _LISTENER_PROC,
        ctypes.c_void_p,
    ]
    return lib


class CoreAudioDeviceWatcher:
    """Meldet Audio-Hardware-Änderungen (Hotplug, Default-Gerät) per Push.

    `callback` wird auf einem CoreAudio-eigenen Thread aufgerufen -- der
    Aufrufer ist dafür zuständig, in den UI-Hauptthread zu marshalen
    (z. B. via `wx.CallAfter`) und ggf. zu entprellen.
    """

    def __init__(self) -> None:
        self._lib: Optional[ctypes.CDLL] = None
        self._listening = False
        self._callback: Optional[Callable[[], None]] = None
        self._c_listener = None
        self._addresses: List[AudioObjectPropertyAddress] = []
        self._lock = threading.Lock()

    def start(self, callback: Callable[[], None]) -> bool:
        if not _IS_MAC:
            return False
        with self._lock:
            if self._listening:
                return True
            try:
                self._lib = _load_coreaudio()
            except Exception:
                self._lib = None
                return False

            self._callback = callback

            def _proc(_object_id, _num_addresses, _addresses, _client_data):
                cb = self._callback
                if cb is not None:
                    try:
                        cb()
                    except Exception:
                        pass
                return 0

            self._c_listener = _LISTENER_PROC(_proc)

            ok = True
            for selector in _WATCHED_SELECTORS:
                addr = AudioObjectPropertyAddress(selector, _K_SCOPE_GLOBAL, _K_ELEMENT_MAIN)
                try:
                    status = self._lib.AudioObjectAddPropertyListener(
                        _K_SYSTEM_OBJECT, ctypes.byref(addr), self._c_listener, None
                    )
                except Exception:
                    status = -1
                if status == 0:
                    self._addresses.append(addr)
                else:
                    ok = False

            self._listening = bool(self._addresses)
            return ok

    def stop(self) -> None:
        with self._lock:
            if not self._listening or self._lib is None:
                self._listening = False
                return
            for addr in self._addresses:
                try:
                    self._lib.AudioObjectRemovePropertyListener(
                        _K_SYSTEM_OBJECT, ctypes.byref(addr), self._c_listener, None
                    )
                except Exception:
                    pass
            self._addresses = []
            self._c_listener = None
            self._callback = None
            self._listening = False

    def is_listening(self) -> bool:
        return self._listening
