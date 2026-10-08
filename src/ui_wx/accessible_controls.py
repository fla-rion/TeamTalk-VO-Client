"""accessible_controls.py – VoiceOver-freundlichere Ersatz-Controls (wx/macOS).

wx.SpinCtrlDouble kombiniert Textfeld und Spin-Buttons in einem einzigen
nativen Control; VoiceOver liest Wertänderungen über die Pfeiltasten dabei
manchmal unzuverlässig vor. AccessibleSpinCtrl trennt beides in ein
eigenständiges wx.TextCtrl (primärer Interaktionspunkt, VoiceOver liest
Textfeld-Änderungen zuverlässig vor) und einen synchronisierten
wx.SpinButton für Maus-Nutzer – Pfeiltasten im Textfeld ändern den Wert
direkt.

CustomTextEntryDialog erweitert wx.TextEntryDialog um frei wählbare
Button-Labels (das native TextEntryDialog erlaubt nur Standard-OK/Abbrechen).

Inspiration (nicht übernommener Code): m45wxcontrols von schulle4u
(github.com/schulle4u/m45wxcontrols).
"""
from __future__ import annotations

import wx


class AccessibleSpinCtrl(wx.Panel):
    """Textfeld + synchronisierter SpinButton als Ersatz für wx.SpinCtrl und
    wx.SpinCtrlDouble.

    Drop-in für die in diesem Projekt genutzten Aufrufstile::

        ctrl = AccessibleSpinCtrl(parent, min=-1000.0, max=1000.0, inc=0.1, initial=0.0)
        ctrl = AccessibleSpinCtrl(parent, value="30", min=0, max=100)   # wie wx.SpinCtrl
        ctrl.Bind(wx.EVT_SPINCTRL, handler)                              # bei Nutzeränderung
        value = ctrl.GetValue()   # int bei ganzzahliger Schrittweite, sonst float
        ctrl.SetName("Position X")

    Wie bei wx.SpinCtrl löst ``SetValue`` kein Ereignis aus; Änderungen durch
    den Nutzer (Pfeiltasten, Spin-Knopf, Eingabe bestätigt/Fokus verlassen)
    senden ``wx.EVT_SPINCTRL``.
    """

    def __init__(
        self,
        parent,
        id=wx.ID_ANY,
        value="",
        pos=wx.DefaultPosition,
        size=wx.DefaultSize,
        style=0,
        min=0.0,
        max=100.0,
        initial=None,
        inc=1,
        digits=None,
        name="AccessibleSpinCtrl",
    ) -> None:
        super().__init__(parent, id, pos, size, style=wx.TAB_TRAVERSAL, name=name)
        self._min = float(min)
        self._max = float(max)
        self._inc = float(inc)
        self._digits = digits if digits is not None else (2 if abs(self._inc) < 1 else 0)
        # Ganzzahl-Modus wie wx.SpinCtrl: GetValue() liefert int
        self._integer = self._digits <= 0 and float(inc).is_integer()
        self._last_spin_pos = 500000
        if initial is None:
            try:
                initial = float(str(value).strip().replace(",", ".")) if str(value).strip() else self._min
            except ValueError:
                initial = self._min

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._text = wx.TextCtrl(self, value="", style=wx.TE_PROCESS_ENTER)
        self._spin = wx.SpinButton(self, style=wx.SP_VERTICAL | wx.SP_ARROW_KEYS)
        self._spin.SetRange(0, 1_000_000)
        self._spin.SetValue(self._last_spin_pos)

        # v10.5.0 – kein wx.ALIGN_CENTER_VERTICAL zusammen mit wx.EXPAND: wx 3.3
        # bricht den Aufbau mit einer Sizer-Assertion ab (App-Start/Dialog).
        sizer.Add(self._text, 1, wx.EXPAND)
        sizer.Add(self._spin, 0, wx.ALIGN_CENTER_VERTICAL)
        self.SetSizerAndFit(sizer)

        self._text.Bind(wx.EVT_TEXT_ENTER, self._on_text_commit)
        self._text.Bind(wx.EVT_KILL_FOCUS, self._on_text_commit)
        self._text.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self._spin.Bind(wx.EVT_SPIN, self._on_spin)

        self.SetValue(initial)
        self._last_reported = self.GetValue()

    # -- Formatierung -----------------------------------------------------

    def _format(self, value: float) -> str:
        if self._digits <= 0:
            return str(int(round(value)))
        return f"{value:.{self._digits}f}"

    def _clamp(self, value: float) -> float:
        return max(self._min, min(self._max, value))

    # -- Öffentliche API (Drop-in zu wx.SpinCtrlDouble) --------------------

    def GetValue(self):
        try:
            value = self._clamp(float(self._text.GetValue().strip().replace(",", ".")))
        except ValueError:
            value = self._clamp(0.0)
        return int(round(value)) if self._integer else value

    def SetValue(self, value) -> None:
        self._text.ChangeValue(self._format(self._clamp(float(value))))

    def SetRange(self, min_val: float, max_val: float) -> None:
        self._min = float(min_val)
        self._max = float(max_val)
        self.SetValue(self.GetValue())

    def GetMin(self):
        return int(self._min) if self._integer else self._min

    def GetMax(self):
        return int(self._max) if self._integer else self._max

    def SetMin(self, min_val) -> None:
        self.SetRange(min_val, self._max)

    def SetMax(self, max_val) -> None:
        self.SetRange(self._min, max_val)

    def SetFocus(self) -> None:
        # Fokus auf das Textfeld, nicht auf das umschließende Panel
        self._text.SetFocus()

    def SetHelpText(self, text: str) -> None:
        self._text.SetHelpText(text)
        super().SetHelpText(text)

    def SetToolTip(self, tip) -> None:
        self._text.SetToolTip(tip)
        super().SetToolTip(tip)

    def SetIncrement(self, inc: float) -> None:
        self._inc = float(inc)

    def SetDigits(self, digits: int) -> None:
        self._digits = int(digits)
        self.SetValue(self.GetValue())

    def SetName(self, name: str) -> bool:
        # VoiceOver liest den Namen des inneren NSTextField vor, nicht des
        # umschließenden Panels – Konvention wie im übrigen Projekt
        # (siehe z.B. ui_wx/tabs/audio.py: `self.input_gain.SetName(...)`).
        self._text.SetName(name)
        return super().SetName(name)

    def Enable(self, enable: bool = True) -> bool:
        self._text.Enable(enable)
        self._spin.Enable(enable)
        return super().Enable(enable)

    def GetTextCtrl(self) -> wx.TextCtrl:
        """Zugriff auf das innere Textfeld, z.B. für zusätzliche Bindings."""
        return self._text

    # -- Interne Handler ----------------------------------------------------

    def _notify_if_changed(self) -> None:
        """wx.EVT_SPINCTRL senden, wenn der Nutzer den Wert geändert hat."""
        value = self.GetValue()
        if value == self._last_reported:
            return
        self._last_reported = value
        evt = wx.SpinEvent(wx.wxEVT_SPINCTRL, self.GetId())
        evt.SetEventObject(self)
        evt.SetPosition(int(round(value)))
        self.GetEventHandler().ProcessEvent(evt)

    def _on_text_commit(self, event) -> None:
        self.SetValue(self.GetValue())
        self._notify_if_changed()
        event.Skip()

    def _on_key_down(self, event) -> None:
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_UP:
            self.SetValue(self.GetValue() + self._inc)
            self._notify_if_changed()
        elif keycode == wx.WXK_DOWN:
            self.SetValue(self.GetValue() - self._inc)
            self._notify_if_changed()
        else:
            event.Skip()

    def _on_spin(self, event) -> None:
        pos = event.GetPosition()
        delta = pos - self._last_spin_pos
        self._last_spin_pos = pos
        if delta > 0:
            self.SetValue(self.GetValue() + self._inc)
        elif delta < 0:
            self.SetValue(self.GetValue() - self._inc)
        self._notify_if_changed()


