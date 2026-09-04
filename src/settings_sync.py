"""Geräte-Sync im lokalen Netzwerk (v10.2.0).

Sicherheitsmodell:
- mDNS-Entdeckung (zeroconf) macht Geräte sichtbar, tauscht KEINE Daten aus.
- Kopplung erfordert expliziten 6-stelligen Code (TOTP-ähnlich, 2 Min. gültig).
- Dauerhaftes Geheimnis pro Geräte-Paar in OS-Keychain (via keychain.py).
- Sync-Nachrichten sind HMAC-SHA256-signiert – kein gültiges Geheimnis, keine Daten.
- Niemals synchronisiert: API-Keys, Passwörter, hardware-spezifische Einstellungen.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import platform
import secrets
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any

import keychain
from platform_paths import app_data_dir

# ── Keychain-Service-Name für Sync-Geheimnisse ─────────────────────────────
_SERVICE_SYNC = "TeamTalkVOClient-Sync"

# Felder, die synchronisiert werden dürfen (niemals API-Keys oder Passwörter)
_SYNCABLE_FIELDS = {
    "server_profiles",           # Serverprofile (ServerStore)
    "ptt_hotkey",
    "hotkey_mute_all",
    "hotkey_voice_activation",
    "hotkey_video_tx",
    "hotkey_announce_level",
    "hotkey_announce_user_info",
    "hotkey_announce_ping",
    "hotkey_reply_last_sender",
    "hotkey_cycle_sound_profile",
    "hotkey_cycle_braille_verbosity",
    "hotkey_ai_summary",
    "hotkey_bookmark_1",
    "hotkey_bookmark_2",
    "hotkey_bookmark_3",
    "hotkey_bookmark_4",
    "hotkey_bookmark_5",
    "hotkey_bookmark_6",
    "hotkey_bookmark_7",
    "hotkey_bookmark_8",
    "hotkey_bookmark_9",
    "hotkey_record_toggle",
    "hotkey_mic_boost_up",
    "hotkey_mic_boost_down",
    "hotkey_volume_up",
    "hotkey_volume_down",
    "hotkey_status_template_1",
    "hotkey_status_template_2",
    "hotkey_status_template_3",
    "hotkey_tts_cancel",
    "hotkey_announce_status",
    "hotkey_ai_reply_suggestions",
    "global_hotkeys_enabled",
    "global_hotkey_ptt",
    "global_hotkey_mute",
    "sound_events",
    "sound_profiles",
    "active_sound_profile",
    "tts_enabled",
    "tts_speak_chat",
    "tts_speak_private",
    "tts_speak_system",
    "tts_speak_own",
    "tts_interrupt",
    "tts_language",
    "tts_voice",
    "tts_rate",
    "tts_volume",
    "tts_speak_user_join",
    "tts_speak_user_leave",
    "tts_speak_who_speaks",
    "tts_speak_channel_topic",
    "tts_connect_announce",
    "tts_chat_rate",
    "tts_system_rate",
    "tts_channel_rate",
    "tts_chat_voice",
    "tts_system_voice",
    "tts_speak_kicked",
    "tts_speak_broadcast",
    "tts_speak_user_away",
    "tts_backend",
    "tts_speak_user_login",
    "tts_speak_file_event",
    "tts_speak_file_transfer",
    "tts_speak_channel_topic_on_join",
    "pronunciation_dict",
    "channel_bookmarks",
    "alert_keywords",
    "alert_keywords_tts",
    "status_templates",
    "auto_reply_enabled",
    "auto_reply_message",
    "chat_highlight_keywords",
    "chat_muted_users",
    "notification_rules",
}


# ── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _device_id() -> str:
    """Stabiler, geräte-eindeutiger Bezeichner (UUID basierend auf MAC-Adresse)."""
    return str(uuid.UUID(int=uuid.getnode()))


def _device_name() -> str:
    return platform.node() or socket.gethostname() or "Unbekanntes Gerät"


def _device_platform() -> str:
    return platform.system()  # Darwin / Windows / Linux


def _hmac_sign(secret: bytes, payload: bytes) -> str:
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def _hmac_verify(secret: bytes, payload: bytes, signature: str) -> bool:
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _send_framed(sock: socket.socket, data: bytes) -> None:
    """Schickt Daten mit 4-Byte-Längenprefix."""
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_framed(sock: socket.socket, timeout: float = 10.0) -> Optional[bytes]:
    """Empfängt eine gerahmte Nachricht. Gibt None bei Fehler/Timeout zurück."""
    sock.settimeout(timeout)
    try:
        raw_len = _recvall(sock, 4)
        if raw_len is None:
            return None
        length = struct.unpack(">I", raw_len)[0]
        if length > 10 * 1024 * 1024:  # Schutz vor zu großen Nachrichten
            return None
        return _recvall(sock, length)
    except Exception:
        return None


def _recvall(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except Exception:
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


# ── Datenklassen ────────────────────────────────────────────────────────────

@dataclass
class PairedDevice:
    device_id: str
    name: str
    platform: str
    last_sync: float = 0.0       # Unix-Timestamp des letzten Syncs


@dataclass
class DeviceList:
    devices: List[PairedDevice] = field(default_factory=list)

    def find(self, device_id: str) -> Optional[PairedDevice]:
        for d in self.devices:
            if d.device_id == device_id:
                return d
        return None

    def remove(self, device_id: str) -> None:
        self.devices = [d for d in self.devices if d.device_id != device_id]

    def upsert(self, dev: PairedDevice) -> None:
        self.remove(dev.device_id)
        self.devices.append(dev)


class DeviceStore:
    """Persistiert die Liste gekoppelter Geräte als JSON."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._list = DeviceList()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._list.devices = [
                PairedDevice(**d) for d in data.get("devices", [])
            ]
        except Exception:
            self._list = DeviceList()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"devices": [asdict(d) for d in self._list.devices]}
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def all(self) -> List[PairedDevice]:
        return list(self._list.devices)

    def find(self, device_id: str) -> Optional[PairedDevice]:
        return self._list.find(device_id)

    def upsert(self, dev: PairedDevice) -> None:
        self._list.upsert(dev)
        self._save()

    def remove(self, device_id: str) -> None:
        self._list.remove(device_id)
        self._save()


