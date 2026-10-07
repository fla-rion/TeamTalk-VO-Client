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


# Art einer Änderung (Argument des Callbacks)
CHANGE_DEVICES = "devices"     # Gerät hinzugekommen/entfernt → SDK-Neustart nötig
CHANGE_DEFAULTS = "defaults"   # nur System-Standardgerät gewechselt


def classify_change(old_sig, new_sig) -> Optional[str]:
    """Vergleicht zwei Signaturen ``(device_ids, default_in, default_out)``.

    ``None`` = keine echte Änderung. Ist eine Signatur unbekannt, gilt das
    vorsichtshalber als Geräteänderung (lieber ein Neustart zu viel)."""
    if old_sig is None or new_sig is None:
        return CHANGE_DEVICES
    if old_sig == new_sig:
        return None
    if old_sig[0] != new_sig[0]:
        return CHANGE_DEVICES
    return CHANGE_DEFAULTS


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
    lib.AudioObjectGetPropertyDataSize.restype = OSStatus
    lib.AudioObjectGetPropertyDataSize.argtypes = [
        AudioObjectID,
        ctypes.POINTER(AudioObjectPropertyAddress),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.AudioObjectGetPropertyData.restype = OSStatus
    lib.AudioObjectGetPropertyData.argtypes = [
        AudioObjectID,
        ctypes.POINTER(AudioObjectPropertyAddress),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
    ]
    return lib


class CoreAudioDeviceWatcher:
    """Meldet Audio-Hardware-Änderungen (Hotplug, Default-Gerät) per Push.

    `callback` wird auf einem CoreAudio-eigenen Thread aufgerufen -- der
    Aufrufer ist dafür zuständig, in den UI-Hauptthread zu marshalen
    (z. B. via `wx.CallAfter`) und ggf. zu entprellen.

    Manche virtuellen Audiotreiber (z. B. Rogue Amoebas "Loopback") melden
    `kAudioHardwarePropertyDevices`/Default-Geräte-Wechsel sehr häufig,
    auch ohne dass sich an der Geräteliste wirklich etwas ändert (interne
    Neukonfiguration ihrer Audio-Capture-Engine). Da der Aufrufer auf jede
    Meldung mit einem vollen `TT_RestartSoundSystem()`-Zyklus reagiert
    (Mikrofon/Ausgabe kurz schließen+neu öffnen), würde ungefiltertes
    Weiterleiten bei so einem Treiber zu ständigen, hörbaren Tonaussetzern
    führen -- unabhängig vom gewählten Gerät, da jeder Zyklus alle Geräte
    betrifft. Deshalb wird vor jedem Callback-Aufruf eine billige,
    treiberunabhängige Signatur (Geräte-IDs + Default-In/Out) direkt per
    CoreAudio gelesen; der Callback feuert nur, wenn sie sich wirklich
    geändert hat.
    """

    def __init__(self) -> None:
        self._lib: Optional[ctypes.CDLL] = None
        self._listening = False
        self._callback: Optional[Callable[[], None]] = None
        self._c_listener = None
        self._addresses: List[AudioObjectPropertyAddress] = []
        self._lock = threading.Lock()
        self._sig_lock = threading.Lock()
        self._last_signature = None

    def _read_signature(self):
        """Liest Geräte-IDs + Default-In/Out direkt von CoreAudio (billig,
        kein SDK-Zugriff). None bei Fehler (Signatur bleibt dann unverändert
        -- lieber einen Callback zu viel als einen zu wenig)."""
        lib = self._lib
        if lib is None:
            return None
        try:
            devices_addr = AudioObjectPropertyAddress(_K_PROP_DEVICES, _K_SCOPE_GLOBAL, _K_ELEMENT_MAIN)
            size = ctypes.c_uint32(0)
            status = lib.AudioObjectGetPropertyDataSize(
                _K_SYSTEM_OBJECT, ctypes.byref(devices_addr), 0, None, ctypes.byref(size)
            )
            if status != 0 or size.value == 0:
                return None
            count = size.value // ctypes.sizeof(AudioObjectID)
            buf = (AudioObjectID * count)()
            got_size = ctypes.c_uint32(size.value)
            status = lib.AudioObjectGetPropertyData(
                _K_SYSTEM_OBJECT, ctypes.byref(devices_addr), 0, None, ctypes.byref(got_size), buf
            )
            if status != 0:
                return None
            device_ids = frozenset(int(x) for x in buf)

            def _read_default(selector: int) -> int:
                addr = AudioObjectPropertyAddress(selector, _K_SCOPE_GLOBAL, _K_ELEMENT_MAIN)
                val = AudioObjectID(0)
                sz = ctypes.c_uint32(ctypes.sizeof(val))
                st = lib.AudioObjectGetPropertyData(
                    _K_SYSTEM_OBJECT, ctypes.byref(addr), 0, None, ctypes.byref(sz), ctypes.byref(val)
                )
                return int(val.value) if st == 0 else -1

            default_in = _read_default(_K_PROP_DEFAULT_INPUT)
            default_out = _read_default(_K_PROP_DEFAULT_OUTPUT)
            return (device_ids, default_in, default_out)
        except Exception:
            return None

    def start(self, callback: Callable[[str], None]) -> bool:
        """``callback(kind)`` mit ``CHANGE_DEVICES`` oder ``CHANGE_DEFAULTS``;
        läuft auf einem CoreAudio-Thread."""
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
            self._last_signature = self._read_signature()

            def _proc(_object_id, _num_addresses, _addresses, _client_data):
                cb = self._callback
                if cb is None:
                    return 0
                try:
                    sig = self._read_signature()
                    with self._sig_lock:
                        kind = classify_change(self._last_signature, sig)
                        if sig is not None:
                            self._last_signature = sig
                    if kind is not None:
                        cb(kind)
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
            with self._sig_lock:
                self._last_signature = None

    def is_listening(self) -> bool:
        return self._listening
