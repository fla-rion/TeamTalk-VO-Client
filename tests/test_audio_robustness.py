"""Tests für Geräte-Gedächtnis (ausgestecktes Gerät), Mikrofon-Watchdog und
Medien-Gesamtlautstärke – ohne SDK/Server, mit Fake-Objekten."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import audio_device_memory as adm  # noqa: E402
import mic_watchdog as mw  # noqa: E402


def _dev(dev_id, name, uid=""):
    return SimpleNamespace(nDeviceID=dev_id, szDeviceName=name, szDeviceID=uid)


def _s(x):
    return x


# --- audio_device_memory -------------------------------------------------

def test_find_by_uid_even_if_index_shifted():
    devs = [_dev(0, "Built-in", "BI"), _dev(1, "USB Headset", "USB-1")]
    assert adm.find_device_index(devs, ("USB-1", "USB Headset"), _s) == 1
    shifted = [_dev(0, "USB Headset", "USB-1"), _dev(1, "Built-in", "BI")]
    assert adm.find_device_index(shifted, ("USB-1", "USB Headset"), _s) == 0


def test_uid_mismatch_does_not_fall_back_to_same_named_other_device():
    devs = [_dev(0, "USB Headset", "USB-2")]
    assert adm.find_device_index(devs, ("USB-1", "USB Headset"), _s) == -1


def test_name_fallback_when_soundsystem_has_no_uid():
    devs = [_dev(0, "Built-in"), _dev(1, "USB Headset")]
    assert adm.find_device_index(devs, ("", "USB Headset"), _s) == 1


def test_plan_selection_missing_device_gets_placeholder():
    devs = [_dev(0, "Built-in", "BI")]
    labels, idx, missing = adm.plan_selection(
        devs, ["Built-in"], ("USB-1", "USB Headset"), (0,), _s, "nicht verbunden"
    )
    assert missing is True
    assert labels == ["Built-in", "USB Headset (nicht verbunden)"]
    assert idx == 1
    # Geöffnet wird übergangsweise das Standardgerät
    assert adm.resolve_open_device(devs, idx, 0) is devs[0]


def test_plan_selection_device_back():
    devs = [_dev(0, "Built-in", "BI"), _dev(1, "USB Headset", "USB-1")]
    labels, idx, missing = adm.plan_selection(
        devs, ["Built-in", "USB Headset"], ("USB-1", "USB Headset"), (0,), _s, "nicht verbunden"
    )
    assert (labels, idx, missing) == (["Built-in", "USB Headset"], 1, False)


def test_plan_selection_without_wanted_uses_fallback():
    devs = [_dev(3, "A"), _dev(7, "B")]
    _labels, idx, missing = adm.plan_selection(devs, ["A", "B"], None, (None, 7), _s, "x")
    assert (idx, missing) == (1, False)


# --- mic_watchdog --------------------------------------------------------

READY_TX = mw.CLIENT_SNDINPUT_READY | mw.CLIENT_TX_VOICE
READY_VA_SILENT = mw.CLIENT_SNDINPUT_READY | mw.CLIENT_SNDINPUT_VOICEACTIVATED
READY_VA_ACTIVE = READY_VA_SILENT | mw.CLIENT_SNDINPUT_VOICEACTIVE


def _run(wd, seq):
    return [wd.tick(t, s) for t, s in seq]


def test_watchdog_silence_under_voice_activation_never_triggers():
    wd = mw.MicWatchdog()
    seq = [(t, mw.MicSample(READY_VA_SILENT, 100, True)) for t in range(0, 120)]
    assert set(_run(wd, seq)) == {mw.ACTION_NONE}


def test_watchdog_progressing_bytes_never_trigger():
    wd = mw.MicWatchdog()
    seq = [(t, mw.MicSample(READY_TX, 100 + t * 50, True)) for t in range(0, 60)]
    assert set(_run(wd, seq)) == {mw.ACTION_NONE}


def test_watchdog_not_in_voice_channel_never_triggers():
    wd = mw.MicWatchdog()
    seq = [(t, mw.MicSample(READY_TX, 100, False)) for t in range(0, 60)]
    assert set(_run(wd, seq)) == {mw.ACTION_NONE}


def test_watchdog_stall_restarts_once_then_gives_up_once():
    wd = mw.MicWatchdog(stall_seconds=6, retry_cooldown=30)
    actions = _run(wd, [(t, mw.MicSample(READY_VA_ACTIVE, 500, True)) for t in range(0, 100)])
    assert actions.count(mw.ACTION_RESTART) == 1
    assert actions.count(mw.ACTION_GIVE_UP) == 1
    assert actions.index(mw.ACTION_RESTART) == 6


def test_watchdog_rearms_after_transmission_resumes():
    wd = mw.MicWatchdog(stall_seconds=6, retry_cooldown=0)
    _run(wd, [(t, mw.MicSample(READY_TX, 500, True)) for t in range(0, 8)])
    # Nach dem Neustart geht wieder etwas raus …
    _run(wd, [(t, mw.MicSample(READY_TX, 500 + t, True)) for t in range(8, 12)])
    # … späterer erneuter Stillstand löst wieder einen Neustart aus
    actions = _run(wd, [(t, mw.MicSample(READY_TX, 600, True)) for t in range(12, 30)])
    assert actions.count(mw.ACTION_RESTART) == 1


def test_sdk_sends_voice_mirrors_can_transmit():
    me = 5
    voice = mw.STREAMTYPE_VOICE
    # Normaler Kanal: senden
    assert mw.sdk_sends_voice(0, {}, me, READY_TX)
    # Unterrichtsmodus ohne Sprechrecht: SDK verwirft die Pakete
    assert not mw.sdk_sends_voice(mw.CHANNEL_CLASSROOM, {}, me, READY_TX)
    assert mw.sdk_sends_voice(mw.CHANNEL_CLASSROOM, {me: voice}, me, READY_TX)
    assert mw.sdk_sends_voice(mw.CHANNEL_CLASSROOM, {mw.TRANSMITUSERS_FREEFORALL: voice}, me, READY_TX)
    # Nur Video erlaubt zählt nicht als Sprechrecht
    assert not mw.sdk_sends_voice(mw.CHANNEL_CLASSROOM, {me: 0x4}, me, READY_TX)
    # Außerhalb des Unterrichtsmodus bedeutet die Liste "gesperrt"
    assert not mw.sdk_sends_voice(0, {me: voice}, me, READY_TX)
    # Kanal ohne Sprachaktivierung: VA-Sprache wird nicht gesendet, PTT schon
    assert not mw.sdk_sends_voice(mw.CHANNEL_NO_VOICEACTIVATION, {}, me, READY_VA_ACTIVE)
    assert mw.sdk_sends_voice(mw.CHANNEL_NO_VOICEACTIVATION, {}, me, READY_TX)


def test_transmit_users_parses_2d_and_flat_arrays():
    assert mw.transmit_users(type("C", (), {"transmitUsers": [[5, 1], [7, 3], [0, 0]]})()) == {5: 1, 7: 3}
    assert mw.transmit_users(type("C", (), {"transmitUsers": [5, 1, 0, 0]})()) == {5: 1}


class _WdClient:
    def __init__(self, channel_type, tx_users, flags):
        self._ch = type("Ch", (), {
            "audiocodec": type("A", (), {"nCodec": 3})(),
            "uChannelType": channel_type,
            "transmitUsers": tx_users,
        })()
        self._flags = flags

    def is_connected(self):
        return True

    def get_flags(self):
        return self._flags

    def get_client_statistics(self):
        return type("S", (), {"nVoiceBytesSent": 500})()

    def get_my_channel_id(self):
        return 1

    def get_channel(self, _cid):
        return self._ch

    def get_my_user_id(self):
        return 5


def test_watchdog_never_restarts_in_classroom_without_permission():
    client = _WdClient(mw.CHANNEL_CLASSROOM, [[0, 0]], READY_VA_ACTIVE)
    sample = mw.sample_from_client(client)
    assert sample is not None and sample.in_voice_channel is False
    wd = mw.MicWatchdog()
    assert set(_run(wd, [(t, sample) for t in range(0, 120)])) == {mw.ACTION_NONE}


def test_watchdog_still_counts_normal_channel():
    sample = mw.sample_from_client(_WdClient(0, [[0, 0]], READY_VA_ACTIVE))
    assert sample is not None and sample.in_voice_channel is True


# --- Medien-Gesamtlautstärke (TeamTalkClient ohne SDK) --------------------

class _FakeTT:
    class StreamType:
        STREAMTYPE_VOICE = 1
        STREAMTYPE_MEDIAFILE_AUDIO = 4
        STREAMTYPE_MEDIAFILE_VIDEO = 8

    def __init__(self):
        self.calls = []

    def _SetUserVolume(self, _inst, uid, st, vol):
        self.calls.append((uid, st, vol))
        return True


def _fake_client():
    from teamtalk_client.client import TeamTalkClient
    c = TeamTalkClient.__new__(TeamTalkClient)
    c.tt = _FakeTT()
    c.client = SimpleNamespace(_tt=None, getServerUsers=lambda: [SimpleNamespace(nUserID=5), SimpleNamespace(nUserID=6)])
    c._user_media_base = {}
    c._media_master_pct = 100
    c._connected = True
    return c


def test_media_master_scales_per_user_base_and_new_users():
    c = _fake_client()
    c.set_user_volume(5, 4, 2000)            # pro Nutzer gewählt
    assert c.tt.calls[-1] == (5, 4, 2000)
    c.tt.calls.clear()
    c.set_media_master_volume(50)
    assert (5, 4, 1000) in c.tt.calls        # 2000 × 50 %
    assert (6, 4, 500) in c.tt.calls         # Standard 1000 × 50 %
    c.tt.calls.clear()
    c.apply_media_master_to_user(9)          # später hinzukommender Nutzer
    assert c.tt.calls == [(9, 4, 500)]
    assert c.get_user_media_volume(5) == 2000


def test_media_master_leaves_voice_untouched():
    c = _fake_client()
    c.set_media_master_volume(50)
    c.tt.calls.clear()
    c.set_user_volume(5, 1, 3000)
    assert c.tt.calls == [(5, 1, 3000)]
    c.tt.calls.clear()
    c.set_user_volume(5, 4 | 8, 2000)        # STREAMTYPE_MEDIAFILE (Audio+Video)
    assert (5, 4, 1000) in c.tt.calls and (5, 8, 2000) in c.tt.calls


def test_media_master_default_is_noop_for_new_users():
    c = _fake_client()
    c.apply_media_master_to_user(9)
    assert c.tt.calls == []


# --- Nachlauf der Sprachaktivierung --------------------------------------

def test_va_delay_default_matches_sdk():
    assert adm.DEFAULT_VA_STOP_DELAY_MS == 1500


def test_va_delay_old_zero_is_migrated_once():
    # Vor v10.7.0 ungefragt gespeicherte 0 → SDK-Vorgabe (sonst zerstückelte Stimme)
    assert adm.stored_va_delay({"va_delay": 0}) == 1500
    assert adm.stored_va_delay({}) == 1500
    # Nach der Migration ist eine bewusst gesetzte 0 erlaubt
    assert adm.stored_va_delay({"va_delay": 0, adm.VA_DELAY_MIGRATION_KEY: True}) == 0
    assert adm.stored_va_delay({"va_delay": 800}) == 800
    assert adm.stored_va_delay({"va_delay": "kaputt"}) == 1500


# --- Gerätewechsel ohne falsche Auswahl ----------------------------------

def test_remap_device_id_follows_identity_not_index():
    old = [_dev(0, "Mac mini-Lautsprecher"), _dev(1, "USB Headset")]
    # Nach dem Neustart steht ein neues Gerät vorne – Indizes verschoben
    new = [_dev(0, "Microsoft Teams Audio"), _dev(1, "Mac mini-Lautsprecher"), _dev(2, "USB Headset")]
    assert adm.remap_device_id(old, 1, new, _s) == 2
    assert adm.remap_device_id(old, 0, new, _s) == 1
    assert adm.remap_device_id(old, 1, [_dev(0, "Mac mini-Lautsprecher")], _s) is None
    assert adm.remap_device_id(old, -1, new, _s) is None


def test_plan_selection_never_falls_back_to_virtual_device():
    import system_audio as sa
    devs = [_dev(1978, "TeamTalk Virtual Sound Device"), _dev(0, "NT Headless"), _dev(1, "Mac mini-Lautsprecher")]
    devs[1].szDeviceName = "Microsoft Teams Audio"
    _labels, idx, missing = adm.plan_selection(
        devs, ["a", "b", "c"], None, (None, None), _s, "x",
        is_virtual=lambda d: sa.is_virtual_device_name(d.szDeviceName),
    )
    assert (idx, missing) == (2, False)


def test_virtual_device_names():
    import system_audio as sa
    for name in ("Microsoft Teams Audio", "ZoomAudioDevice", "TeamTalk Virtual Sound Device",
                 "BlackHole 2ch", "Loopback Audio"):
        assert sa.is_virtual_device_name(name), name
    for name in ("MacBook Pro-Lautsprecher", "AirPods Pro", "USB Headset", "Jabra Evolve2 65"):
        assert not sa.is_virtual_device_name(name), name


def test_coreaudio_change_classification():
    import coreaudio_watch as cw
    a = (frozenset({1, 2}), 1, 2)
    assert cw.classify_change(a, a) is None
    assert cw.classify_change(a, (frozenset({1, 2}), 1, 1)) == cw.CHANGE_DEFAULTS
    assert cw.classify_change(a, (frozenset({1, 2, 3}), 1, 2)) == cw.CHANGE_DEVICES
    assert cw.classify_change(None, a) == cw.CHANGE_DEVICES
