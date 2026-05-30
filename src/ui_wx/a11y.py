# Thin re-export — alle Implementierungen liegen in src/ui/a11y.py.
# ui_wx.a11y importiert von dort, damit Fixes nur an einem Ort gepflegt werden müssen.
from ui.a11y import (  # noqa: F401
    setup_list_accessible,
    patch_list_row_accessibility,
    patch_control_accessibility,
    patch_button_accessibility,
    post_voiceover_announcement,
    LiveRegionAnnouncer,
    FocusRestoreHelper,
    bind_listbox_keyboard_nav,
    setup_tab_order,
    set_accessible_name,
    set_accessible_help,
    audit_accessibility,
)
