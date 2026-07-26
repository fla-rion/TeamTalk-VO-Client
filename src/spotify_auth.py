"""Spotify PKCE OAuth flow — pure Python stdlib, no external deps.

Uses the same client-ID that librespot uses internally so no developer
account or app registration is required.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import urllib.parse
import urllib.request
from typing import Callable, Optional

_CLIENT_ID = "65b708073fc0480ea92a077233ca87bd"
_REDIRECT_PORT = 5588
_REDIRECT_URI = f"http://127.0.0.1:{_REDIRECT_PORT}/login"
_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SCOPES = (
    "streaming "
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)

_SUCCESS_HTML = """\
<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Spotify – Anmeldung erfolgreich</title>
<style>body{font-family:sans-serif;text-align:center;padding:60px;background:#191414;color:#fff}
h1{color:#1db954}p{color:#ccc}</style></head>
<body><h1>&#10003; Anmeldung erfolgreich!</h1>
<p>Du kannst dieses Fenster jetzt schlie&szlig;en und zum TeamTalk VO Client zur&uuml;ckkehren.</p>
</body></html>"""


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(96)).rstrip(b"=").decode()[:96]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class _CallbackServer:
    """Minimal HTTP server that catches exactly one OAuth callback."""

    def __init__(self) -> None:
        self.code: Optional[str] = None
        self.error: Optional[str] = None
        self._done = threading.Event()
        _parent = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                _parent.code = (qs.get("code") or [None])[0]
                _parent.error = (qs.get("error") or [None])[0]
                body = _SUCCESS_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                _parent._done.set()

            def log_message(self, *_):
                pass

        self._srv = http.server.HTTPServer(("127.0.0.1", _REDIRECT_PORT), _Handler)
        self._srv.timeout = 1.0

    def wait(self, timeout: float) -> bool:
        """Pump the server until callback arrives or timeout expires."""
        import time
        deadline = time.monotonic() + timeout
        while not self._done.is_set() and time.monotonic() < deadline:
            self._srv.handle_request()
        self._srv.server_close()
        return self._done.is_set()


def build_auth_url() -> tuple[str, str]:
    """Return (auth_url, code_verifier). Start a login flow."""
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(12)
    params = {
        "client_id": _CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": _SCOPES,
    }
    url = f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return url, verifier


def exchange_code(code: str, verifier: str) -> str:
    """Exchange auth code for access token. Returns the access token."""
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _REDIRECT_URI,
        "client_id": _CLIENT_ID,
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(_TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"Kein Access-Token in der Antwort: {data}")
    return token


def login(
    on_url: Optional[Callable[[str], None]] = None,
    timeout: float = 120.0,
) -> str:
    """
    Run the full PKCE OAuth flow.

    Opens the browser, waits for the callback, exchanges the code.
    Returns the access token on success, raises on failure.

    ``on_url`` is called with the auth URL so the UI can display it
    (useful when the browser doesn't open automatically).
    """
    import webbrowser

    auth_url, verifier = build_auth_url()
    srv = _CallbackServer()

    webbrowser.open(auth_url)
    if on_url:
        on_url(auth_url)

    if not srv.wait(timeout):
        raise TimeoutError(
            "Spotify-Login Timeout – kein Callback erhalten. "
            "Hast du die Anmeldung im Browser abgeschlossen?"
        )
    if srv.error:
        raise PermissionError(f"Spotify-Anmeldung abgelehnt: {srv.error}")
    if not srv.code:
        raise RuntimeError("Kein Autorisierungscode erhalten.")

    return exchange_code(srv.code, verifier)
