import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui.user_names import format_user_name  # noqa: E402


def test_nickname_mode_is_default_and_falls_back():
    assert format_user_name("Flo", "flarion") == "Flo"
    assert format_user_name("", "flarion") == "flarion"
    assert format_user_name("", "", fallback="Benutzer") == "Benutzer"


def test_username_mode_falls_back_to_nickname():
    assert format_user_name("Flo", "flarion", "username") == "flarion"
    assert format_user_name("Flo", "", "username") == "Flo"


def test_both_mode():
    assert format_user_name("Flo", "flarion", "both") == "Flo (flarion)"
    assert format_user_name("Flo", "Flo", "both") == "Flo"
    assert format_user_name("", "flarion", "both") == "flarion"
