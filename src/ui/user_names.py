"""Anzeige von Nutzernamen gemäß Einstellung "Nutzer anzeigen als".

Modi (``AppSettings.user_name_display``):
  "nickname"  – Nickname (Standard, bisheriges Verhalten)
  "username"  – Benutzername (Kontoname)
  "both"      – "Nickname (Benutzername)"

Ist der gewählte Name leer, wird der andere angezeigt.
"""

NAME_DISPLAY_MODES = ("nickname", "username", "both")


def format_user_name(nickname: str, username: str, mode: str = "nickname", fallback: str = "") -> str:
    nick = (nickname or "").strip()
    user = (username or "").strip()
    if mode == "username":
        return user or nick or fallback
    if mode == "both":
        if nick and user and nick != user:
            return f"{nick} ({user})"
        return nick or user or fallback
    return nick or user or fallback