class CustomTextEntryDialog(wx.Dialog):
    """wx.TextEntryDialog-Ersatz mit frei wählbaren Button-Labels.

    Das native wx.TextEntryDialog erlaubt nur die System-Standardlabels für
    OK/Abbrechen. CustomTextEntryDialog bietet dieselbe Kern-API
    (GetValue/SetValue, ShowModal gibt wx.ID_OK/wx.ID_CANCEL zurück), lässt
    aber `ok_label`/`cancel_label` frei wählen.
    """

    def __init__(
        self,
        parent,
        message: str,
        caption: str = "",
        value: str = "",
        ok_label: str = "",
        cancel_label: str = "",
        style=wx.OK | wx.CANCEL,
    ) -> None:
        from i18n import _
        ok_label = ok_label or _("OK")
        cancel_label = cancel_label or _("Abbrechen")
        super().__init__(parent, title=caption, style=wx.DEFAULT_DIALOG_STYLE)
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(wx.StaticText(self, label=message), 0, wx.ALL, 10)
        self._text = wx.TextCtrl(self, value=value)
        # VoiceOver: Eingabefeld trägt die Frage als Namen
        self._text.SetName(message.rstrip(": ").strip() or caption)
        root.Add(self._text, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 10)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.AddStretchSpacer()
        if style & wx.CANCEL:
            cancel_btn = wx.Button(self, wx.ID_CANCEL, label=cancel_label)
            btn_row.Add(cancel_btn, 0, wx.RIGHT, 6)
        ok_btn = wx.Button(self, wx.ID_OK, label=ok_label)
        ok_btn.SetDefault()
        btn_row.Add(ok_btn, 0)
        root.Add(btn_row, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizerAndFit(root)
        self._text.SetFocus()

    def GetValue(self) -> str:
        return self._text.GetValue()

    def SetValue(self, value: str) -> None:
        self._text.SetValue(value)
