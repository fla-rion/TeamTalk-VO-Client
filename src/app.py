"""Platform router — macOS → app_wx (wxPython), Windows/Linux → app_qt (PySide6)."""
import sys


def _apply_pending_settings_restore() -> None:
    """Ein beim letzten Lauf vorbereitetes Einstellungs-Backup übernehmen,
    bevor die App settings.db öffnet (siehe settings_backup.py)."""
    try:
        from platform_paths import app_data_dir
        import settings_backup
        settings_backup.apply_pending_restore_at_startup(app_data_dir())
    except Exception as exc:  # Start nie daran scheitern lassen
        print(f"[Backup] Wiederherstellung beim Start fehlgeschlagen: {exc}", file=sys.stderr)


if __name__ == "__main__":
    _apply_pending_settings_restore()
    if sys.platform == "darwin":
        from app_wx import run_app
    else:
        from app_qt import run_app
    run_app()
