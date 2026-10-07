"""Verschlüsseltes Einstellungs-Backup (Export/Import als eine Datei).

Sichert die Einstellungs- und Profildateien aus dem App-Datenordner
(``settings.db`` samt Serverprofilen, Plugin-Einstellungen und weitere
``.json``/``.txt``-Dateien direkt im Ordner) in eine passwortgeschützte
Datei (``.ttbackup``). Unabhängig vom Geräte-Sync, für manuelles Backup oder
Rechnerwechsel.

Format (JSON):
    {"format": "ttvoclient-backup", "version": 1,
     "kdf": {"name": "scrypt", "n": 32768, "r": 8, "p": 1, "salt": b64},
     "cipher": "AES-256-GCM", "nonce": b64, "data": b64}
``data`` ist ein mit AES-256-GCM verschlüsseltes ZIP mit ``manifest.json``
und den Dateien; der Kopf (ohne ``data``) ist als zusätzliche authentifizierte
Daten gebunden, eine Manipulation fällt also beim Entschlüsseln auf.

Wiederherstellen in zwei Schritten, damit die laufende App den
wiederhergestellten Stand nicht beim Beenden wieder überschreibt:
``stage_restore`` legt die Dateien in ``restore_pending/`` ab, die App startet
neu, und ``apply_pending_restore`` übernimmt sie beim nächsten Start, bevor
``settings.db`` geöffnet wird. Der vorherige Stand bleibt in
``before_restore_<Zeit>/`` erhalten.

Nicht enthalten: Chat-Verläufe (Unterordner) und Passwörter, die im
Schlüsselbund (Keychain) liegen.
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

FORMAT_NAME = "ttvoclient-backup"
FORMAT_VERSION = 1
BACKUP_EXTENSION = ".ttbackup"
MIN_PASSWORD_LENGTH = 6

ALLOWED_SUFFIXES = (".db", ".json", ".txt")
PENDING_DIR = "restore_pending"
BEFORE_RESTORE_PREFIX = "before_restore_"
KEEP_BEFORE_RESTORE = 3

# Einstellungen mit Geheimnissen (app_settings in settings.db / settings.json)
SECRET_SETTING_KEYS = (
    "bearware_password",
    "elevenlabs_api_key",
    "claude_api_key",
    "gemini_api_key",
    "channel_password_index",
    "webhook_url",
)
# Felder eines Serverprofils mit Geheimnissen
SERVER_SECRET_FIELDS = ("password", "channel_password", "elevenlabs_api_key")
# Plugin-Einstellungen, deren Schlüssel so heißen, gelten als geheim
_PLUGIN_SECRET_HINTS = ("pass", "token", "secret", "api_key", "apikey")

_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1


class BackupError(Exception):
    """Fehler mit Grund: "wrong_password", "invalid", "no_crypto", "password_short"."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason


@dataclass
class BackupContents:
    manifest: Dict
    files: Dict[str, bytes] = field(default_factory=dict)
    encrypted: bool = True

    @property
    def secrets_included(self) -> bool:
        return bool(self.manifest.get("secrets_included", True))

    @property
    def created(self) -> str:
        return str(self.manifest.get("created", ""))

    @property
    def app_version(self) -> str:
        return str(self.manifest.get("app_version", ""))


# ---------------------------------------------------------------------------
# Dateien sammeln / Geheimnisse entfernen
# ---------------------------------------------------------------------------

def is_allowed_name(name: str) -> bool:
    """Nur einfache Dateinamen direkt im Datenordner (kein Pfad, keine
    versteckten Dateien) mit erlaubter Endung."""
    if not name or name != os.path.basename(name) or "/" in name or "\\" in name:
        return False
    if name.startswith(".") or name in (".", ".."):
        return False
    return name.lower().endswith(ALLOWED_SUFFIXES)


