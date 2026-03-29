"""HTTP-Steuer-API – lokaler HTTP-Server für externe Steuerung (v4.3.0).

Startet einen einfachen HTTP-Server auf localhost:PORT.
Nützlich für Streamdeck, Home Assistant, Skripte etc.

Endpunkte (alle GET):
  /ptt/on          – PTT aktivieren
  /ptt/off         – PTT deaktivieren
  /ptt/toggle      – PTT umschalten
  /mute/on         – Stummschalten
  /mute/off        – Stummschalten aufheben
  /mute/toggle     – Stummschalten umschalten
  /channel/<name>  – Kanal nach Name beitreten
  /status/<text>   – Statusnachricht setzen
  /speak/<text>    – Text per TTS vorlesen
  /info            – JSON: version, connected, channel, users
  /channels        – v4.3.0: JSON-Liste aller Kanäle
  /users           – v4.3.0: JSON-Liste aller Nutzer im aktuellen Kanal
  /server          – v4.3.0: JSON: Serverinfo und Verbindungsstatus
  /docs            – v4.3.0: OpenAPI/Swagger HTML
  /chat            – POST: {"text": "..."} → Nachricht in aktuellen Kanal senden

v4.0.0 – HTTP-API v2:
  /events/stream   – SSE-Stream (text/event-stream) für Echtzeit-Events

v4.3.0 – HTTP-API v3:
  SSE-Token-Authentifizierung (X-Api-Token Header oder ?token= Query-Param)
  GET /channels, /users, /server
  GET /docs  – OpenAPI-Dokumentation
"""
from __future__ import annotations

import json
import queue
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app import MainFrame

_frame_ref: "MainFrame | None" = None
_api_token: Optional[str] = None  # v4.3.0 – optionaler Auth-Token

# Globale SSE-Event-Queue (alle aktiven SSE-Clients teilen sich diesen Ring-Puffer)
_sse_clients: List[queue.Queue] = []
_sse_lock = threading.Lock()

_SSE_KEEPALIVE_S = 15

