"""Deezer track download via yt-dlp + ARL cookie.

Authentication: ARL token (192-char cookie from deezer.com).
Username/password login was removed by Deezer — ARL is the only method.

The ARL is written to a temporary Netscape cookie file; yt-dlp (already
bundled in third_party/yt-dlp/) handles everything else including decryption.

No extra pip packages required.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger("tt.deezer")

_ARL_FILE = Path.home() / ".config" / "tt-vo-client" / "deezer_arl.txt"
_SEARCH_URL = "https://api.deezer.com/search"

# ---------------------------------------------------------------------------
# ARL persistence
# ---------------------------------------------------------------------------

def load_arl() -> str:
    if _ARL_FILE.exists():
        return _ARL_FILE.read_text(encoding="utf-8").strip()
    return ""


def save_arl(arl: str) -> None:
    _ARL_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ARL_FILE.write_text(arl.strip(), encoding="utf-8")


def clear_arl() -> None:
    if _ARL_FILE.exists():
        _ARL_FILE.unlink()


def has_arl() -> bool:
    return bool(load_arl())


# ---------------------------------------------------------------------------
# Public search (no auth required)
# ---------------------------------------------------------------------------

def search_tracks(query: str, limit: int = 25) -> List[dict]:
    """Search Deezer public API. Returns list of track dicts."""
    url = f"{_SEARCH_URL}?q={urllib.parse.quote(query)}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data.get("data", [])


def format_track(t: dict) -> str:
    """Human-readable label for a search result track dict."""
    title = t.get("title") or "?"
    artist = (t.get("artist") or {}).get("name") or ""
    duration = t.get("duration") or 0
    mins, secs = divmod(int(duration), 60)
    parts = [title]
    if artist:
        parts.append(artist)
    parts.append(f"{mins}:{secs:02d}")
    return " — ".join(parts)


# ---------------------------------------------------------------------------
# yt-dlp helper
# ---------------------------------------------------------------------------

def _find_ytdlp() -> Optional[str]:
    exe = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "yt-dlp" / exe
        if p.exists():
            return str(p)
    root = Path(__file__).resolve().parent.parent
    p = root / "third_party" / "yt-dlp" / exe
    if p.exists():
        return str(p)
    return shutil.which(exe) or shutil.which("yt-dlp")


def _write_cookie_file(arl: str, path: str) -> None:
    """Write ARL as a Netscape cookie file for yt-dlp."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f".deezer.com\tTRUE\t/\tTRUE\t2147483647\tarl\t{arl}\n")


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------

class DeezerDownloader:
    """Downloads a single Deezer track via yt-dlp and a temp cookie file."""

    def __init__(self) -> None:
        self._tmpdir: Optional[str] = None
        self._thread: Optional[threading.Thread] = None

    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def download(
        self,
        track_id: int,
        arl: str,
        on_done: Callable[[str], None],
        on_error: Callable[[str], None],
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        if self.is_busy():
            on_error("Download läuft bereits.")
            return
        self._thread = threading.Thread(
            target=self._run,
            args=(track_id, arl, on_done, on_error, on_status),
            daemon=True,
            name="deezer_dl",
        )
        self._thread.start()

    def cleanup(self) -> None:
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None

    # ------------------------------------------------------------------

    def _run(self, track_id, arl, on_done, on_error, on_status):
        try:
            self._download(track_id, arl, on_done, on_error, on_status)
        except Exception as exc:
            logger.exception("DeezerDownloader crash: %s", exc)
            on_error(str(exc))

    def _download(self, track_id, arl, on_done, on_error, on_status):
        ytdlp = _find_ytdlp()
        if not ytdlp:
            on_error(
                "yt-dlp nicht gefunden.\n"
                "Bitte third_party/yt-dlp/ prüfen."
            )
            return

        self.cleanup()
        tmpdir = tempfile.mkdtemp(prefix="tt_deezer_")
        self._tmpdir = tmpdir

        cookie_file = os.path.join(tmpdir, "deezer.txt")
        _write_cookie_file(arl, cookie_file)

        track_url = f"https://www.deezer.com/track/{track_id}"
        out_tmpl = os.path.join(tmpdir, "%(title)s.%(ext)s")

        if on_status:
            on_status("Download läuft…")

        cmd = [
            ytdlp,
            "--cookies", cookie_file,
            "--no-playlist",
            "-f", "bestaudio/best",
            "-o", out_tmpl,
            "--no-progress",
            "--quiet",
            track_url,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            on_error("Download-Timeout (120 s überschritten).")
            return

        if result.returncode != 0:
            err = (result.stderr or result.stdout or "Unbekannter Fehler").strip()
            # Friendly hint for expired ARL
            if "login" in err.lower() or "premium" in err.lower() or "403" in err:
                err += "\n→ ARL-Token möglicherweise abgelaufen. Neu aus dem Browser kopieren."
            on_error(err)
            return

        files = (
            list(Path(tmpdir).rglob("*.mp3"))
            + list(Path(tmpdir).rglob("*.flac"))
            + list(Path(tmpdir).rglob("*.ogg"))
            + list(Path(tmpdir).rglob("*.m4a"))
            + list(Path(tmpdir).rglob("*.opus"))
        )
        if not files:
            on_error("Download abgeschlossen, aber keine Audiodatei gefunden.")
            return

        on_done(str(files[0]))
