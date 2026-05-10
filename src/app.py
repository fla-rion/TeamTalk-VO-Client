"""Platform router — macOS → app_wx (wxPython), Windows/Linux → app_qt (PySide6)."""
import sys

if __name__ == "__main__":
    if sys.platform == "darwin":
        from app_wx import run_app
    else:
        from app_qt import run_app
    run_app()
