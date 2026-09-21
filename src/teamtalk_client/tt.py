from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_teamtalk_sdk_on_path() -> None:
    here = Path(__file__).resolve()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        sdk_py = Path(sys._MEIPASS) / "TeamTalkPy"
        dll_dir = Path(sys._MEIPASS) / "TeamTalk_DLL"
        if sys.platform == "win32":
            try:
                if dll_dir.exists():
                    os.add_dll_directory(str(dll_dir))
            except Exception:
                pass
    else:
        root = here.parents[2]
        if sys.platform == "win32":
            sdk_root = root / "third_party" / "teamtalk" / "tt5sdk_v5.19a_win64" / "Library"
        else:
            sdk_root = root / "third_party" / "teamtalk" / "tt5sdk_v5.19a_macos_universal" / "Library"
        sdk_py = sdk_root / "TeamTalkPy"
        dll_dir = sdk_root / "TeamTalk_DLL"
    if sys.platform == "darwin":
        # TeamTalk5.py lädt die Lib unter macOS per nacktem Dateinamen
        # (cdll.LoadLibrary("libTeamTalk5.dylib")). SIP verhindert, dass dyld
        # eine so referenzierte Datei findet, wenn sie nicht bereits geladen
        # ist. Deshalb hier vorab per absolutem Pfad laden – der nachfolgende
        # nackte LoadLibrary-Aufruf findet die Lib dann über das bereits
        # geladene Image.
        dylib_path = dll_dir / "libTeamTalk5.dylib"
        if dylib_path.exists():
            try:
                import ctypes
                ctypes.CDLL(str(dylib_path))
            except OSError:
                pass
    if str(sdk_py) not in sys.path:
        sys.path.insert(0, str(sdk_py))


def load_teamtalk_module():
    ensure_teamtalk_sdk_on_path()
    import importlib
    return importlib.import_module("TeamTalk5")
