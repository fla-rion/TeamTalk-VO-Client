"""Sprechbereit-Befehl und BearWare-Töne für Sprachaktivierung/Stummschaltung.

Prüft die Logik von MainFrame (wx) an einem Ersatzobjekt, ohne Fenster und
ohne TeamTalk-SDK: Töne nur bei echten Zustandswechseln, alle Schalter
synchron, und der Sprechbereit-Befehl wendet Audio an, hebt die
Stummschaltung auf und schaltet die Sprachaktivierung ein (bzw. wieder aus).
"""
import os
import sys
import types
from pathlib import Path

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

import sound_manager  # noqa: E402


def test_default_sounds_are_bundled():
    sounds_dir = Path(SRC) / "sounds"
    missing = [
        key for key, name in sound_manager.DEFAULT_SOUNDS.items()
        if not (sounds_dir / name).exists()
        and not (sounds_dir / sound_manager.FALLBACK_SOUNDS.get(key, name)).exists()
    ]
    assert missing == []


def test_bearware_sound_names():
    # Dateinamen wie in qtTeamTalk/settings.h (SOUNDEVENT_VOICEACTMEON/-OFF,
    # SOUNDEVENT_MUTEALLON/-OFF)
    assert sound_manager.DEFAULT_SOUNDS["voiceact_me_on"] == "vox_me_enable.wav"
    assert sound_manager.DEFAULT_SOUNDS["voiceact_me_off"] == "vox_me_disable.wav"
    assert sound_manager.DEFAULT_SOUNDS["mute_all_on"] == "mute_all.wav"
    assert sound_manager.DEFAULT_SOUNDS["mute_all_off"] == "unmute_all.wav"


@pytest.fixture(scope="module")
def main_frame_cls(tmp_path_factory):
    pytest.importorskip("wx")
    # app_wx leitet beim Import stdout/stderr ins Startup-Log um – für den
    # Test in ein temporäres Verzeichnis und danach wiederherstellen.
    import platform_paths
    log_dir = tmp_path_factory.mktemp("logs")
    orig_log_dir = platform_paths.log_dir
    platform_paths.log_dir = lambda: log_dir
    out, err = sys.stdout, sys.stderr
    try:
        import app_wx
    finally:
        sys.stdout, sys.stderr = out, err
        platform_paths.log_dir = orig_log_dir
    return app_wx.MainFrame


class _Ctrl:
    def __init__(self, value=False):
        self.value = value

    def SetValue(self, v):
        self.value = v

    def GetValue(self):
        return self.value


class _Item:
    def __init__(self):
        self.checked = False

    def Check(self, v=True):
        self.checked = v


class _Client:
    def __init__(self):
        self.va = False
        self.muted = False

    def is_voice_activation_enabled(self):
        return self.va

    def enable_voice_activation(self, enable):
        self.va = bool(enable)
        return True

    def set_voice_activation_level(self, _level):
        return True

    def set_voice_activation_stop_delay(self, _ms):
        return True

    def set_sound_output_mute(self, muted):
        self.muted = bool(muted)
        return True


def _fake_frame(cls, apply_ok=True, input_ok=True):
    sounds, statuses, applied = [], [], []
    audio_tab = types.SimpleNamespace(
        voice_activation=_Ctrl(), output_mute=_Ctrl(),
        voice_level=_Ctrl(20), va_delay=_Ctrl(500),
        on_apply_audio=lambda _e, announce=True: applied.append(announce) or apply_ok,
    )
    f = types.SimpleNamespace(
        client=_Client(), audio_tab=audio_tab, _mute_all=False,
        tb_va=_Ctrl(), tb_mute=_Ctrl(),
        _audio_va_item=_Item(), _audio_mute_item=_Item(), _user_mute_item=_Item(),
        sounds=sounds, statuses=statuses, applied=applied,
    )
    f._play_sound_event = sounds.append
    f.set_status = statuses.append
    f._check_input_device_configured = lambda: input_ok
    for name in ("set_mute_all", "set_voice_activation", "_sync_voice_activation_controls",
                 "toggle_speak_ready"):
        setattr(f, name, types.MethodType(getattr(cls, name), f))
    return f


def test_mute_plays_sound_only_on_change_and_syncs_controls(main_frame_cls):
    f = _fake_frame(main_frame_cls)
    f.set_mute_all(True)
    f.set_mute_all(True)  # zweiter Weg (z. B. Menü-Haken) – kein zweiter Ton
    assert f.sounds == ["mute_all_on"]
    assert f.client.muted and f.tb_mute.value and f.audio_tab.output_mute.value
    assert f._audio_mute_item.checked and f._user_mute_item.checked
    f.set_mute_all(False)
    assert f.sounds == ["mute_all_on", "mute_all_off"]
    assert not f.tb_mute.value and not f._user_mute_item.checked


def test_silent_restore_has_no_sound(main_frame_cls):
    f = _fake_frame(main_frame_cls)
    f.set_mute_all(True, sound=False, status=False)
    assert f.sounds == [] and f.statuses == [] and f.client.muted


def test_voice_activation_toggle_sounds(main_frame_cls):
    f = _fake_frame(main_frame_cls)
    assert f.set_voice_activation(True)
    f.set_voice_activation(True)
    f.set_voice_activation(False)
    assert f.sounds == ["voiceact_me_on", "voiceact_me_off"]
    assert not f.tb_va.value and not f._audio_va_item.checked


def test_voice_activation_without_input_device(main_frame_cls):
    f = _fake_frame(main_frame_cls, input_ok=False)
    f.tb_va.value = True  # Nutzer hat den Schalter gedrückt
    assert f.set_voice_activation(True) is False
    assert f.client.va is False and f.tb_va.value is False and f.sounds == []


def test_speak_ready_applies_unmutes_and_enables(main_frame_cls):
    f = _fake_frame(main_frame_cls)
    f.set_mute_all(True, sound=False, status=False)
    f.toggle_speak_ready()
    assert f.applied == [False]           # Audio angewendet, ohne Zwischenansage
    assert f.client.muted is False and f._mute_all is False
    assert f.client.va is True and f.tb_va.value is True
    assert f.sounds == ["voiceact_me_on"]  # nur ein Ton für den ganzen Befehl
    from i18n import _
    assert f.statuses[-1] == _("Sprechbereit: Audio angewendet, Sprachaktivierung an, Stummschaltung aufgehoben")


def test_speak_ready_toggles_off(main_frame_cls):
    f = _fake_frame(main_frame_cls)
    f.toggle_speak_ready()
    f.toggle_speak_ready()
    assert f.client.va is False
    assert f.applied == [False]           # Ausschalten öffnet Geräte nicht neu
    assert f.sounds == ["voiceact_me_on", "voiceact_me_off"]


def test_speak_ready_stops_when_apply_fails(main_frame_cls):
    f = _fake_frame(main_frame_cls, apply_ok=False)
    f.set_mute_all(True, sound=False, status=False)
    f.toggle_speak_ready()
    assert f.client.va is False and f.client.muted is True and f.sounds == []