# ── Keychain-Hilfsfunktionen ─────────────────────────────────────────────────

def _secret_key(peer_id: str) -> str:
    return f"sync_secret::{peer_id}"


def save_sync_secret(peer_id: str, secret_hex: str) -> bool:
    kr = keychain._kr()
    if kr is None:
        return False
    try:
        kr.set_password(_SERVICE_SYNC, _secret_key(peer_id), secret_hex)
        return True
    except Exception:
        return False


def load_sync_secret(peer_id: str) -> Optional[str]:
    kr = keychain._kr()
    if kr is None:
        return None
    try:
        return kr.get_password(_SERVICE_SYNC, _secret_key(peer_id))
    except Exception:
        return None


def delete_sync_secret(peer_id: str) -> None:
    kr = keychain._kr()
    if kr is None:
        return
    try:
        kr.delete_password(_SERVICE_SYNC, _secret_key(peer_id))
    except Exception:
        pass


# ── Kopplung ─────────────────────────────────────────────────────────────────

class PairingServer:
    """Lauscht auf einem zufälligen TCP-Port und führt die Kopplung als Server durch.

    Protokoll:
    1. A (Server) sendet: {"type": "hello", "device_id": ..., "name": ..., "platform": ...}
    2. B (Client) sendet: {"type": "code", "code": "<6 Ziffern>"}
    3. A prüft Code (HMAC-SHA256 des ephemeren Schlüssels, 6 Ziffern, Zeitfenster 120 s).
    4. A sendet: {"type": "ok", "device_id": ..., "name": ..., "platform": ...}
       oder:     {"type": "error", "reason": "..."}
    5. Beide Seiten generieren dauerhaftes Geheimnis und speichern es.
    """

    def __init__(self, on_paired: Callable[[PairedDevice], None]) -> None:
        self._on_paired = on_paired
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._ephemeral_key = secrets.token_bytes(16)
        self._start_time = time.time()
        self._port = 0
        self._code = self._generate_code()
        self._done = threading.Event()

    def _generate_code(self) -> str:
        """Erzeuge 6-stelligen Code aus HMAC des ephemeren Schlüssels + Zeitstempel-Fenster."""
        window = int(self._start_time / 120)  # 2-Minuten-Fenster
        msg = struct.pack(">Q", window)
        digest = hmac.new(self._ephemeral_key, msg, hashlib.sha256).digest()
        code_int = int.from_bytes(digest[:4], "big") % 1_000_000
        return f"{code_int:06d}"

    @property
    def code(self) -> str:
        return self._code

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", 0))
        self._port = self._sock.getsockname()[1]
        self._sock.listen(1)
        self._sock.settimeout(130.0)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            conn, _ = self._sock.accept()
        except Exception:
            return
        try:
            self._handle(conn)
        finally:
            conn.close()
            self._sock.close()

    def _verify_code(self, provided: str) -> bool:
        now = time.time()
        for window_offset in (0, -1):  # aktuelles und vorheriges Fenster prüfen
            window = int((now + window_offset * 120) / 120)
            msg = struct.pack(">Q", window)
            digest = hmac.new(self._ephemeral_key, msg, hashlib.sha256).digest()
            expected = f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"
            if hmac.compare_digest(expected, provided):
                return True
        return False

    def _handle(self, conn: socket.socket) -> None:
        hello = json.dumps({
            "type": "hello",
            "device_id": _device_id(),
            "name": _device_name(),
            "platform": _device_platform(),
        }).encode("utf-8")
        _send_framed(conn, hello)

        raw = _recv_framed(conn)
        if raw is None:
            return
        try:
            msg = json.loads(raw.decode("utf-8"))
        except Exception:
            return

        if msg.get("type") != "code":
            return

        provided = str(msg.get("code", ""))
        if not self._verify_code(provided):
            err = json.dumps({"type": "error", "reason": "Ungültiger Code"}).encode("utf-8")
            _send_framed(conn, err)
            return

        # Code korrekt → dauerhaftes Geheimnis erzeugen und austauschen
        shared_secret = secrets.token_hex(32)
        peer_id = str(msg.get("peer_device_id", ""))
        peer_name = str(msg.get("peer_name", "Unbekannt"))
        peer_platform = str(msg.get("peer_platform", ""))

        ok = json.dumps({
            "type": "ok",
            "device_id": _device_id(),
            "name": _device_name(),
            "platform": _device_platform(),
            "shared_secret": shared_secret,
        }).encode("utf-8")
        _send_framed(conn, ok)

        if peer_id:
            save_sync_secret(peer_id, shared_secret)
            dev = PairedDevice(
                device_id=peer_id,
                name=peer_name,
                platform=peer_platform,
            )
            self._on_paired(dev)
        self._done.set()

    def stop(self) -> None:
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass


class PairingClient:
    """Verbindet sich zu einem PairingServer und gibt den Code ein."""

    def pair(
        self,
        host: str,
        port: int,
        code: str,
        on_success: Callable[[PairedDevice, str], None],
        on_error: Callable[[str], None],
    ) -> None:
        threading.Thread(
            target=self._run, args=(host, port, code, on_success, on_error), daemon=True
        ).start()

    def _run(
        self,
        host: str,
        port: int,
        code: str,
        on_success: Callable[[PairedDevice, str], None],
        on_error: Callable[[str], None],
    ) -> None:
        try:
            sock = socket.create_connection((host, port), timeout=15.0)
        except Exception as exc:
            on_error(f"Verbindung fehlgeschlagen: {exc}")
            return
        try:
            raw = _recv_framed(sock)
            if raw is None:
                on_error("Keine Antwort vom Gerät")
                return
            hello = json.loads(raw.decode("utf-8"))
            if hello.get("type") != "hello":
                on_error("Unerwartetes Protokoll")
                return

            msg = json.dumps({
                "type": "code",
                "code": code.strip(),
                "peer_device_id": _device_id(),
                "peer_name": _device_name(),
                "peer_platform": _device_platform(),
            }).encode("utf-8")
            _send_framed(sock, msg)

            raw2 = _recv_framed(sock)
            if raw2 is None:
                on_error("Keine Antwort nach Code-Eingabe")
                return
            resp = json.loads(raw2.decode("utf-8"))

            if resp.get("type") == "error":
                on_error(resp.get("reason", "Unbekannter Fehler"))
                return

            if resp.get("type") != "ok":
                on_error("Unerwartete Antwort")
                return

            peer_id = str(resp["device_id"])
            shared_secret = str(resp["shared_secret"])
            save_sync_secret(peer_id, shared_secret)
            dev = PairedDevice(
                device_id=peer_id,
                name=str(resp.get("name", "Unbekannt")),
                platform=str(resp.get("platform", "")),
            )
            on_success(dev, shared_secret)
        except Exception as exc:
            on_error(f"Fehler beim Koppeln: {exc}")
        finally:
            sock.close()


