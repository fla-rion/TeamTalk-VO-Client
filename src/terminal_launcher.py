"""Ein Skript in einem sichtbaren Terminal-Fenster ausführen.

Für Installationen, bei denen der Nutzer den Fortschritt sehen und ggf. ein
Passwort eingeben soll (whisper.cpp nachinstallieren, Linux-Update per apt).
Das Skript selbst zeigt am Ende eine Meldung und wartet auf Enter.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from i18n import _

_LINUX_TERMINALS = (
    ("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]), ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]), ("mate-terminal", ["-x"]), ("lxterminal", ["-e"]),
    ("tilix", ["-e"]), ("kitty", []), ("alacritty", ["-e"]), ("xterm", ["-e"]),
)


def linux_terminal_command(script: Path) -> Optional[List[str]]:
    cmd = ["bash", str(script)]
    for term, prefix in _LINUX_TERMINALS:
        if shutil.which(term):
            return [term] + prefix + cmd
    return None


def write_script(content: str, prefix: str, windows: bool) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".ps1" if windows else ".sh")
    # PowerShell liest UTF-8 mit BOM sicher (Umlaute in den Meldungen)
    with os.fdopen(fd, "w", encoding="utf-8-sig" if windows else "utf-8", newline="\n") as f:
        f.write(content)
    path = Path(name)
    if not windows:
        path.chmod(0o755)
    return path


def run_in_terminal(content: str, prefix: str = "ttvo-") -> Tuple[bool, str]:
    """Schreibt ``content`` (PowerShell unter Windows, sonst bash) in eine
    temporäre Datei und startet sie in einem neuen Terminal-Fenster."""
    windows = sys.platform == "win32"
    script = write_script(content, prefix, windows)
    try:
        if windows:
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                creationflags=0x00000010,  # CREATE_NEW_CONSOLE
            )
        elif sys.platform == "darwin":
            osa = f'tell application "Terminal" to do script "bash " & quoted form of "{script}"'
            subprocess.Popen(["osascript", "-e", osa, "-e", 'tell application "Terminal" to activate'])
        else:
            cmd = linux_terminal_command(script)
            if cmd is None:
                return False, _("Kein Terminal-Programm gefunden. Bitte im Terminal ausführen: bash {}").format(script)
            subprocess.Popen(cmd)
    except OSError as exc:
        return False, str(exc)
    return True, ""