def _snapshot_sqlite(path: Path) -> bytes:
    """Konsistente Kopie einer (evtl. gerade geöffneten) SQLite-Datei."""
    with tempfile.TemporaryDirectory() as tmp:
        dst_path = Path(tmp) / "snap.db"
        src = sqlite3.connect(str(path))
        try:
            dst = sqlite3.connect(str(dst_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        return dst_path.read_bytes()


def collect_files(app_dir: Path) -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    if not app_dir.is_dir():
        return files
    for f in sorted(app_dir.iterdir()):
        if not f.is_file() or not is_allowed_name(f.name):
            continue
        if f.suffix.lower() == ".db":
            files[f.name] = _snapshot_sqlite(f)
        else:
            files[f.name] = f.read_bytes()
    return files


def _is_secret_plugin_key(key: str) -> bool:
    k = str(key or "").lower()
    return any(h in k for h in _PLUGIN_SECRET_HINTS)


def _strip_db(data: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.db"
        p.write_bytes(data)
        conn = sqlite3.connect(str(p))
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "app_settings" in tables:
                for key in SECRET_SETTING_KEYS:
                    empty = "[]" if key == "channel_password_index" else json.dumps("")
                    conn.execute("UPDATE app_settings SET value=? WHERE key=?", (empty, key))
            if "server_profiles" in tables:
                for row_id, raw in conn.execute("SELECT id, data FROM server_profiles").fetchall():
                    try:
                        prof = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(prof, dict):
                        for fld in SERVER_SECRET_FIELDS:
                            if fld in prof:
                                prof[fld] = ""
                        conn.execute("UPDATE server_profiles SET data=? WHERE id=?", (json.dumps(prof), row_id))
            if "plugin_settings" in tables:
                for name, key in conn.execute("SELECT plugin_name, key FROM plugin_settings").fetchall():
                    if _is_secret_plugin_key(key):
                        conn.execute(
                            "UPDATE plugin_settings SET value_json=? WHERE plugin_name=? AND key=?",
                            (json.dumps(""), name, key),
                        )
            conn.commit()
            conn.execute("VACUUM")  # gelöschte Werte nicht im freien Speicher lassen
        finally:
            conn.close()
        return p.read_bytes()


def _strip_json(name: str, data: bytes) -> bytes:
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception:
        return data
    if isinstance(obj, dict):
        for key in SECRET_SETTING_KEYS:
            if key in obj:
                obj[key] = [] if key == "channel_password_index" else ""
    elif isinstance(obj, list):  # servers.json
        for prof in obj:
            if isinstance(prof, dict):
                for fld in SERVER_SECRET_FIELDS:
                    if fld in prof:
                        prof[fld] = ""
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def strip_secrets(files: Dict[str, bytes]) -> Dict[str, bytes]:
    out: Dict[str, bytes] = {}
    for name, data in files.items():
        low = name.lower()
        if low.endswith(".db"):
            out[name] = _strip_db(data)
        elif low.endswith(".json"):
            out[name] = _strip_json(name, data)
        else:
            out[name] = data
    return out


# ---------------------------------------------------------------------------
# Verschlüsselung
# ---------------------------------------------------------------------------

def _crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        from cryptography.exceptions import InvalidTag
    except Exception as exc:  # pragma: no cover - nur ohne Abhängigkeit
        raise BackupError("no_crypto", str(exc))
    return AESGCM, Scrypt, InvalidTag


def _derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    _AESGCM, Scrypt, _InvalidTag = _crypto()
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(password.encode("utf-8"))


def _aad(header: Dict) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _zip(manifest: Dict, files: Dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, data in sorted(files.items()):
            zf.writestr(name, data)
    return buf.getvalue()


def _unzip(data: bytes) -> BackupContents:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BackupError("invalid", str(exc))
    with zf:
        names = zf.namelist()
        manifest: Dict = {}
        if "manifest.json" in names:
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except Exception:
                manifest = {}
        files = {n: zf.read(n) for n in names if n != "manifest.json" and is_allowed_name(n)}
    if not isinstance(manifest, dict):
        manifest = {}
    manifest.setdefault("files", sorted(files))
    return BackupContents(manifest=manifest, files=files)


def create_backup(
    app_dir: Path,
    password: str,
    include_secrets: bool,
    app_version: str = "",
    now: Optional[datetime] = None,
    files: Optional[Dict[str, bytes]] = None,
) -> bytes:
    """Erzeugt den Inhalt einer ``.ttbackup``-Datei."""
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise BackupError("password_short")
    AESGCM, _Scrypt, _InvalidTag = _crypto()
    if files is None:
        files = collect_files(app_dir)
    if not include_secrets:
        files = strip_secrets(files)
    manifest = {
        "app_version": app_version,
        "created": (now or datetime.now()).isoformat(timespec="seconds"),
        "secrets_included": bool(include_secrets),
        "files": sorted(files),
    }
    plain = _zip(manifest, files)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "kdf": {"name": "scrypt", "n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P, "salt": _b64(salt)},
        "cipher": "AES-256-GCM",
        "nonce": _b64(nonce),
    }
    key = _derive_key(password, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    cipher = AESGCM(key).encrypt(nonce, plain, _aad(header))
    doc = dict(header)
    doc["data"] = _b64(cipher)
    return json.dumps(doc).encode("utf-8")


def is_encrypted_backup(data: bytes) -> bool:
    head = data[:200].lstrip()
    return head.startswith(b"{") and FORMAT_NAME.encode() in data[:400]


def read_backup(data: bytes, password: str = "") -> BackupContents:
    """Liest eine ``.ttbackup``-Datei (Passwort nötig) oder ein altes,
    unverschlüsseltes ZIP-Backup früherer Versionen (ohne Passwort)."""
    if not is_encrypted_backup(data):
        if data[:2] == b"PK":
            contents = _unzip(data)
            contents.encrypted = False
            contents.manifest.setdefault("secrets_included", True)
            return contents
        raise BackupError("invalid", "unbekanntes Dateiformat")
    AESGCM, _Scrypt, InvalidTag = _crypto()
    try:
        doc = json.loads(data.decode("utf-8"))
        if doc.get("format") != FORMAT_NAME or int(doc.get("version", 0)) > FORMAT_VERSION:
            raise BackupError("invalid", "nicht unterstützte Backup-Version")
        header = {k: doc[k] for k in ("format", "version", "kdf", "cipher", "nonce")}
        kdf = header["kdf"]
        salt = base64.b64decode(kdf["salt"])
        nonce = base64.b64decode(header["nonce"])
        cipher = base64.b64decode(doc["data"])
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("invalid", str(exc))
    if n > 2 ** 20 or r > 32 or p > 16:  # keine Speicher-Bombe aus fremden Dateien
        raise BackupError("invalid", "ungültige Schlüsselparameter")
    key = _derive_key(password or "", salt, n, r, p)
    try:
        plain = AESGCM(key).decrypt(nonce, cipher, _aad(header))
    except InvalidTag:
        raise BackupError("wrong_password")
    return _unzip(plain)


# ---------------------------------------------------------------------------
# Wiederherstellen
# ---------------------------------------------------------------------------

def stage_restore(contents: BackupContents, app_dir: Path) -> Path:
    """Legt die Dateien zum Übernehmen beim nächsten Start bereit."""
    pending = app_dir / PENDING_DIR
    if pending.exists():
        shutil.rmtree(pending)
    pending.mkdir(parents=True)
    for name, data in contents.files.items():
        if is_allowed_name(name):
            (pending / name).write_bytes(data)
    manifest = dict(contents.manifest)
    manifest["files"] = sorted(n for n in contents.files if is_allowed_name(n))
    (pending / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return pending


def _merge_secrets_db(restored: Path, previous: Path) -> None:
    """Backup ohne Geheimnisse: Passwörter/API-Schlüssel des bisherigen
    Stands behalten statt sie mit leeren Werten zu überschreiben."""
    old = sqlite3.connect(str(previous))
    new = sqlite3.connect(str(restored))
    try:
        old_tables = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        new_tables = {r[0] for r in new.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "app_settings" in old_tables and "app_settings" in new_tables:
            for key in SECRET_SETTING_KEYS:
                row = old.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
                if row is not None:
                    new.execute(
                        "INSERT INTO app_settings (key, value) VALUES (?, ?)"
                        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, row[0]),
                    )
        if "server_profiles" in old_tables and "server_profiles" in new_tables:
            secrets: Dict[tuple, Dict] = {}
            for (raw,) in old.execute("SELECT data FROM server_profiles").fetchall():
                try:
                    p = json.loads(raw)
                except Exception:
                    continue
                if isinstance(p, dict):
                    k = (str(p.get("host", "")).lower(), int(p.get("tcp_port", 0) or 0), str(p.get("username", "")))
                    secrets[k] = {f: p.get(f, "") for f in SERVER_SECRET_FIELDS}
            for row_id, raw in new.execute("SELECT id, data FROM server_profiles").fetchall():
                try:
                    p = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(p, dict):
                    continue
                k = (str(p.get("host", "")).lower(), int(p.get("tcp_port", 0) or 0), str(p.get("username", "")))
                if k in secrets:
                    for f, v in secrets[k].items():
                        if not p.get(f) and v:
                            p[f] = v
                    new.execute("UPDATE server_profiles SET data=? WHERE id=?", (json.dumps(p), row_id))
        if "plugin_settings" in old_tables and "plugin_settings" in new_tables:
            for name, key, value in old.execute("SELECT plugin_name, key, value_json FROM plugin_settings").fetchall():
                if _is_secret_plugin_key(key):
                    new.execute(
                        "UPDATE plugin_settings SET value_json=? WHERE plugin_name=? AND key=? AND value_json=?",
                        (value, name, key, json.dumps("")),
                    )
        new.commit()
    finally:
        old.close()
        new.close()


def has_pending_restore(app_dir: Path) -> bool:
    return (app_dir / PENDING_DIR / "_manifest.json").exists()


def apply_pending_restore(app_dir: Path, now: Optional[datetime] = None) -> Optional[str]:
    """Beim Start vor dem Öffnen der Datenbank aufrufen. Gibt den Namen des
    Sicherungsordners mit dem vorherigen Stand zurück, sonst None."""
    pending = app_dir / PENDING_DIR
    manifest_path = pending / "_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    names: List[str] = [n for n in manifest.get("files", []) if is_allowed_name(n) and (pending / n).is_file()]
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    before = app_dir / f"{BEFORE_RESTORE_PREFIX}{stamp}"
    before.mkdir(parents=True, exist_ok=True)
    for f in app_dir.iterdir():
        if f.is_file() and is_allowed_name(f.name):
            shutil.copy2(f, before / f.name)
    for name in names:
        shutil.copy2(pending / name, app_dir / name)
        if not manifest.get("secrets_included", True) and name.lower().endswith(".db") and (before / name).exists():
            try:
                _merge_secrets_db(app_dir / name, before / name)
            except Exception:
                pass
    shutil.rmtree(pending, ignore_errors=True)
    # Nur die letzten Sicherungsstände behalten
    olds = sorted(p for p in app_dir.iterdir() if p.is_dir() and p.name.startswith(BEFORE_RESTORE_PREFIX))
    for old in olds[:-KEEP_BEFORE_RESTORE]:
        shutil.rmtree(old, ignore_errors=True)
    return before.name
