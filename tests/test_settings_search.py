import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import settings_search as ss  # noqa: E402


def _e(label, category="", section="Audio & Aufnahme", aliases=()):
    return ss.SettingEntry(section, section, category, label, tuple(aliases))


ENTRIES = [
    _e("Eingabegerät", "Geräte"),
    _e("Ausgabegerät", "Geräte"),
    _e("Sprachaktivierung", "Sprachaktivierung"),
    _e("Aktivierungspegel (0–100)", "Sprachaktivierung"),
    _e("Nachlauf (ms)", "Sprachaktivierung", aliases=("Sprachaktivierung Nachlauf",)),
    _e("Bei Gerätewechsel automatisch anwenden", "Aktionen"),
    _e("App-Sprache", "Allgemein", section="Allgemein"),
]


def test_clean_label():
    assert ss.clean_label("&Push-to-Talk (Leertaste halten):") == "Push-to-Talk (Leertaste halten)"
    assert ss.clean_label("Audio an&wenden\tCtrl+A") == "Audio anwenden"
    assert ss.clean_label("Rock && Roll") == "Rock & Roll"


def test_umlauts_and_case():
    labels = [e.label for e in ss.search(ENTRIES, "gerate")]
    assert labels[:2] == ["Eingabegerät", "Ausgabegerät"] or "Eingabegerät" in labels
    assert [e.label for e in ss.search(ENTRIES, "GERAETE")] == [e.label for e in ss.search(ENTRIES, "geräte")]


def test_prefix_ranks_before_substring():
    labels = [e.label for e in ss.search(ENTRIES, "sprachakt")]
    assert labels[0] == "Sprachaktivierung"


def test_all_words_must_match_and_context_counts():
    labels = [e.label for e in ss.search(ENTRIES, "pegel sprachaktivierung")]
    assert labels == ["Aktivierungspegel (0–100)"]
    assert ss.search(ENTRIES, "pegel video") == []


def test_alias_is_searchable():
    assert [e.label for e in ss.search(ENTRIES, "nachlauf")] == ["Nachlauf (ms)"]


def test_duplicates_collapsed_and_empty_query():
    dup = ENTRIES + [_e("Eingabegerät", "Geräte")]
    assert [e.label for e in ss.search(dup, "eingabe")] == ["Eingabegerät"]
    assert ss.search(ENTRIES, "   ") == []


def test_display_text():
    e = _e("Nachlauf (ms)", "Sprachaktivierung")
    assert e.display == "Nachlauf (ms), Sprachaktivierung, Audio & Aufnahme"
    assert _e("Sprachaktivierung", "Sprachaktivierung").display == "Sprachaktivierung, Audio & Aufnahme"
