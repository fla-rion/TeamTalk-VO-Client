"""update_manager – GitHub-Release-Abfrage und Asset-Download.

Öffentliche API:
    fetch_releases(limit)        -> List[Release]
    get_platform_asset(release)  -> Optional[ReleaseAsset]
    download_asset(asset, dest_dir, progress_cb) -> str  (Pfad zur Datei)
    open_file_or_folder(path)    -> None
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, List, Optional

_GITHUB_API = "https://api.github.com/repos/fla-rion/TeamTalk-VO-Client/releases"
_HEADERS = {"User-Agent": "TeamTalk-VO-Client-UpdateManager"}


def _ssl_context() -> Optional[ssl.SSLContext]:
    """Baut den SSL-Kontext aus certifis eigenem CA-Bundle statt den
    System-Vertrauensspeicher zu verwenden.

    In der per PyInstaller gebauten App liest urllib sonst die
    Standard-OpenSSL-Pfade des Systems - das funktioniert normalerweise,
    ist aber genau die Konstellation, in der ein eingefrorenes Python am
    ehesten mit CERTIFICATE_VERIFY_FAILED scheitert, obwohl derselbe
    Code als reines Skript einwandfrei läuft. certifi liegt als
    requests-Abhängigkeit ohnehin im Bundle (PyInstaller hat dafür einen
    eigenen Hook, der certifi.where() im gefrorenen Zustand korrekt
    auflöst), daher explizit dessen aktuelles CA-Bundle verwenden statt
    stillschweigend auf den System-Vertrauensspeicher zu hoffen.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


_SSL_CONTEXT = _ssl_context()


@dataclass
class ReleaseAsset:
    name: str
    download_url: str
    size: int  # Bytes


@dataclass
class Release:
    tag: str
    name: str
    date: str        # "YYYY-MM-DD"
    body: str        # Changelog-Text
    assets: List[ReleaseAsset] = field(default_factory=list)

    @property
    def platform_asset(self) -> Optional[ReleaseAsset]:
        return get_platform_asset(self)


def fetch_releases(limit: int = 50) -> List[Release]:
    """Holt alle Releases von der GitHub-API (kein Token nötig)."""
    url = f"{_GITHUB_API}?per_page={limit}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result: List[Release] = []
    for r in data:
        if r.get("draft") or r.get("prerelease"):
            continue
        assets = [
            ReleaseAsset(
                name=a["name"],
                download_url=a["browser_download_url"],
                size=int(a.get("size", 0)),
            )
            for a in r.get("assets", [])
        ]
        result.append(Release(
            tag=r["tag_name"],
            name=r.get("name") or r["tag_name"],
            date=(r.get("published_at") or "")[:10],
            body=(r.get("body") or "").strip(),
            assets=assets,
        ))
    return result


def _linux_arch() -> str:
    import platform
    return "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"


def _platform_patterns(plat: Optional[str] = None, arch: Optional[str] = None) -> List[tuple]:
    """(Endung, ist_Installer) in Vorzugsreihenfolge – Installationspakete
    (seit v11.2.1) vor den bisherigen Archiven."""
    plat = plat or sys.platform
    if plat == "darwin":
        return [(".pkg", True), (".dmg", False)]
    if plat == "win32":
        return [("-setup.exe", True), ("-windows.zip", False), (".zip", False)]
    arch = arch or _linux_arch()
    deb_arch = "arm64" if arch == "arm64" else "amd64"
    return [(f"_{deb_arch}.deb", True), (f"_linux_{arch}.tar.gz", False)]


def get_platform_asset(release: Release, plat: Optional[str] = None,
                       arch: Optional[str] = None) -> Optional[ReleaseAsset]:
    """Gibt das passende Asset für die aktuelle Plattform zurück
    (Installationspaket bevorzugt)."""
    for suffix, _installer in _platform_patterns(plat, arch):
        for asset in release.assets:
            if asset.name.lower().endswith(suffix):
                return asset
    return None


_INSTALLER_SUFFIXES = {"darwin": (".pkg",), "win32": ("-setup.exe",), "linux": (".deb",)}


def is_installer(name: str, plat: Optional[str] = None) -> bool:
    plat = plat or sys.platform
    key = plat if plat in _INSTALLER_SUFFIXES else "linux"
    return name.lower().endswith(_INSTALLER_SUFFIXES[key])


def download_asset(
    asset: ReleaseAsset,
    dest_dir: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Lädt ein Asset herunter und gibt den Zielpfad zurück.

    progress_cb(downloaded_bytes, total_bytes) wird regelmäßig aufgerufen.
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, asset.name)
    req = urllib.request.Request(asset.download_url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=120, context=_SSL_CONTEXT) as resp:
        total = int(resp.headers.get("Content-Length") or asset.size or 0)
        downloaded = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)
    return dest_path


def install_update(path: str) -> "tuple[bool, str]":
    """Startet das heruntergeladene Installationspaket. Die App muss sich
    danach selbst beenden (macht der Aufrufer nach Bestätigung des Nutzers).

    macOS: Installer (.pkg) per ``open``. Windows: Setup-Programm (Inno Setup,
    schließt eine noch laufende App selbst). Linux: ``apt-get install`` des
    .deb in einem Terminal mit Passwortabfrage (pkexec/sudo).
    """
    import subprocess
    from i18n import _
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]  # UAC-Abfrage kommt vom Setup
        else:
            from terminal_launcher import run_in_terminal
            ok, err = run_in_terminal(linux_install_script(path), prefix="ttvo-update-")
            if not ok:
                return False, err
    except OSError as exc:
        return False, str(exc)
    return True, _("Setup gestartet")


def linux_install_script(deb_path: str) -> str:
    from i18n import _

    def q(s: str) -> str:
        return "'" + str(s).replace("'", "'\\''") + "'"
    return f"""#!/bin/bash
echo {q(_("TeamTalk VO Client wird aktualisiert …"))}
ok=0
if command -v pkexec >/dev/null 2>&1; then
  pkexec apt-get install -y {q(deb_path)} && ok=1
else
  sudo apt-get install -y {q(deb_path)} && ok=1
fi
echo
if [ "$ok" -eq 1 ]; then echo {q(_("Fertig: Das Update ist installiert. Du kannst TeamTalk VO Client wieder starten."))}; else echo {q(_("Installation fehlgeschlagen"))}; fi
echo
read -r -p {q(_("Enter drücken, um dieses Fenster zu schließen") + " ")} _
"""


def open_file_or_folder(path: str) -> None:
    """Öffnet eine Datei oder ihren übergeordneten Ordner im Dateimanager."""
    import subprocess
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def reveal_in_finder(path: str) -> None:
    """Zeigt die Datei im Finder / Explorer an (markiert)."""
    import subprocess
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", path])
    else:
        open_file_or_folder(path)


def format_size(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"