_OPENAPI_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>TeamTalk VO Client – HTTP-API v3</title>
<style>
body{font-family:monospace;max-width:900px;margin:2em auto;padding:0 1em}
h1{color:#333}h2{color:#555;border-bottom:1px solid #ccc}
.ep{background:#f4f4f4;padding:.5em 1em;margin:.5em 0;border-left:4px solid #4a90d9}
.method{font-weight:bold;color:#4a90d9}.badge{display:inline-block;padding:2px 6px;
border-radius:3px;font-size:.8em;background:#4a90d9;color:#fff;margin-right:4px}
.post{background:#27ae60}.desc{color:#666;font-size:.9em}
</style>
</head>
<body>
<h1>TeamTalk VO Client – HTTP-API v3</h1>
<p>Lokaler HTTP-Server für externe Steuerung (Streamdeck, Home Assistant, Skripte).</p>
<p><b>Basis-URL:</b> <code>http://127.0.0.1:PORT</code></p>
<p><b>Authentifizierung:</b> Bei konfiguriertem API-Token: Header <code>X-Api-Token: &lt;token&gt;</code>
oder Query-Parameter <code>?token=&lt;token&gt;</code></p>

<h2>Steuerung (GET)</h2>
<div class="ep"><span class="badge">GET</span><b>/ptt/on</b> &nbsp;–&nbsp; <span class="desc">PTT aktivieren</span></div>
<div class="ep"><span class="badge">GET</span><b>/ptt/off</b> &nbsp;–&nbsp; <span class="desc">PTT deaktivieren</span></div>
<div class="ep"><span class="badge">GET</span><b>/ptt/toggle</b> &nbsp;–&nbsp; <span class="desc">PTT umschalten</span></div>
<div class="ep"><span class="badge">GET</span><b>/mute/on</b> &nbsp;–&nbsp; <span class="desc">Stummschalten</span></div>
<div class="ep"><span class="badge">GET</span><b>/mute/off</b> &nbsp;–&nbsp; <span class="desc">Stummschaltung aufheben</span></div>
<div class="ep"><span class="badge">GET</span><b>/mute/toggle</b> &nbsp;–&nbsp; <span class="desc">Stummschaltung umschalten</span></div>
<div class="ep"><span class="badge">GET</span><b>/channel/&lt;name&gt;</b> &nbsp;–&nbsp; <span class="desc">Kanal nach Name beitreten</span></div>
<div class="ep"><span class="badge">GET</span><b>/status/&lt;text&gt;</b> &nbsp;–&nbsp; <span class="desc">Statusnachricht setzen</span></div>
<div class="ep"><span class="badge">GET</span><b>/speak/&lt;text&gt;</b> &nbsp;–&nbsp; <span class="desc">Text per TTS vorlesen</span></div>

<h2>Abfragen (GET)</h2>
<div class="ep"><span class="badge">GET</span><b>/info</b> &nbsp;–&nbsp; <span class="desc">App-Version, Verbindungsstatus, aktueller Kanal</span></div>
<div class="ep"><span class="badge">GET</span><b>/server</b> &nbsp;–&nbsp; <span class="desc">Serverinfo: Name, Host, verbunden, Nutzerzahl</span></div>
<div class="ep"><span class="badge">GET</span><b>/channels</b> &nbsp;–&nbsp; <span class="desc">Liste aller Kanäle mit ID, Name, Nutzerzahl</span></div>
<div class="ep"><span class="badge">GET</span><b>/users</b> &nbsp;–&nbsp; <span class="desc">Nutzer im aktuellen Kanal mit ID, Name, Status</span></div>

<h2>Chat (POST)</h2>
<div class="ep"><span class="badge post">POST</span><b>/chat</b> &nbsp;–&nbsp;
<span class="desc">Nachricht in aktuellen Kanal senden.<br>Body: <code>{"text": "Hallo Kanal!"}</code></span></div>

<h2>Events (SSE)</h2>
<div class="ep"><span class="badge">GET</span><b>/events/stream</b> &nbsp;–&nbsp;
<span class="desc">Server-Sent Events Stream. Events: <code>chat_message</code>, <code>user_joined</code>,
<code>user_left</code>, <code>channel_joined</code>, <code>connection_state_changed</code>,
<code>file_transfer_complete</code></span></div>

<h2>Antwortformat</h2>
<pre>{"ok": true, "result": ...}
{"ok": false, "error": "Fehlermeldung"}</pre>
</body>
</html>"""


def _push_sse_event(event_type: str, data: dict) -> None:
    """Fügt ein Event in alle aktiven SSE-Clients-Queues ein."""
    payload = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


def _check_auth(handler: "BaseHTTPRequestHandler") -> bool:
    """v4.3.0 – Prüft API-Token wenn konfiguriert. Gibt True wenn OK."""
    if not _api_token:
        return True  # kein Token konfiguriert → offen
    # Header
    header_token = handler.headers.get("X-Api-Token", "")
    if header_token == _api_token:
        return True
    # Query-Parameter
    parsed = urllib.parse.urlparse(handler.path)
    params = urllib.parse.parse_qs(parsed.query)
    query_token = params.get("token", [""])[0]
    if query_token == _api_token:
        return True
    return False


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass  # kein stdout-Spam

    def _send_unauthorized(self) -> None:
        body = json.dumps({"ok": False, "error": "Unauthorized"}).encode()
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not _check_auth(self):
            self._send_unauthorized()
            return
        parsed_path = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed_path.path.rstrip("/"))

        # OpenAPI-Doku
        if path == "/docs":
            body = _OPENAPI_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # SSE-Stream
        if path == "/events/stream":
            self._handle_sse()
            return
        try:
            result = self._dispatch(path)
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            self.send_response(200)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if not _check_auth(self):
            self._send_unauthorized()
            return
        parsed_path = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed_path.path.rstrip("/"))
        length = int(self.headers.get("Content-Length", 0) or 0)
        body_raw = self.rfile.read(length) if length > 0 else b""
        try:
            result = self._dispatch_post(path, body_raw)
            body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode()
            self.send_response(200)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self) -> None:
        """Hält die Verbindung als SSE-Stream offen und sendet Events."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        client_q: queue.Queue = queue.Queue(maxsize=64)
        with _sse_lock:
            _sse_clients.append(client_q)

        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
        except Exception:
            with _sse_lock:
                if client_q in _sse_clients:
                    _sse_clients.remove(client_q)
            return

        last_keepalive = time.time()
        try:
            while True:
                try:
                    payload = client_q.get(timeout=2.0)
                    self.wfile.write(payload.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    pass
                if time.time() - last_keepalive > _SSE_KEEPALIVE_S:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_keepalive = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _sse_lock:
                if client_q in _sse_clients:
                    _sse_clients.remove(client_q)

    def _dispatch(self, path: str) -> object:
        import wx
        f = _frame_ref
        if f is None:
            raise RuntimeError("App not ready")

        if path == "/ptt/on":
            wx.CallAfter(f.client.enable_voice_transmission, True)
            return "PTT on"
        if path == "/ptt/off":
            wx.CallAfter(f.client.enable_voice_transmission, False)
            return "PTT off"
        if path == "/ptt/toggle":
            wx.CallAfter(f._http_api_toggle_ptt)
            return "PTT toggled"
        if path == "/mute/on":
            wx.CallAfter(f.client.set_sound_output_mute, True)
            return "muted"
        if path == "/mute/off":
            wx.CallAfter(f.client.set_sound_output_mute, False)
            return "unmuted"
        if path == "/mute/toggle":
            wx.CallAfter(f._http_api_toggle_mute)
            return "mute toggled"
        if path.startswith("/channel/"):
            name = path[9:]
            wx.CallAfter(f._http_api_join_channel, name)
            return f"joining {name}"
        if path.startswith("/status/"):
            text = path[8:]
            wx.CallAfter(f.client.change_status, f._status_mode, text)
            return f"status set: {text}"
        if path.startswith("/speak/"):
            text = path[7:]
            wx.CallAfter(f.tts.speak, text, kind="system")
            return f"speaking: {text}"
        if path == "/info":
            return {
                "version": getattr(f, "_app_version", ""),
                "connected": f.client.is_connected(),
                "channel": getattr(f, "_current_server_key", ""),
            }

        # v4.3.0 – neue REST-Endpunkte
        if path == "/server":
            return self._get_server_info(f)
        if path == "/channels":
            return self._get_channels(f)
        if path == "/users":
            return self._get_users(f)

        raise ValueError(f"Unknown path: {path}")

    def _get_server_info(self, f) -> dict:
        """v4.3.0 – Serverinfo."""
        try:
            profile = getattr(f, "_current_profile", None)
            name = str(getattr(profile, "name", "") or "") if profile else ""
            host = str(getattr(profile, "host", "") or "") if profile else ""
            port = int(getattr(profile, "tcp_port", 0) or 0) if profile else 0
        except Exception:
            name = host = ""
            port = 0
        return {
            "server_name": name,
            "host": host,
            "port": port,
            "connected": f.client.is_connected(),
        }

    def _get_channels(self, f) -> list:
        """v4.3.0 – Kanalliste."""
        result = []
        try:
            channels = list(f.client.get_channels() or [])
            for ch in channels:
                try:
                    cid = int(ch.nChannelID)
                    cname = f.tt_str(ch.szName) or ""
                    result.append({"id": cid, "name": cname})
                except Exception:
                    pass
        except Exception:
            pass
        return result

    def _get_users(self, f) -> list:
        """v4.3.0 – Nutzer im aktuellen Kanal."""
        result = []
        try:
            ch_id = f.client.get_my_channel_id()
            if ch_id:
                users = list(f.client.get_channel_users(ch_id) or [])
                for u in users:
                    try:
                        uid = int(u.nUserID)
                        uname = f.tt_str(u.szNickname) or f.tt_str(u.szUsername) or ""
                        result.append({"id": uid, "name": uname})
                    except Exception:
                        pass
        except Exception:
            pass
        return result

    def _dispatch_post(self, path: str, body: bytes) -> object:
        import wx
        f = _frame_ref
        if f is None:
            raise RuntimeError("App not ready")
        if path == "/chat":
            data = json.loads(body.decode("utf-8")) if body else {}
            text = str(data.get("text", "")).strip()
            if not text:
                raise ValueError("'text' field required")
            ch_id = f.client.get_my_channel_id()
            if not ch_id:
                raise RuntimeError("Not in a channel")
            wx.CallAfter(f.client.send_channel_message, int(ch_id), text)
            return "message sent"
        raise ValueError(f"Unknown POST path: {path}")


class HttpApiServer:
    """Verwaltet den HTTP-Server-Thread."""

    def __init__(self, frame: "MainFrame") -> None:
        global _frame_ref
        _frame_ref = frame
        self._frame = frame
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._setup_bus_events(frame)

    def _setup_bus_events(self, frame: "MainFrame") -> None:
        """Abonniert Bus-Events und leitet sie als SSE-Events weiter."""
        try:
            bus = frame.bus
            bus.on("chat_message", lambda **kw: _push_sse_event("chat_message", _safe_dict(kw)))
            bus.on("user_joined", lambda **kw: _push_sse_event("user_joined", _safe_dict(kw)))
            bus.on("user_left", lambda **kw: _push_sse_event("user_left", _safe_dict(kw)))
            bus.on("channel_joined", lambda **kw: _push_sse_event("channel_joined", _safe_dict(kw)))
            bus.on("connection_state_changed", lambda **kw: _push_sse_event("connection_state_changed", _safe_dict(kw)))
            bus.on("file_transfer_complete", lambda **kw: _push_sse_event("file_transfer_complete", _safe_dict(kw)))
        except Exception:
            pass

    def set_token(self, token: Optional[str]) -> None:
        """v4.3.0 – Setzt den API-Authentifizierungstoken."""
        global _api_token
        _api_token = token.strip() if token else None

    def start(self, port: int = 8765) -> None:
        if self._server is not None:
            return
        try:
            self._server = HTTPServer(("127.0.0.1", port), _Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="HttpAPI",
                daemon=True,
            )
            self._thread.start()
            print(f"[HttpAPI v3] Läuft auf http://127.0.0.1:{port}  (Doku: /docs  SSE: /events/stream)")
        except Exception as exc:
            print(f"[HttpAPI] Start fehlgeschlagen: {exc}")
            self._server = None

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

    def push_event(self, event_type: str, data: dict) -> None:
        """Schiebt manuell ein Event in den SSE-Stream."""
        _push_sse_event(event_type, data)


def _safe_dict(kw: dict) -> dict:
    """Konvertiert Bus-Event-kwargs in JSON-serialisierbare Werte."""
    result = {}
    for k, v in kw.items():
        try:
            json.dumps(v)
            result[k] = v
        except (TypeError, ValueError):
            result[k] = str(v)
    return result
