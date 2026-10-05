"""BearWare-Beitrittscodes (Join Codes, TeamTalk 5.22+).

Ein Serverbetreiber kann seinen Server über den offiziellen TeamTalk-Client
privat bei bearware.dk veröffentlichen und erhält dafür einen kurzen Code.
Der Code wird über denselben Webdienst wie die öffentliche Serverliste in
vollständige Verbindungsdaten aufgelöst::

    GET https://www.bearware.dk/teamtalk/tt5servers.php
        ?client=…&version=…&os=…&action=joincode&joincode=<code>

Die Antwort ist eine .tt-Datei (``<teamtalk><host>…</host></teamtalk>``),
bei unbekanntem Code ein leeres ``<teamtalk/>``. Groß-/Kleinschreibung des
Codes spielt für den Dienst keine Rolle.

Das *Erzeugen* eines Codes (``action=publish&joincode=1``) setzt ein
BearWare.dk-WebLogin mit Token voraus und wird hier bewusst nicht angeboten.
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode
from typing import Callable, Optional

from .models import ParsedTeamTalkFile
from .tt_file_parser import parse_teamtalk_xml_text

JOINCODE_SERVICE_URL = "https://www.bearware.dk/teamtalk/tt5servers.php"
CLIENT_NAME = "TeamTalkVOClient"
_FETCH_TIMEOUT = 10

# Codes des offiziellen Dienstes sind kurze alphanumerische Kennungen
# (z. B. "abcdefgh"). Bewusst etwas großzügiger, damit künftige Formate
# nicht am Client scheitern – Pfade und URLs fallen trotzdem heraus.
_JOINCODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


class JoinCodeError(Exception):
    """Webdienst nicht erreichbar oder Antwort unbrauchbar."""


def looks_like_join_code(text: str) -> bool:
    """True, wenn *text* weder tt://-URL noch Dateipfad ist, sondern ein Code."""
    candidate = (text or "").strip()
    if not candidate or candidate.lower().startswith("tt://"):
        return False
    return bool(_JOINCODE_RE.match(candidate))


def _os_name() -> str:
    if sys.platform == "darwin":
        return "Mac"
    if sys.platform.startswith("win"):
        return "Windows"
    return "Linux"


def build_join_code_url(code: str, app_version: str = "") -> str:
    params = {
        "client": CLIENT_NAME,
        "version": app_version or "",
        "os": _os_name(),
        "action": "joincode",
        "joincode": (code or "").strip(),
    }
    return f"{JOINCODE_SERVICE_URL}?{urlencode(params)}"


def _default_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "TeamTalk VO Client"})
    with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
        return resp.read()


def resolve_join_code(
    code: str,
    app_version: str = "",
    fetch: Optional[Callable[[str], bytes]] = None,
) -> Optional[ParsedTeamTalkFile]:
    """Löst einen Beitrittscode in Verbindungsdaten auf.

    Blockiert (Netzwerk) – nur aus einem Hintergrund-Thread aufrufen.
    Gibt None zurück, wenn der Dienst den Code nicht kennt; wirft
    JoinCodeError bei Netzwerk-/Formatfehlern.
    """
    code = (code or "").strip()
    if not code:
        return None
    fetch = fetch or _default_fetch
    try:
        data = fetch(build_join_code_url(code, app_version))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise JoinCodeError(str(exc)) from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if "<teamtalk" not in text.lower():
        raise JoinCodeError("unexpected response")
    parsed = parse_teamtalk_xml_text(text, fallback_name=code)
    if parsed is None:
        return None
    if not parsed.joincode:
        parsed.joincode = code
        parsed.profile.joincode = code
    return parsed
