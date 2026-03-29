"""Plugin-Loader – lädt Plugins aus dem `plugins/`-Verzeichnis (ab v1.10.1).

Plugins müssen eine Funktion `register(bus, api)` exportieren.
Rückwärtskompatibilität: `register(bus)` (nur ein Parameter) wird ebenfalls akzeptiert.

Optionales Modul-Attribut `metadata` (dict):
    {
        "name": "Mein Plugin",
        "version": "1.0",
        "description": "Was das Plugin macht",
        "author": "Autor",
        "requires": ["other_plugin.py"],  # v4.2.0 – Abhängigkeiten
    }

v4.1.0 – Fehlerhafte Plugins werden isoliert: Lade-Fehler werden in
_errors gespeichert und stören andere Plugins nicht.
Deaktivierte Plugins (disabled_plugins-Liste) werden übersprungen.

v4.2.0 – Abhängigkeiten: requires-Feld in Metadaten, automatische
Lade-Reihenfolge. Reload eines einzelnen Plugins ohne Neustart.
"""
from __future__ import annotations

import importlib.util
import inspect
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from event_bus import EventBus
    from plugin_api import PluginAPI

_DEFAULT_META: Dict[str, Any] = {
    "name": "",
    "version": "",
    "description": "",
    "author": "",
    "requires": [],  # v4.2.0
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
        pro Plugin isoliert gespeichert.
        v4.2.0: Abhängigkeiten (requires) werden vor abhängigen Plugins geladen.
        """
        if not self._dir.exists():
            return 0
        disabled_set = set(disabled or [])
        all_paths = {
            p.name: p for p in sorted(self._dir.glob("*.py"))
            if not p.name.startswith("_") and p.name not in disabled_set
        }
        # v4.2.0 – topologische Sortierung nach requires
        ordered = self._topo_sort(all_paths)
        count = 0
        for filename in ordered:
            path = all_paths[filename]
            count += self._load_one(path)
        return count

    def _topo_sort(self, paths: Dict[str, Path]) -> List[str]:
        """Sortiert Plugins so, dass requires-Abhängigkeiten zuerst geladen werden."""
        # Schnelle Vorschau-Metadaten ohne vollständiges Laden
        requires_map: Dict[str, List[str]] = {}
        for name, path in paths.items():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                # Sehr vereinfachtes Parsen: suche nach metadata = {...}
                import ast
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Assign)
                        and any(
                            isinstance(t, ast.Name) and t.id == "metadata"
                            for t in node.targets
                        )
                        and isinstance(node.value, ast.Dict)
                    ):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and k.value == "requires":
                                if isinstance(v, (ast.List, ast.Tuple)):
                                    deps = [
                                        elt.value for elt in v.elts
                                        if isinstance(elt, ast.Constant)
                                        and isinstance(elt.value, str)
                                    ]
                                    requires_map[name] = deps
            except Exception:
                pass

        visited: set = set()
        order: List[str] = []

        def visit(name: str, stack: set) -> None:
            if name in visited:
                return
            if name in stack:
                return  # Zyklus ignorieren
            stack.add(name)
            for dep in requires_map.get(name, []):
                if dep in paths:
                    visit(dep, stack)
            stack.discard(name)
            visited.add(name)
            order.append(name)

        for name in sorted(paths.keys()):
            visit(name, set())
        return order

    def _load_one(self, path: Path) -> int:
        """Lädt ein einzelnes Plugin. Gibt 1 bei Erfolg, 0 bei Fehler zurück."""
        try:
            spec = importlib.util.spec_from_file_location(f"plugin_{path.stem}", path)
            if spec is None or spec.loader is None:
                return 0
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            if hasattr(module, "register") and callable(module.register):
                self._call_register(module)
                if path.name in self._loaded:
                    self._loaded.remove(path.name)
                self._loaded.append(path.name)
                meta: Dict[str, Any] = dict(_DEFAULT_META)
                raw = getattr(module, "metadata", None)
                if isinstance(raw, dict):
                    for k in _DEFAULT_META:
                        if k in raw:
                            if k == "requires":
                                meta[k] = list(raw[k]) if isinstance(raw[k], (list, tuple)) else []
                            else:
                                meta[k] = str(raw[k])
                if not meta["name"]:
                    meta["name"] = path.stem
                self._metadata[path.name] = meta
                self._errors.pop(path.name, None)
                return 1
        except Exception as exc:
            tb = traceback.format_exc()
            self._errors[path.name] = f"{exc}\n{tb}"
            print(f"[PluginLoader] Fehler beim Laden von {path.name}: {exc}")
        return 0

    def reload_plugin(self, filename: str) -> bool:
        """v4.2.0 – Lädt ein einzelnes Plugin neu (ohne App-Neustart).

        Gibt True zurück wenn erfolgreich. Entfernt vorher alle Bus-Handler
        des Plugins NICHT (da nicht nachverfolgbar) – geeignet für Entwickler.
        """
        path = self._dir / filename
        if not path.exists():
            return False
        if filename in self._loaded:
            self._loaded.remove(filename)
        result = self._load_one(path)
        return result == 1

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
