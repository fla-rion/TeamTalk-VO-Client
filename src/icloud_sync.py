"""iCloud Key-Value-Store Sync (macOS only, erfordert PyObjC).

Synchronisiert Serverprofile und Einstellungen über NSUbiquitousKeyValueStore.
Funktioniert nur auf macOS mit einem angemeldeten iCloud-Account.
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

_SERVERS_KEY = "icloud_saved_servers_v1"
_PREFS_KEY   = "icloud_app_preferences_v1"

try:
    from Foundation import NSUbiquitousKeyValueStore, NSNotificationCenter
    _HAS_KVS = True
except ImportError:
    _HAS_KVS = False


class ICloudSyncClient:
    """iCloud KVS Sync für macOS (erfordert PyObjC + iCloud-Account)."""

    def __init__(self, on_external_change: Callable[[List[str]], None] | None = None) -> None:
        self._on_change = on_external_change
        self._available = _HAS_KVS
        if self._available:
            self._kvs = NSUbiquitousKeyValueStore.defaultStore()
            self._kvs.synchronize()
            if on_external_change:
                NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
                    self._ObjcObserver(on_external_change),
                    "handleChange:",
                    "NSUbiquitousKeyValueStoreDidChangeExternallyNotification",
                    self._kvs,
                )

    @property
    def is_available(self) -> bool:
        return self._available

    def upload_servers(self, servers: List[Dict]) -> bool:
        if not self._available:
            return False
        try:
            self._kvs.setData_forKey_(
                json.dumps(servers, ensure_ascii=False).encode("utf-8"),
                _SERVERS_KEY
            )
            self._kvs.synchronize()
            return True
        except Exception:
            return False

    def upload_preferences(self, prefs: Dict) -> bool:
        if not self._available:
            return False
        safe = {k: v for k, v in prefs.items() if "key" not in k.lower() and "password" not in k.lower()}
        try:
            self._kvs.setData_forKey_(
                json.dumps(safe, ensure_ascii=False).encode("utf-8"),
                _PREFS_KEY
            )
            self._kvs.synchronize()
            return True
        except Exception:
            return False

    def download_servers(self) -> Optional[List[Dict]]:
        if not self._available:
            return None
        try:
            data = self._kvs.dataForKey_(_SERVERS_KEY)
            if data is None:
                return None
            return json.loads(bytes(data))
        except Exception:
            return None

    def download_preferences(self) -> Optional[Dict]:
        if not self._available:
            return None
        try:
            data = self._kvs.dataForKey_(_PREFS_KEY)
            if data is None:
                return None
            return json.loads(bytes(data))
        except Exception:
            return None

    class _ObjcObserver:
        """Minimaler ObjC-Objekt-Wrapper für Notification-Callback."""
        def __init__(self, callback: Callable[[List[str]], None]) -> None:
            self._cb = callback

        def handleChange_(self, notification) -> None:
            try:
                info = notification.userInfo()
                keys = list(info.get("NSUbiquitousKeyValueStoreChangedKeysKey") or [])
                import wx
                wx.CallAfter(self._cb, keys)
            except Exception:
                pass
