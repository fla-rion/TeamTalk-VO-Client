"""Plugin-Loader – lädt Plugins aus dem `plugins/`-Verzeichnis (ab v1.10.1).

Plugins müssen eine Funktion `register(bus, api)` exportieren.
Rückwärtskompatibilität: `register(bus)` (nur ein Parameter) wird ebenfalls akzeptiert.

Optionales Modul-Attribut `metadata` (dict):
    {
        "name": "Mein Plugin",
        "version": "1.0",
        "description": "Was das Plugin macht",
        "author": "Autor",
    }

v4.1.0 – Fehlerhafte Plugins werden isoliert: Lade-Fehler werden in
_errors gespeichert und stören andere Plugins nicht.
Deaktivierte Plugins (disabled_plugins-Liste) werden übersprungen.
"""
from __future__ import annotations

import importlib.util
import inspect
import traceback
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from event_bus import EventBus
    from plugin_api import PluginAPI

_DEFAULT_META: Dict[str, str] = {
    "name": "",
    "version": "",
    "description": "",
    "author": "",
}


class PluginLoader:
    def __init__(self, bus: "EventBus", plugins_dir: Path, api: Optional["PluginAPI"] = None) -> None:
        self._bus = bus
        self._dir = plugins_dir
        self._api = api
        self._loaded: List[str] = []
        # filename -> metadata dict
        self._metadata: Dict[str, Dict[str, str]] = {}
        # v4.1.0 – Fehler-Tracking: filename -> Fehlermeldung
        self._errors: Dict[str, str] = {}

    def load_all(self, disabled: Optional[List[str]] = None) -> int:
        """Lädt alle Plugins aus dem Plugins-Verzeichnis.

        v4.1.0: disabled-Liste überspringt Plugins; Lade-Fehler werden
        pro Plugin isoliert gespeichert (kein Abbruch der gesamten Ladephase).
        Gibt Anzahl erfolgreich geladener Plugins zurück.
        """
        if not self._dir.exists():
            return 0
        disabled_set = set(disabled or [])
        count = 0
        for path in sorted(self._dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            if path.name in disabled_set:
                print(f"[PluginLoader] Übersprungen (deaktiviert): {path.name}")
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"plugin_{path.stem}", path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                if hasattr(module, "register") and callable(module.register):
                    self._call_register(module)
                    self._loaded.append(path.name)
                    # Metadaten einlesen
                    meta = dict(_DEFAULT_META)
                    raw = getattr(module, "metadata", None)
                    if isinstance(raw, dict):
                        for k in _DEFAULT_META:
                            if k in raw:
                                meta[k] = str(raw[k])
                    if not meta["name"]:
                        meta["name"] = path.stem
                    self._metadata[path.name] = meta
                    count += 1
            except Exception as exc:
                tb = traceback.format_exc()
                self._errors[path.name] = f"{exc}\n{tb}"
                print(f"[PluginLoader] Fehler beim Laden von {path.name}: {exc}")
        return count

    def _call_register(self, module) -> None:
        """Ruft register(bus, api) oder register(bus) auf (Rückwärtskompatibilität)."""
        fn = module.register
        try:
            sig = inspect.signature(fn)
            n_params = len(sig.parameters)
        except (ValueError, TypeError):
            n_params = 1
        if n_params >= 2 and self._api is not None:
            fn(self._bus, self._api)
        else:
            fn(self._bus)

    @property
    def loaded_plugins(self) -> List[str]:
        return list(self._loaded)

    def get_metadata(self, filename: str) -> Dict[str, str]:
        """Gibt die Metadaten eines geladenen Plugins zurück."""
        return dict(self._metadata.get(filename, _DEFAULT_META))

    def all_metadata(self) -> Dict[str, Dict[str, str]]:
        """Gibt Metadaten aller geladenen Plugins zurück."""
        return {k: dict(v) for k, v in self._metadata.items()}

    def get_errors(self) -> Dict[str, str]:
        """v4.1.0 – Gibt Lade-Fehler zurück (filename → Traceback-String)."""
        return dict(self._errors)

    def has_error(self, filename: str) -> bool:
        """v4.1.0 – True wenn das Plugin beim Laden fehlgeschlagen ist."""
        return filename in self._errors
