"""Gewähltes Audiogerät über Ein-/Ausstecken hinweg merken.

Das TeamTalk-SDK vergibt ``nDeviceID`` als laufenden Index; laut
``TeamTalk.h`` kann er sich ändern, sobald USB-Geräte ein- oder ausgesteckt
werden. Stabil ist nur ``szDeviceID`` ("uniquely identifying the sound device
even when new sound devices are being added and removed"), das aber nicht von
jedem Soundsystem geliefert wird – dann dient der Gerätename als Ersatz.

Die Logik ist UI-frei, damit wx- und Qt-Oberfläche sie gleich nutzen:
Ist das gewählte Gerät gerade nicht verbunden, bleibt es als Eintrag
"<Name> (nicht verbunden)" am Ende der Auswahl stehen, geöffnet wird
übergangsweise das System-Standardgerät; kommt das Gerät zurück, wird es
wieder ausgewählt.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

# (szDeviceID, szDeviceName) – beides kann leer sein
DeviceIdentity = Tuple[str, str]


def device_identity(dev, tt_str: Callable) -> DeviceIdentity:
    uid = (tt_str(getattr(dev, "szDeviceID", "") or "") or "").strip()
    name = (tt_str(getattr(dev, "szDeviceName", "") or "") or "").strip()
    return uid, name


def find_device_index(devices: Sequence, wanted: Optional[DeviceIdentity], tt_str: Callable) -> int:
    """Index des gewünschten Geräts in ``devices`` oder -1.

    Erst über die stabile Geräte-ID, nur ohne ID über den Namen – damit zwei
    gleichnamige Geräte mit unterschiedlicher ID nicht verwechselt werden.
    """
    if not wanted:
        return -1
    uid, name = wanted
    if uid:
        for idx, dev in enumerate(devices):
            if device_identity(dev, tt_str)[0] == uid:
                return idx
        # ID nicht gefunden: nur auf den Namen ausweichen, wenn das Soundsystem
        # für das Kandidatengerät gar keine ID liefert.
        for idx, dev in enumerate(devices):
            d_uid, d_name = device_identity(dev, tt_str)
            if not d_uid and name and d_name == name:
                return idx
        return -1
    if name:
        for idx, dev in enumerate(devices):
            if device_identity(dev, tt_str)[1] == name:
                return idx
    return -1


def find_device_id_index(devices: Sequence, device_id) -> int:
    if device_id is None:
        return -1
    for idx, dev in enumerate(devices):
        if int(dev.nDeviceID) == int(device_id):
            return idx
    return -1


def remap_device_id(old_devices: Sequence, old_index: int, new_devices: Sequence, tt_str: Callable):
    """``nDeviceID`` des zuvor gewählten Geräts in der neuen Liste.

    ``nDeviceID`` ist nur ein laufender Index und verschiebt sich nach einem
    Soundsystem-Neustart, wenn Geräte hinzukommen oder wegfallen – die alte
    Nummer zeigt dann auf ein anderes Gerät. Deshalb über die Identität
    (szDeviceID bzw. Name) neu zuordnen; ``None``, wenn das Gerät fehlt."""
    if not 0 <= old_index < len(old_devices):
        return None
    idx = find_device_index(new_devices, device_identity(old_devices[old_index], tt_str), tt_str)
    return int(new_devices[idx].nDeviceID) if idx >= 0 else None


def missing_label(wanted: DeviceIdentity, not_connected_text: str) -> str:
    name = wanted[1] or wanted[0] or "?"
    return f"{name} ({not_connected_text})"


def plan_selection(
    devices: Sequence,
    labels: List[str],
    wanted: Optional[DeviceIdentity],
    fallback_ids: Sequence,
    tt_str: Callable,
    not_connected_text: str,
    is_virtual: Optional[Callable[[object], bool]] = None,
) -> Tuple[List[str], int, bool]:
    """Berechnet Auswahl-Einträge und zu wählenden Index.

    Rückgabe ``(labels, index, missing)``. Bei ``missing`` ist ``index`` der
    angehängte Platzhalter-Eintrag (``== len(devices)``).
    """
    idx = find_device_index(devices, wanted, tt_str)
    if idx >= 0:
        return list(labels), idx, False
    if wanted and (wanted[0] or wanted[1]):
        return list(labels) + [missing_label(wanted, not_connected_text)], len(devices), True
    for dev_id in fallback_ids:
        idx = find_device_id_index(devices, dev_id)
        if idx >= 0:
            return list(labels), idx, False
    if is_virtual is not None:
        # Notauswahl: lieber echte Hardware als z. B. "TeamTalk Virtual Sound
        # Device" oder ein Konferenz-App-Gerät, das zufällig vorne steht.
        for idx, dev in enumerate(devices):
            if not is_virtual(dev):
                return list(labels), idx, False
    return list(labels), (0 if devices else -1), False


def resolve_open_device(devices: Sequence, selection: int, default_id) -> Optional[object]:
    """Gerät, das tatsächlich geöffnet werden soll: das gewählte, oder beim
    Platzhalter ("nicht verbunden") das aktuelle System-Standardgerät."""
    if 0 <= selection < len(devices):
        return devices[selection]
    idx = find_device_id_index(devices, default_id)
    if idx >= 0:
        return devices[idx]
    return devices[0] if devices else None


# Nachlauf der Sprachaktivierung: SDK-Vorgabe laut TeamTalk.h
# (TT_SetVoiceActivationStopDelay) sind 1500 ms. Bis v10.6.1 stand das Feld
# im Audio-Tab auf 0 und wurde seit v10.5.0 beim Einschalten der
# Sprachaktivierung ans SDK übergeben – das Mikrofon schloss dann nach jeder
# Silbe, die Stimme kam zerstückelt an.
DEFAULT_VA_STOP_DELAY_MS = 1500
VA_DELAY_MIGRATION_KEY = "va_delay_v2"


def stored_va_delay(prefs: dict) -> int:
    """Nachlauf aus gespeicherten Audio-Einstellungen; ein alter 0-Wert (vor
    v10.7.0 ungefragt gespeichert) wird einmalig durch die SDK-Vorgabe ersetzt."""
    try:
        value = int(prefs.get("va_delay", DEFAULT_VA_STOP_DELAY_MS))
    except (TypeError, ValueError):
        return DEFAULT_VA_STOP_DELAY_MS
    if value <= 0 and not prefs.get(VA_DELAY_MIGRATION_KEY):
        return DEFAULT_VA_STOP_DELAY_MS
    return max(0, value)


def prefs_have_devices(prefs: dict) -> bool:
    """Ob ein Audio-Einstellungssatz echte Geräte enthält. Nur solche werden
    automatisch gespeichert – sonst würde ein Zwischenstand ohne Geräteliste
    (z. B. vor dem ersten Soundsystem-Start) gute Einstellungen überschreiben."""
    if not isinstance(prefs, dict):
        return False
    has_in = prefs.get("input_device_id") is not None or bool(prefs.get("input_device_name") or prefs.get("input_device_uid"))
    has_out = prefs.get("output_device_id") is not None or bool(prefs.get("output_device_name") or prefs.get("output_device_uid"))
    return has_in and has_out


def migrate_audio_autosave(settings) -> bool:
    """v11.2.2: "Audioeinstellungen beim Start anwenden" war standardmäßig aus –
    gespeicherte Audio-Einstellungen wirkten deshalb nach dem Neustart nicht.
    Einmalig für alle einschalten. True, wenn etwas geändert wurde."""
    if getattr(settings, "audio_autosave_migrated", False):
        return False
    settings.auto_apply_audio = True
    settings.audio_autosave_migrated = True
    return True
