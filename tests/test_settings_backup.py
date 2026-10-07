"""Verschlüsseltes Einstellungs-Backup – nur temporäre Ordner, nie echte Daten."""
import io
import json
import os
import sqlite3
import sys
import zipfile
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("cryptography")
import settings_backup as sb  # noqa: E402

PW = "geheim123"


def _make_app_dir(tmp_path, api_key="sk-echt", server_pw="srvpw"):
    d = tmp_path / "app"
    d.mkdir()
    conn = sqlite3.connect(str(d / "settings.db"))
    conn.executescript("""
        CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE server_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, sort_order INTEGER DEFAULT 0, data TEXT NOT NULL);
        CREATE TABLE plugin_settings (plugin_name TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, PRIMARY KEY (plugin_name, key));
    """)
    conn.execute("INSERT INTO app_settings VALUES ('claude_api_key', ?)", (json.dumps(api_key),))
    conn.execute("INSERT INTO app_settings VALUES ('gender', ?)", (json.dumps("Neutral"),))
    conn.execute("INSERT INTO app_settings VALUES ('channel_password_index', ?)", (json.dumps([{"pw": "x"}]),))
    prof = {"name": "Testserver", "host": "Example.org", "tcp_port": 10333, "username": "flo",
            "password": server_pw, "channel_password": "kpw", "elevenlabs_api_key": "el"}
    conn.execute("INSERT INTO server_profiles (sort_order, data) VALUES (0, ?)", (json.dumps(prof),))
    conn.execute("INSERT INTO plugin_settings VALUES ('wetter', 'api_token', ?)", (json.dumps("tok"),))
    conn.execute("INSERT INTO plugin_settings VALUES ('wetter', 'city', ?)", (json.dumps("Aachen"),))
    conn.commit()
    conn.close()
    (d / "servers.json").write_text(json.dumps([prof]), encoding="utf-8")
    (d / "scheduled_joins.json").write_text("[]", encoding="utf-8")
    (d / "client.log").write_text("nicht sichern", encoding="utf-8")
    (d / "chat_history").mkdir()
    return d


def _db_value(path, key):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def _profile(path):
    conn = sqlite3.connect(str(path))
    try:
        return json.loads(conn.execute("SELECT data FROM server_profiles").fetchone()[0])
    finally:
        conn.close()


def test_roundtrip_with_secrets(tmp_path):
    d = _make_app_dir(tmp_path)
    data = sb.create_backup(d, PW, include_secrets=True, app_version="10.11.0",
                            now=datetime(2026, 10, 8, 12, 0))
    assert b"sk-echt" not in data and b"Testserver" not in data  # verschlüsselt
    c = sb.read_backup(data, PW)
    assert c.encrypted and c.secrets_included and c.app_version == "10.11.0"
    assert c.created == "2026-10-08T12:00:00"
    assert sorted(c.files) == ["scheduled_joins.json", "servers.json", "settings.db"]
    db = tmp_path / "check.db"
    db.write_bytes(c.files["settings.db"])
    assert _db_value(db, "claude_api_key") == "sk-echt"


def test_wrong_password_and_tampering(tmp_path):
    d = _make_app_dir(tmp_path)
    data = sb.create_backup(d, PW, include_secrets=True)
    with pytest.raises(sb.BackupError) as exc:
        sb.read_backup(data, "falsch!!")
    assert exc.value.reason == "wrong_password"
    doc = json.loads(data)
    doc["kdf"]["n"] = 2 ** 14  # Kopf manipuliert → Schlüssel/AAD passen nicht
    with pytest.raises(sb.BackupError):
        sb.read_backup(json.dumps(doc).encode(), PW)
    with pytest.raises(sb.BackupError) as exc:
        sb.read_backup(b"irgendwas", PW)
    assert exc.value.reason == "invalid"


def test_password_too_short(tmp_path):
    d = _make_app_dir(tmp_path)
    with pytest.raises(sb.BackupError) as exc:
        sb.create_backup(d, "123", include_secrets=False)
    assert exc.value.reason == "password_short"


def test_without_secrets_strips_everything_secret(tmp_path):
    d = _make_app_dir(tmp_path)
    c = sb.read_backup(sb.create_backup(d, PW, include_secrets=False), PW)
    assert not c.secrets_included
    db = tmp_path / "check.db"
    db.write_bytes(c.files["settings.db"])
    assert _db_value(db, "claude_api_key") == ""
    assert _db_value(db, "channel_password_index") == []
    assert _db_value(db, "gender") == "Neutral"  # normale Einstellung bleibt
    prof = _profile(db)
    assert prof["password"] == "" and prof["channel_password"] == "" and prof["elevenlabs_api_key"] == ""
    assert prof["host"] == "Example.org"
    raw = c.files["settings.db"]
    assert b"sk-echt" not in raw and b"srvpw" not in raw and b'"tok"' not in raw  # auch nicht im freien Speicher
    servers = json.loads(c.files["servers.json"])
    assert servers[0]["password"] == ""


def test_restore_is_staged_and_applied_on_next_start(tmp_path):
    src = _make_app_dir(tmp_path)
    data = sb.create_backup(src, PW, include_secrets=True)
    target = tmp_path / "ziel"
    target.mkdir()
    conn = sqlite3.connect(str(target / "settings.db"))
    conn.executescript("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    conn.execute("INSERT INTO app_settings VALUES ('gender', ?)", (json.dumps("Männlich"),))
    conn.commit()
    conn.close()

    sb.stage_restore(sb.read_backup(data, PW), target)
    assert sb.has_pending_restore(target)
    assert _db_value(target / "settings.db", "gender") == "Männlich"  # noch nichts überschrieben

    before = sb.apply_pending_restore(target, now=datetime(2026, 10, 8, 13, 0))
    assert before == "before_restore_20261008_130000"
    assert _db_value(target / "settings.db", "gender") == "Neutral"
    assert _db_value(target / before / "settings.db", "gender") == "Männlich"
    assert not sb.has_pending_restore(target)
    assert sb.apply_pending_restore(target) is None


def test_restore_without_secrets_keeps_current_passwords(tmp_path):
    src = _make_app_dir(tmp_path)
    data = sb.create_backup(src, PW, include_secrets=False)
    (tmp_path / "other").mkdir()
    target = _make_app_dir(tmp_path / "other", api_key="sk-aktuell", server_pw="aktuellpw")
    sb.stage_restore(sb.read_backup(data, PW), target)
    sb.apply_pending_restore(target)
    assert _db_value(target / "settings.db", "claude_api_key") == "sk-aktuell"
    assert _profile(target / "settings.db")["password"] == "aktuellpw"


def test_legacy_zip_backup_is_readable(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("settings.db", b"x")
        zf.writestr("../boese.json", b"{}")
        zf.writestr("unter/ordner.json", b"{}")
    c = sb.read_backup(buf.getvalue())
    assert not c.encrypted and list(c.files) == ["settings.db"]


def test_staging_rejects_unsafe_names(tmp_path):
    c = sb.BackupContents(manifest={}, files={"settings.db": b"a", "../x.json": b"b", ".versteckt.json": b"c"})
    pending = sb.stage_restore(c, tmp_path)
    assert sorted(p.name for p in pending.iterdir()) == ["_manifest.json", "settings.db"]
