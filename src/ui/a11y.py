"""Barrierefreiheits-Helfer: VoiceOver-Rollen für wxPython auf macOS."""
from __future__ import annotations

import sys

import wx


def _get_table_subview(nsview):
    """Gibt das wxNSTableView-Unterelement eines NSScrollView zurück."""
    try:
        for sv in nsview.subviews():
            cls = sv.__class__.__name__
            if "TableView" in cls or "ListView" in cls:
                return sv
            # NSClipView enthält die TableView
            if "ClipView" in cls:
                for child in sv.subviews():
                    if "TableView" in cls or "View" in child.__class__.__name__:
                        return child
        return None
    except Exception:
        return None


def setup_list_accessible(lb: wx.ListBox) -> None:
    """Setzt die native NSAccessibility-Rolle auf AXList (VoiceOver: 'Liste')."""
    if sys.platform != "darwin":
        return

    def _apply():
        try:
            import objc  # noqa: PLC0415
            from AppKit import NSAccessibilityListRole  # noqa: PLC0415

            handle = lb.GetHandle()
            if not handle:
                return
            nsview = objc.objc_object(c_void_p=handle)

            # NSScrollView → NSClipView → wxNSTableView
            tableview = None
            for sv in nsview.subviews():
                cls = sv.__class__.__name__
                if "ClipView" in cls:
                    for child in sv.subviews():
                        tableview = child
                        break
                    break

            if tableview is None:
                return

            tableview.setAccessibilityRole_(NSAccessibilityListRole)
            tableview.setAccessibilityRoleDescription_("Liste")
        except Exception:
            pass

    # Muss nach dem Erstellen des Fensters ausgeführt werden
    wx.CallAfter(_apply)
