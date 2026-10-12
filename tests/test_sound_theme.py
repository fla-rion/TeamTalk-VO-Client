"""Sound-Themes: Standard "modern", Umschalten auf "classic", Rückfall."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import sound_manager  # noqa: E402
from sound_manager import DEFAULT_SOUNDS, SOUND_THEMES, SoundManager  # noqa: E402

SOUNDS = Path(__file__).resolve().parent.parent / "src" / "sounds"


def test_default_theme_is_modern():
    m = SoundManager()
    assert m.theme == "modern"
    assert Path(m._resolve("user_join", None)) == SOUNDS / "modern" / "newuser.wav"


def test_every_theme_covers_all_events():
    for sub in SOUND_THEMES.values():
        for filename in set(DEFAULT_SOUNDS.values()):
            assert (SOUNDS / sub / filename).is_file(), (sub, filename)


def test_classic_theme_uses_root_pack():
    m = SoundManager()
    m.set_theme("classic")
    assert Path(m._resolve("user_join", None)) == SOUNDS / "newuser.wav"


def test_unknown_theme_falls_back_to_default():
    m = SoundManager()
    m.set_theme("gibt-es-nicht")
    assert m.theme == sound_manager.DEFAULT_SOUND_THEME


def test_pack_dir_and_custom_path_override_theme(tmp_path):
    (tmp_path / "newuser.wav").write_bytes(b"RIFF")
    m = SoundManager()
    m.set_pack_dir(str(tmp_path))
    assert Path(m._resolve("user_join", None)) == tmp_path / "newuser.wav"
    custom = tmp_path / "eigen.wav"
    custom.write_bytes(b"RIFF")
    assert Path(m._resolve("user_join", str(custom))) == custom
