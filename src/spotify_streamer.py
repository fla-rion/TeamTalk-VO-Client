"""Spotify streaming via librespot binary.

librespot runs as a Spotify Connect device. The user authenticates once
via OAuth (browser) and librespot stores the credentials. From the second
launch onwards no login is needed.

PCM from librespot is read via a FIFO (POSIX) or named pipe (Windows) and
injected into the TeamTalk channel via InsertAudioBlock.

Requires Spotify Premium.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("tt.spotify")

_SAMPLE_RATE = 44100
_CHANNELS = 2
_FRAME_BYTES = 4410 * _CHANNELS * 2  # 100 ms @ 44100 Hz stereo S16LE

_WIN_PIPE_NAME = r"\\.\pipe\tt_spotify_pcm"


def find_librespot() -> Optional[str]:
    """Return path to the librespot binary, or None if not found."""
    exe = "librespot.exe" if sys.platform == "win32" else "librespot"

    # 1. Bundled inside frozen app (PyInstaller)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "librespot" / exe
        if bundled.exists():
            return str(bundled)

    # 2. third_party/librespot/ in repo
    root = Path(__file__).resolve().parent.parent
    local = root / "third_party" / "librespot" / exe
    if local.exists():
        return str(local)

    # 3. ~/.cargo/bin (cargo install librespot)
    cargo_bin = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "bin" / exe
    if cargo_bin.exists():
        return str(cargo_bin)

    # 4. System PATH
    return shutil.which(exe)


def credentials_path() -> str:
    """Path where librespot stores its credentials after first login."""
    config_dir = Path.home() / ".config" / "tt-vo-client"
    config_dir.mkdir(parents=True, exist_ok=True)
    return str(config_dir / "librespot_credentials.json")


def has_stored_credentials() -> bool:
    return Path(credentials_path()).exists()


class SpotifyStreamer:
    """Manages a librespot subprocess and pumps PCM into TeamTalk."""

    def __init__(self, client) -> None:
        self._client = client
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._tmpdir: Optional[str] = None
        self._pipe_path: Optional[str] = None
        self._win_handle = None
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._running

    def start(
        self,
        librespot_path: str,
        device_name: str = "TeamTalk Stream",
        access_token: str = "",
        bitrate: str = "320",
    ) -> bool:
        if self._running:
            return True

        binary = librespot_path.strip() or find_librespot()
        if not binary or not Path(binary).exists():
            self._emit_error(
                "librespot nicht gefunden.\n"
                "Bitte 'python scripts/download_librespot.py' ausführen "
                "oder den Pfad manuell eintragen."
            )
            return False

        creds = credentials_path()
        have_creds = Path(creds).exists()
        have_token = bool(access_token.strip())

        if not have_creds and not have_token:
            self._emit_error(
                "Nicht angemeldet. Bitte zuerst 'Mit Spotify anmelden' klicken."
            )
            return False

        if sys.platform == "win32":
            if not self._setup_windows_pipe():
                return False
        else:
            if not self._setup_posix_fifo():
                return False

        cmd = [
            binary,
            "--name", device_name,
            "--backend", "pipe",
            "--device", self._pipe_path,
            "--bitrate", bitrate,
            "--initial-volume", "100",
            "--credentials-cache", creds,
        ]
        if have_token:
            cmd += ["--access-token", access_token]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:
            self._emit_error(f"librespot-Start fehlgeschlagen: {exc}")
            self._cleanup_pipe()
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._pump, daemon=True, name="spotify_pump"
        )
        self._thread.start()
        self._emit_status(
            f"Spotify bereit – wähle '{device_name}' in deiner Spotify-App aus"
        )
        return True

    def stop(self) -> None:
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass
            self._proc = None
        self._cleanup_pipe()

    # ------------------------------------------------------------------
    # Pipe setup
    # ------------------------------------------------------------------

    def _setup_posix_fifo(self) -> bool:
        try:
            self._tmpdir = tempfile.mkdtemp(prefix="tt_spotify_")
            self._pipe_path = os.path.join(self._tmpdir, "pcm.fifo")
            os.mkfifo(self._pipe_path)
            return True
        except Exception as exc:
            self._emit_error(f"FIFO erstellen fehlgeschlagen: {exc}")
            return False

    def _setup_windows_pipe(self) -> bool:
        import ctypes
        PIPE_ACCESS_INBOUND = 0x00000001
        PIPE_TYPE_BYTE = 0x00000000
        PIPE_WAIT = 0x00000000
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateNamedPipeW(
            _WIN_PIPE_NAME,
            PIPE_ACCESS_INBOUND,
            PIPE_TYPE_BYTE | PIPE_WAIT,
            1, 0, 65536, 0, None,
        )
        if handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            self._emit_error(f"Named Pipe erstellen fehlgeschlagen (Fehler {err})")
            return False
        self._win_handle = handle
        self._pipe_path = _WIN_PIPE_NAME
        return True

    def _cleanup_pipe(self) -> None:
        if self._win_handle is not None:
            try:
                import ctypes
                ctypes.WinDLL("kernel32").CloseHandle(self._win_handle)
            except Exception:
                pass
            self._win_handle = None
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
        self._pipe_path = None

    # ------------------------------------------------------------------
    # PCM pump
    # ------------------------------------------------------------------

    def _pump(self) -> None:
        try:
            if sys.platform == "win32":
                self._pump_windows()
            else:
                self._pump_posix()
        except Exception as exc:
            if self._running:
                logger.exception("Spotify pump crashed: %s", exc)
                self._emit_error(f"Spotify-Stream unterbrochen: {exc}")
        finally:
            self._running = False

    def _pump_posix(self) -> None:
        with open(self._pipe_path, "rb") as f:
            buf = b""
            while self._running:
                chunk = f.read(8192)
                if not chunk:
                    break
                buf += chunk
                while len(buf) >= _FRAME_BYTES:
                    self._inject(buf[:_FRAME_BYTES])
                    buf = buf[_FRAME_BYTES:]

    def _pump_windows(self) -> None:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ConnectNamedPipe(self._win_handle, None)
        if not self._running:
            return
        raw = ctypes.create_string_buffer(8192)
        bytes_read = ctypes.c_ulong(0)
        buf = b""
        while self._running:
            ok = kernel32.ReadFile(
                self._win_handle, raw, 8192, ctypes.byref(bytes_read), None
            )
            if not ok:
                break
            buf += bytes(raw.raw[: bytes_read.value])
            while len(buf) >= _FRAME_BYTES:
                self._inject(buf[:_FRAME_BYTES])
                buf = buf[_FRAME_BYTES:]
        kernel32.CloseHandle(self._win_handle)
        self._win_handle = None

    def _inject(self, pcm: bytes) -> None:
        try:
            self._client.insert_audio_block_bytes(pcm, _SAMPLE_RATE, _CHANNELS)
        except Exception as exc:
            logger.warning("insert_audio_block_bytes: %s", exc)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _emit_status(self, msg: str) -> None:
        if self.on_status:
            self.on_status(msg)

    def _emit_error(self, msg: str) -> None:
        logger.error("SpotifyStreamer: %s", msg)
        if self.on_error:
            self.on_error(msg)
