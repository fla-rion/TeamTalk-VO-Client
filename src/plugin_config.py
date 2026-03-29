"""PluginConfig – persistenter Key-Value-Store je Plugin (ab v1.10.1).

Daten werden als JSON in
``~/Library/Application Support/TeamTalkVOClient/plugin_configs/<plugin_name>.json``
gespeichert.

v4.2.0 – PluginDbConfig: SQLite-basierter Store in settings.db.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from settings_db import SettingsDB


def _config_dir() -> Path:
    base = Path.home() / "Library" / "Application Support" / "TeamTalkVOClient" / "plugin_configs"
    base.mkdir(parents=True, exist_ok=True)
    return base


class PluginConfig:
    """Einfacher persistenter Key-Value-Store für ein Plugin."""

    def __init__(self, plugin_name: str) -> None:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in plugin_name)
        self._path = _config_dir() / f"{safe}.json"
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text("utf-8"))
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        """Liest einen Wert aus dem Store."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Setzt einen Wert und speichert sofort."""
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> None:
        """Entfernt einen Schlüssel."""
        self._data.pop(key, None)
        self._save()

    def all(self) -> dict:
        """Gibt alle gespeicherten Schlüssel-Wert-Paare zurück."""
        return dict(self._data)


class PluginDbConfig:
    """v4.2.0 – SQLite-basierter Key-Value-Store für Plugins in settings.db.

    Alle Plugin-Daten werden in der Tabelle ``plugin_settings`` mit
    Spalten (plugin_name, key, value_json) gespeichert.
    """

    def __init__(self, plugin_name: str, db: "SettingsDB") -> None:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in plugin_name)
        self._name = safe
        self._db = db
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with self._db.connect() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS plugin_settings "
                    "(plugin_name TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, "
                    "PRIMARY KEY (plugin_name, key))"
                )
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        try:
            with self._db.connect() as conn:
                row = conn.execute(
                    "SELECT value_json FROM plugin_settings WHERE plugin_name=? AND key=?",
                    (self._name, key),
                ).fetchone()
                if row:
                    return json.loads(row[0])
        except Exception:
            pass
        return default

    def set(self, key: str, value: Any) -> None:
        try:
            with self._db.connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO plugin_settings (plugin_name, key, value_json) VALUES (?,?,?)",
                    (self._name, key, json.dumps(value, ensure_ascii=False)),
                )
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            with self._db.connect() as conn:
                conn.execute(
                    "DELETE FROM plugin_settings WHERE plugin_name=? AND key=?",
                    (self._name, key),
                )
        except Exception:
            pass

    def all(self) -> dict:
        result = {}
        try:
            with self._db.connect() as conn:
                rows = conn.execute(
                    "SELECT key, value_json FROM plugin_settings WHERE plugin_name=?",
                    (self._name,),
                ).fetchall()
                for k, v in rows:
                    try:
                        result[k] = json.loads(v)
                    except Exception:
                        result[k] = v
        except Exception:
            pass
        return result

    def clear(self) -> None:
        """Löscht alle Einstellungen des Plugins."""
        try:
            with self._db.connect() as conn:
                conn.execute(
                    "DELETE FROM plugin_settings WHERE plugin_name=?",
                    (self._name,),
                )
        except Exception:
            pass
