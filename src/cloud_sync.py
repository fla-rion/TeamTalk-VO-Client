"""Google Drive Sync – plattformübergreifende Cloud-Synchronisierung.

Speichert Serverprofile und Einstellungen in der App-Daten-Sandbox von Google Drive
(appDataFolder – für Nutzer unsichtbar). Funktioniert auf macOS, Windows und Linux.

Voraussetzung: Google OAuth2 Client-ID in settings (google_client_id).
Standardmäßig wird eine Browser-Auth-Seite geöffnet.
"""
from __future__ import annotations

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

_DRIVE_FILE_NAME = "teamtalk_vo_sync.json"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_URL = "https://www.googleapis.com/drive/v3/files"
_DRIVE_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class GoogleDriveSyncClient:
    """Google Drive Sync Client für den Hauptclient."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        on_token_saved: Callable[[Dict], None] | None = None,
        stored_tokens: Dict | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._on_token_saved = on_token_saved
        self._tokens: Dict = stored_tokens or {}
        self._user_email: str = ""
        if self._tokens.get("access_token"):
            self._refresh_user_info()

    @property
    def is_signed_in(self) -> bool:
        return bool(self._tokens.get("refresh_token"))

    @property
    def user_email(self) -> str:
        return self._user_email

    # MARK: - Auth

    def sign_in(self, redirect_port: int = 19882) -> bool:
        """Öffnet Browser für OAuth2, wartet auf Callback."""
        if not _HAS_REQUESTS:
            raise RuntimeError("requests nicht installiert (pip install requests)")
        redirect_uri = f"http://localhost:{redirect_port}"
        scope = "https://www.googleapis.com/auth/drive.appdata https://www.googleapis.com/auth/userinfo.email"
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        code: list[str | None] = [None]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                qs = parse_qs(urlparse(self.path).query)
                code[0] = (qs.get("code") or [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>TeamTalk VO: Anmeldung erfolgreich. Du kannst dieses Fenster schliessen.</h1>")

        server = HTTPServer(("localhost", redirect_port), Handler)
        server.timeout = 120
        webbrowser.open(auth_url)
        server.handle_request()
        server.server_close()
        if not code[0]:
            return False
        return self._exchange_code(code[0], redirect_uri)

    def sign_out(self) -> None:
        self._tokens = {}
        self._user_email = ""

    def _exchange_code(self, code: str, redirect_uri: str) -> bool:
        resp = requests.post(_TOKEN_URL, data={
            "code": code, "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }, timeout=10)
        if resp.status_code != 200:
            return False
        self._tokens = resp.json()
        if self._on_token_saved:
            self._on_token_saved(self._tokens)
        self._refresh_user_info()
        return True

    def _refresh_token(self) -> bool:
        rt = self._tokens.get("refresh_token")
        if not rt:
            return False
        resp = requests.post(_TOKEN_URL, data={
            "refresh_token": rt, "client_id": self.client_id,
            "client_secret": self.client_secret, "grant_type": "refresh_token",
        }, timeout=10)
        if resp.status_code != 200:
            return False
        new = resp.json()
        self._tokens["access_token"] = new["access_token"]
        if self._on_token_saved:
            self._on_token_saved(self._tokens)
        return True

    def _auth_header(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._tokens.get('access_token', '')}"}

    def _refresh_user_info(self) -> None:
        try:
            r = requests.get(_USERINFO_URL, headers=self._auth_header(), timeout=5)
            if r.status_code == 200:
                self._user_email = r.json().get("email", "")
        except Exception:
            pass

    # MARK: - Upload

    def upload(self, payload: Dict) -> bool:
        """Lädt Sync-Payload zu Google Drive hoch (appDataFolder)."""
        if not _HAS_REQUESTS or not self._tokens.get("access_token"):
            return False
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._try_upload(data) or (self._refresh_token() and self._try_upload(data))

    def _try_upload(self, data: bytes) -> bool:
        file_id = self._find_file()
        if file_id:
            url = f"{_DRIVE_UPLOAD_URL}/{file_id}?uploadType=media"
            method = "PATCH"
        else:
            meta = {"name": _DRIVE_FILE_NAME, "parents": ["appDataFolder"]}
            r = requests.post(
                _DRIVE_URL, headers={**self._auth_header(), "Content-Type": "application/json"},
                json=meta, timeout=10
            )
            if r.status_code not in (200, 201):
                return False
            file_id = r.json().get("id")
            url = f"{_DRIVE_UPLOAD_URL}/{file_id}?uploadType=media"
            method = "PATCH"
        r = requests.request(
            method, url,
            headers={**self._auth_header(), "Content-Type": "application/json"},
            data=data, timeout=15
        )
        return r.status_code == 200

    # MARK: - Download

    def download(self) -> Optional[Dict]:
        """Lädt Sync-Payload von Google Drive herunter."""
        if not _HAS_REQUESTS or not self._tokens.get("access_token"):
            return None
        result = self._try_download()
        if result is None and self._refresh_token():
            result = self._try_download()
        return result

    def _try_download(self) -> Optional[Dict]:
        file_id = self._find_file()
        if not file_id:
            return None
        r = requests.get(
            f"{_DRIVE_URL}/{file_id}?alt=media",
            headers=self._auth_header(), timeout=15
        )
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except Exception:
            return None

    def _find_file(self) -> Optional[str]:
        q = f"name='{_DRIVE_FILE_NAME}' and 'appDataFolder' in parents and trashed=false"
        r = requests.get(
            _DRIVE_URL, params={"spaces": "appDataFolder", "q": q, "fields": "files(id,name)"},
            headers=self._auth_header(), timeout=10
        )
        if r.status_code != 200:
            return None
        files = r.json().get("files", [])
        return files[0]["id"] if files else None


class SyncPayloadBuilder:
    """Baut und entpackt den plattformübergreifenden Sync-Payload."""

    PLATFORM = "macos"  # wird in app_wx.py überschrieben

    @staticmethod
    def build(settings_store, server_profiles: List[Dict]) -> Dict:
        """Erstellt Sync-Payload aus SettingsStore und Serverprofilen."""
        s = settings_store.settings
        return {
            "platform": SyncPayloadBuilder.PLATFORM,
            "app_version": getattr(settings_store, "_app_version", "?"),
            "synced_at": time.time(),
            "servers": server_profiles,
            "preferences": {
                "nickname": getattr(s, "nickname", ""),
                "announcement_mode": getattr(s, "announcement_mode", "full"),
                "auto_reconnect": getattr(s, "auto_reconnect", True),
                "voice_activation_enabled": getattr(s, "voice_activation", False),
                "master_volume": getattr(s, "master_volume", 100),
            },
        }

    @staticmethod
    def extract_servers(payload: Dict) -> List[Dict]:
        return payload.get("servers", [])

    @staticmethod
    def extract_preferences(payload: Dict) -> Dict:
        return payload.get("preferences", {})