# ── mDNS-Discovery (zeroconf) ─────────────────────────────────────────────

_MDNS_SERVICE_TYPE = "_ttvocsync._tcp.local."


class SyncDiscovery:
    """Registriert das eigene Gerät per mDNS und entdeckt gekoppelte Geräte."""

    def __init__(self, port: int, device_store: DeviceStore) -> None:
        self._port = port
        self._store = device_store
        self._zc = None
        self._info = None
        self._browser = None
        self._discovered: Dict[str, str] = {}  # device_id → host
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            from zeroconf import Zeroconf, ServiceInfo, ServiceBrowser
            import socket as _socket
            self._zc = Zeroconf()
            host_ip = _socket.gethostbyname(_socket.gethostname())
            dev_id = _device_id()
            self._info = ServiceInfo(
                _MDNS_SERVICE_TYPE,
                f"{dev_id}.{_MDNS_SERVICE_TYPE}",
                addresses=[_socket.inet_aton(host_ip)],
                port=self._port,
                properties={"device_id": dev_id, "name": _device_name()},
            )
            self._zc.register_service(self._info)
            self._browser = ServiceBrowser(self._zc, _MDNS_SERVICE_TYPE, self)
        except Exception:
            pass

    def remove_service(self, zc, type_, name):
        pass

    def add_service(self, zc, type_, name):
        try:
            from zeroconf import ServiceInfo
            info = zc.get_service_info(type_, name)
            if info is None:
                return
            props = {k.decode() if isinstance(k, bytes) else k:
                     v.decode() if isinstance(v, bytes) else v
                     for k, v in (info.properties or {}).items()}
            peer_id = props.get("device_id", "")
            if not peer_id or peer_id == _device_id():
                return
            # Nur sichtbar machen, wenn bereits gekoppelt
            if self._store.find(peer_id) is not None:
                import socket as _socket
                addr = _socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
                with self._lock:
                    self._discovered[peer_id] = addr
        except Exception:
            pass

    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)

    def get_address(self, device_id: str) -> Optional[str]:
        with self._lock:
            return self._discovered.get(device_id)

    def stop(self) -> None:
        try:
            if self._zc and self._info:
                self._zc.unregister_service(self._info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass


# ── Sync-Protokoll ────────────────────────────────────────────────────────

class SyncChannel:
    """Führt einen authentifizierten Datenaustausch mit einem gekoppelten Gerät durch.

    Protokoll (TCP, JSON, HMAC-signiert):
    1. Sender öffnet Verbindung.
    2. Sender schickt: {"msg": <payload_json_str>, "sig": <hmac_hex>}
    3. Empfänger prüft Signatur, verarbeitet Payload.
    4. Empfänger antwortet: {"msg": ..., "sig": ...} mit ack/data.
    """

    def push(
        self,
        host: str,
        port: int,
        peer_id: str,
        payload: Dict[str, Any],
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        threading.Thread(
            target=self._push_run,
            args=(host, port, peer_id, payload, on_done),
            daemon=True,
        ).start()

    def _push_run(
        self,
        host: str,
        port: int,
        peer_id: str,
        payload: Dict[str, Any],
        on_done: Optional[Callable[[bool, str], None]],
    ) -> None:
        secret_hex = load_sync_secret(peer_id)
        if not secret_hex:
            if on_done:
                on_done(False, "Kein Geheimnis für dieses Gerät")
            return
        secret = bytes.fromhex(secret_hex)
        try:
            sock = socket.create_connection((host, port), timeout=15.0)
        except Exception as exc:
            if on_done:
                on_done(False, f"Verbindung fehlgeschlagen: {exc}")
            return
        try:
            # Schritt 1: Identifikation senden
            ident = json.dumps({"device_id": _device_id()}).encode("utf-8")
            _send_framed(sock, ident)

            # Schritt 2: Ident-Ack empfangen
            raw_ack = _recv_framed(sock, timeout=10.0)
            if raw_ack is None:
                if on_done:
                    on_done(False, "Keine Ident-Antwort")
                return
            ack = json.loads(raw_ack.decode("utf-8"))
            if ack.get("type") != "ident_ok":
                if on_done:
                    on_done(False, "Identifikation abgelehnt")
                return

            # Schritt 3: HMAC-signiertes Payload senden
            payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            sig = _hmac_sign(secret, payload_bytes)
            envelope = json.dumps({"msg": payload_bytes.decode("utf-8"), "sig": sig}).encode("utf-8")
            _send_framed(sock, envelope)

            raw = _recv_framed(sock, timeout=15.0)
            if raw is None:
                if on_done:
                    on_done(False, "Keine Antwort")
                return
            resp = json.loads(raw.decode("utf-8"))
            success = resp.get("type") == "ack"
            msg = resp.get("msg", "OK" if success else "Unbekannter Fehler")
            if on_done:
                on_done(success, msg)
        except Exception as exc:
            if on_done:
                on_done(False, str(exc))
        finally:
            sock.close()

    def handle_incoming(
        self, conn: socket.socket, peer_id: str
    ) -> Optional[Dict[str, Any]]:
        """Prüft Signatur und gibt dekodierten Payload zurück oder None bei Fehler."""
        secret_hex = load_sync_secret(peer_id)
        if not secret_hex:
            return None
        secret = bytes.fromhex(secret_hex)
        raw = _recv_framed(conn, timeout=10.0)
        if raw is None:
            return None
        try:
            envelope = json.loads(raw.decode("utf-8"))
            msg_str = envelope["msg"]
            sig = envelope["sig"]
        except Exception:
            return None
        if not _hmac_verify(secret, msg_str.encode("utf-8"), sig):
            return None
        try:
            return json.loads(msg_str)
        except Exception:
            return None


# ── Sync-Listener ─────────────────────────────────────────────────────────

class SyncListener:
    """Hört auf eingehende Sync-Verbindungen und verarbeitet sie."""

    def __init__(
        self,
        port: int,
        device_store: DeviceStore,
        on_sync_received: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        self._port = port
        self._store = device_store
        self._on_sync = on_sync_received
        self._sock: Optional[socket.socket] = None
        self._running = False

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", self._port))
        self._sock.listen(5)
        self._sock.settimeout(1.0)
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        channel = SyncChannel()
        while self._running:
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            threading.Thread(
                target=self._handle, args=(conn, addr, channel), daemon=True
            ).start()

    def _handle(self, conn: socket.socket, addr, channel: SyncChannel) -> None:
        try:
            # Identify sender: first handshake message contains peer_id
            raw = _recv_framed(conn, timeout=5.0)
            if raw is None:
                return
            try:
                ident = json.loads(raw.decode("utf-8"))
                peer_id = str(ident.get("device_id", ""))
            except Exception:
                return

            if not peer_id or self._store.find(peer_id) is None:
                return  # Unbekanntes Gerät – kommentarlos ablehnen

            # Schicke Ack für Identifikation
            _send_framed(conn, json.dumps({"type": "ident_ok"}).encode("utf-8"))

            payload = channel.handle_incoming(conn, peer_id)
            if payload is None:
                _send_framed(conn, json.dumps({"type": "error", "msg": "Authentifizierung fehlgeschlagen"}).encode("utf-8"))
                return

            _send_framed(conn, json.dumps({"type": "ack", "msg": "OK"}).encode("utf-8"))
            self._on_sync(peer_id, payload)
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self) -> None:
        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    @property
    def port(self) -> int:
        return self._port


# ── Hauptklasse ───────────────────────────────────────────────────────────

_SYNC_PORT = 19882  # Fester Port für den Sync-Listener


class SettingsSyncManager:
    """Verwaltet Geräte-Kopplung, Entdeckung und Einstellungs-Sync.

    Verwendung:
        mgr = SettingsSyncManager(settings_store, server_store, bus)
        mgr.start()
        # Kopplung initiieren:
        server = mgr.start_pairing()
        print(server.code)  # 6-stelligen Code anzeigen
        # Auf anderem Gerät:
        mgr.pair_with(host, port, code)
    """

    def __init__(self, settings_store, server_store=None, bus=None) -> None:
        self._settings_store = settings_store
        self._server_store = server_store
        self._bus = bus
        data_dir = app_data_dir()
        self._device_store = DeviceStore(data_dir / "sync_devices.json")
        self._listener: Optional[SyncListener] = None
        self._discovery: Optional[SyncDiscovery] = None
        self._pairing_server: Optional[PairingServer] = None
        self._sync_what: Dict[str, bool] = {
            "server_profiles": True,
            "hotkeys": True,
            "tts": True,
            "sound": True,
            "notifications": True,
        }

    # ── Lebenszyklus ──────────────────────────────────────────────────────

    def start(self) -> None:
        self._listener = SyncListener(
            _SYNC_PORT, self._device_store, self._on_sync_received
        )
        self._listener.start()
        self._discovery = SyncDiscovery(_SYNC_PORT, self._device_store)
        self._discovery.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
        if self._discovery:
            self._discovery.stop()
        if self._pairing_server:
            self._pairing_server.stop()

    # ── Kopplung ──────────────────────────────────────────────────────────

    def start_pairing(self) -> PairingServer:
        """Startet den Kopplung-Server und gibt ihn zurück (Code über .code abrufbar)."""
        self._pairing_server = PairingServer(on_paired=self._on_paired)
        self._pairing_server.start()
        return self._pairing_server

    def pair_with(
        self,
        host: str,
        port: int,
        code: str,
        on_success: Callable[[PairedDevice], None],
        on_error: Callable[[str], None],
    ) -> None:
        """Verbindet sich mit einem Kopplung-Server und gibt den Code ein."""
        def _success(dev: PairedDevice, _secret: str) -> None:
            self._device_store.upsert(dev)
            if self._bus:
                self._bus.emit("sync_paired", device=dev)
            on_success(dev)

        client = PairingClient()
        client.pair(host, port, code, _success, on_error)

    def unpair(self, device_id: str) -> None:
        """Hebt die Kopplung mit einem Gerät auf."""
        self._device_store.remove(device_id)
        delete_sync_secret(device_id)
        if self._bus:
            self._bus.emit("sync_unpaired", device_id=device_id)

    def _on_paired(self, dev: PairedDevice) -> None:
        self._device_store.upsert(dev)
        if self._bus:
            self._bus.emit("sync_paired", device=dev)

    # ── Geräteliste ───────────────────────────────────────────────────────

    def paired_devices(self) -> List[PairedDevice]:
        return self._device_store.all()

    # ── Sync ausführen ────────────────────────────────────────────────────

    def sync_all(
        self,
        on_done: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Synchronisiert mit allen gekoppelten, erreichbaren Geräten.

        Ruft on_done(success_count, total_count) auf wenn abgeschlossen.
        """
        devices = self._device_store.all()
        if not devices:
            if on_done:
                on_done(0, 0)
            return

        payload = self._build_sync_payload()
        total = len(devices)
        results: List[bool] = []
        done_event = threading.Event()

        def _check_done(ok: bool, _msg: str) -> None:
            results.append(ok)
            if len(results) >= total:
                done_event.set()
                if on_done:
                    on_done(sum(results), total)

        channel = SyncChannel()
        for dev in devices:
            host = self._resolve_host(dev.device_id)
            if not host:
                _check_done(False, "Nicht erreichbar")
                continue
            channel.push(host, _SYNC_PORT, dev.device_id, payload, _check_done)

    def sync_with(
        self,
        device_id: str,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Synchronisiert mit einem bestimmten Gerät."""
        dev = self._device_store.find(device_id)
        if dev is None:
            if on_done:
                on_done(False, "Gerät nicht gefunden")
            return
        host = self._resolve_host(device_id)
        if not host:
            if on_done:
                on_done(False, "Gerät nicht erreichbar")
            return
        payload = self._build_sync_payload()
        SyncChannel().push(host, _SYNC_PORT, device_id, payload, on_done)

    def _resolve_host(self, device_id: str) -> Optional[str]:
        if self._discovery:
            return self._discovery.get_address(device_id)
        return None

    # ── Payload-Aufbau ────────────────────────────────────────────────────

    def _build_sync_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "version": 1,
            "sender_id": _device_id(),
            "timestamp": time.time(),
            "what": self._sync_what,
        }
        s = self._settings_store.settings

        if self._sync_what.get("hotkeys"):
            hotkeys = {}
            for field_name in _SYNCABLE_FIELDS:
                if field_name.startswith("hotkey") or field_name in ("ptt_hotkey", "global_hotkeys_enabled", "global_hotkey_ptt", "global_hotkey_mute"):
                    val = getattr(s, field_name, None)
                    if val is not None:
                        hotkeys[field_name] = val
            payload["hotkeys"] = hotkeys

        if self._sync_what.get("tts"):
            tts_fields = {
                f: getattr(s, f, None)
                for f in _SYNCABLE_FIELDS
                if f.startswith("tts_") or f == "pronunciation_dict"
            }
            payload["tts"] = {k: v for k, v in tts_fields.items() if v is not None}

        if self._sync_what.get("sound"):
            payload["sound"] = {
                "sound_events": dict(getattr(s, "sound_events", {}) or {}),
                "sound_profiles": list(getattr(s, "sound_profiles", []) or []),
                "active_sound_profile": str(getattr(s, "active_sound_profile", "Standard") or "Standard"),
            }

        if self._sync_what.get("notifications"):
            payload["notifications"] = {
                "alert_keywords": list(getattr(s, "alert_keywords", []) or []),
                "alert_keywords_tts": bool(getattr(s, "alert_keywords_tts", True)),
                "notification_rules": list(getattr(s, "notification_rules", []) or []),
            }

        if self._sync_what.get("server_profiles") and self._server_store:
            try:
                from dataclasses import asdict as _asdict
                profiles = []
                for p in self._server_store.items():
                    d = _asdict(p)
                    # Passwörter niemals synchronisieren
                    d.pop("password", None)
                    d.pop("channel_password", None)
                    profiles.append(d)
                payload["server_profiles"] = profiles
            except Exception:
                pass

        payload["channel_bookmarks"] = list(getattr(s, "channel_bookmarks", []) or [])
        payload["status_templates"] = list(getattr(s, "status_templates", []) or [])

        return payload

    # ── Eingehenden Sync verarbeiten ──────────────────────────────────────

    def _on_sync_received(self, peer_id: str, payload: Dict[str, Any]) -> None:
        """Verarbeitet empfangene Sync-Daten (Last-Write-Wins)."""
        remote_ts = float(payload.get("timestamp", 0))
        local_ts = time.time()

        # Nur übernehmen wenn Remote-Zeitstempel nicht zu alt (max. 5 Minuten Abweichung)
        if abs(local_ts - remote_ts) > 300:
            return

        s = self._settings_store.settings
        changed = False

        if "hotkeys" in payload:
            for field_name, value in payload["hotkeys"].items():
                if field_name in _SYNCABLE_FIELDS and hasattr(s, field_name):
                    setattr(s, field_name, value)
                    changed = True

        if "tts" in payload:
            for field_name, value in payload["tts"].items():
                if field_name in _SYNCABLE_FIELDS and hasattr(s, field_name):
                    setattr(s, field_name, value)
                    changed = True

        if "sound" in payload:
            sd = payload["sound"]
            if "sound_events" in sd:
                s.sound_events = dict(sd["sound_events"])
                changed = True
            if "sound_profiles" in sd:
                s.sound_profiles = list(sd["sound_profiles"])
                changed = True
            if "active_sound_profile" in sd:
                s.active_sound_profile = str(sd["active_sound_profile"])
                changed = True

        if "notifications" in payload:
            nd = payload["notifications"]
            if "alert_keywords" in nd:
                s.alert_keywords = list(nd["alert_keywords"])
                changed = True
            if "alert_keywords_tts" in nd:
                s.alert_keywords_tts = bool(nd["alert_keywords_tts"])
                changed = True
            if "notification_rules" in nd:
                s.notification_rules = list(nd["notification_rules"])
                changed = True

        if "channel_bookmarks" in payload:
            s.channel_bookmarks = list(payload["channel_bookmarks"])
            changed = True

        if "status_templates" in payload:
            s.status_templates = list(payload["status_templates"])
            changed = True

        if "server_profiles" in payload and self._server_store:
            try:
                from ui.models import ServerProfile
                from dataclasses import fields as _fields
                valid_names = {f.name for f in _fields(ServerProfile)}
                existing_hosts = {
                    f"{p.host}:{p.tcp_port}" for p in self._server_store.items()
                }
                for pd in payload["server_profiles"]:
                    filtered = {k: v for k, v in pd.items() if k in valid_names}
                    filtered.pop("password", None)
                    filtered.pop("channel_password", None)
                    key = f"{filtered.get('host', '')}:{filtered.get('tcp_port', 0)}"
                    if key not in existing_hosts:
                        try:
                            self._server_store.add(ServerProfile(**filtered))
                        except Exception:
                            pass
                changed = True
            except Exception:
                pass

        if changed:
            self._settings_store.save()
            # Letzten Sync-Zeitstempel des Geräts aktualisieren
            dev = self._device_store.find(peer_id)
            if dev:
                dev.last_sync = time.time()
                self._device_store.upsert(dev)
            if self._bus:
                self._bus.emit("sync_completed", peer_id=peer_id)

    # ── Sync-Auswahl ──────────────────────────────────────────────────────

    def set_sync_what(self, what: Dict[str, bool]) -> None:
        self._sync_what.update(what)
