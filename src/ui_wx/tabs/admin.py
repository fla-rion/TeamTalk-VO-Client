from __future__ import annotations

import threading
from typing import List, TYPE_CHECKING

import wx

from ui_wx.a11y import setup_list_accessible

if TYPE_CHECKING:
    from app import MainFrame


class AdminTab(wx.Panel):
    """Tab 7: Administration -- user accounts, bans, server properties."""

    def __init__(self, parent: wx.Window, frame: MainFrame) -> None:
        super().__init__(parent)
        self.frame = frame
        self.SetName("Administration")

        self._accounts: List = []
        self._bans: List = []

        sizer = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(self, label="Administrationsfunktionen (nur für Admins)")
        info.SetName("Admin-Info")
        sizer.Add(info, 0, wx.ALL, 8)

        # --- User accounts ---
        acc_box = wx.StaticBox(self, label="Benutzerkonten")
        acc_sizer = wx.StaticBoxSizer(acc_box, wx.VERTICAL)

        acc_header = wx.StaticText(acc_box, label="Benutzername, Typ, Notiz")
        acc_header.SetName("Benutzerkonten Kopfzeile")
        acc_sizer.Add(acc_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, 4)
        self.account_list = wx.ListBox(self)
        self.account_list.SetName("Benutzerkonten")
        setup_list_accessible(self.account_list)
        acc_sizer.Add(self.account_list, 1, wx.ALL | wx.EXPAND, 4)

        acc_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.load_accounts_btn = wx.Button(self, label="&Konten laden")
        self.load_accounts_btn.SetName("Konten laden")
        self.load_accounts_btn.Bind(wx.EVT_BUTTON, self.on_load_accounts)
        self.add_account_btn = wx.Button(self, label="Konto &hinzufügen")
        self.add_account_btn.SetName("Konto hinzufügen")
        self.add_account_btn.Bind(wx.EVT_BUTTON, self.on_add_account)
        self.edit_account_btn = wx.Button(self, label="Konto &bearbeiten")
        self.edit_account_btn.SetName("Konto bearbeiten")
        self.edit_account_btn.Bind(wx.EVT_BUTTON, self.on_edit_account)
        self.del_account_btn = wx.Button(self, label="Konto &löschen")
        self.del_account_btn.SetName("Konto löschen")
        self.del_account_btn.Bind(wx.EVT_BUTTON, self.on_del_account)
        acc_btn_row.Add(self.load_accounts_btn, 0, wx.RIGHT, 8)
        acc_btn_row.Add(self.add_account_btn, 0, wx.RIGHT, 8)
        acc_btn_row.Add(self.edit_account_btn, 0, wx.RIGHT, 8)
        acc_btn_row.Add(self.del_account_btn, 0)
        acc_sizer.Add(acc_btn_row, 0, wx.ALL, 4)

        sizer.Add(acc_sizer, 1, wx.ALL | wx.EXPAND, 8)

        # --- Bans ---
        ban_box = wx.StaticBox(self, label="Sperren")
        ban_sizer = wx.StaticBoxSizer(ban_box, wx.VERTICAL)

        ban_header = wx.StaticText(ban_box, label="IP-Adresse, Benutzername, Zeitpunkt")
        ban_header.SetName("Sperrliste Kopfzeile")
        ban_sizer.Add(ban_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, 4)
        self.ban_list = wx.ListBox(self)
        self.ban_list.SetName("Sperrliste")
        setup_list_accessible(self.ban_list)
        ban_sizer.Add(self.ban_list, 1, wx.ALL | wx.EXPAND, 4)

        ban_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.load_bans_btn = wx.Button(self, label="&Sperren laden")
        self.load_bans_btn.SetName("Sperren laden")
        self.load_bans_btn.Bind(wx.EVT_BUTTON, self.on_load_bans)
        self.unban_btn = wx.Button(self, label="&Entsperren")
        self.unban_btn.SetName("Entsperren")
        self.unban_btn.Bind(wx.EVT_BUTTON, self.on_unban)
        self.ban_ip_btn = wx.Button(self, label="IP-Adresse &bannen...")
        self.ban_ip_btn.SetName("IP-Adresse bannen")
        self.ban_ip_btn.Bind(wx.EVT_BUTTON, self.on_ban_ip)
        ban_btn_row.Add(self.load_bans_btn, 0, wx.RIGHT, 8)
        ban_btn_row.Add(self.unban_btn, 0, wx.RIGHT, 8)
        ban_btn_row.Add(self.ban_ip_btn, 0)
        ban_sizer.Add(ban_btn_row, 0, wx.ALL, 4)

        sizer.Add(ban_sizer, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        # --- Server properties ---
        srv_box = wx.StaticBox(self, label="Servereigenschaften")
        srv_sizer = wx.StaticBoxSizer(srv_box, wx.VERTICAL)

        srv_form = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        srv_form.AddGrowableCol(1)

        self.srv_name = self._add_field(srv_form, "Servername", "")
        self.srv_motd = self._add_field(srv_form, "MOTD", "")
        self.srv_maxusers = self._add_field(srv_form, "Max. Benutzer", "0")
        srv_sizer.Add(srv_form, 0, wx.ALL | wx.EXPAND, 4)

        srv_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.load_props_btn = wx.Button(self, label="&Laden")
        self.load_props_btn.SetName("Servereigenschaften laden")
        self.load_props_btn.Bind(wx.EVT_BUTTON, self.on_load_props)
        self.save_props_btn = wx.Button(self, label="&Speichern")
        self.save_props_btn.SetName("Servereigenschaften speichern")
        self.save_props_btn.Bind(wx.EVT_BUTTON, self.on_save_props)
        self.save_config_btn = wx.Button(self, label="&Konfiguration speichern")
        self.save_config_btn.SetName("Konfiguration speichern")
        self.save_config_btn.Bind(wx.EVT_BUTTON, self.on_save_config)
        srv_btn_row.Add(self.load_props_btn, 0, wx.RIGHT, 8)
        srv_btn_row.Add(self.save_props_btn, 0, wx.RIGHT, 8)
        srv_btn_row.Add(self.save_config_btn, 0)
        srv_sizer.Add(srv_btn_row, 0, wx.ALL, 4)

        sizer.Add(srv_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        self.SetSizer(sizer)


    def _add_field(self, sizer, label, value):
        lbl = wx.StaticText(self, label=label)
        lbl.SetName(label)
        ctrl = wx.TextCtrl(self, value=value)
        ctrl.SetName(label)
        sizer.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(ctrl, 1, wx.EXPAND)
        return ctrl

    def check_admin_visibility(self):
        try:
            tt = self.frame.client.tt
            user_type = self.frame.client.get_my_user_type()
            is_admin = bool(user_type & tt.UserType.USERTYPE_ADMIN)
        except Exception:
            is_admin = False
        self.Enable(is_admin)

    # --- Accounts ---

    def on_load_accounts(self, _event):
        self.load_accounts_btn.Disable()
        self.add_account_btn.Disable()
        self.edit_account_btn.Disable()
        self.del_account_btn.Disable()
        self.account_list.Clear()
        self._accounts = []
        self.frame.set_status("Benutzerkonten werden geladen...")

        def worker():
            try:
                cmdid = self.frame.client.do_list_user_accounts()
                if cmdid <= 0:
                    wx.CallAfter(self.frame.set_status, "Benutzerkonten konnten nicht abgerufen werden (keine Admin-Rechte?)")
                    return
                # Kurz warten, damit der Server die Kontoliste schicken kann
                import time
                time.sleep(1.5)
                wx.CallAfter(self._finish_load_accounts)
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Laden der Konten: {e}")
            finally:
                wx.CallAfter(self.load_accounts_btn.Enable)
                wx.CallAfter(self.add_account_btn.Enable)
                wx.CallAfter(self.edit_account_btn.Enable)
                wx.CallAfter(self.del_account_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_load_accounts(self) -> None:
        count = len(self._accounts)
        if count == 0:
            self.frame.set_status(
                "Keine Benutzerkonten empfangen – "
                "prüfe ob du Admin-Rechte und 'Nutzerkonten anzeigen'-Berechtigung hast."
            )
        else:
            self.frame.set_status(f"{count} Benutzerkonto(en) geladen")

    def add_account_to_list(self, account):
        tt_str = self.frame.tt_str
        self._accounts.append(account)
        tt = self.frame.client.tt
        utype = "Administrator" if account.uUserType & tt.UserType.USERTYPE_ADMIN else "Standard"
        label = f"{tt_str(account.szUsername)}, {utype}, {tt_str(account.szNote)}"
        self.account_list.Append(label)

    def on_add_account(self, _event):
        dlg = _AccountDialog(self, self.frame)
        accel = wx.AcceleratorTable([(wx.ACCEL_CMD, ord("W"), wx.ID_CLOSE)])
        dlg.SetAcceleratorTable(accel)
        dlg.Bind(wx.EVT_MENU, lambda e: dlg.EndModal(wx.ID_CANCEL), id=wx.ID_CLOSE)
        if dlg.ShowModal() == wx.ID_OK:
            vals = dlg.get_values()
            dlg.Destroy() # Destroy dialog immediately after getting values

            if not vals["username"] or not vals["password"]:
                self.frame.set_status("Benutzername und Passwort sind erforderlich.")
                return

            self.add_account_btn.Disable()
            self.frame.set_status(f"Konto wird erstellt: {vals['username']}...")

            def worker():
                try:
                    tt = self.frame.client.tt
                    utype = int(tt.UserType.USERTYPE_ADMIN) if vals["admin"] else int(tt.UserType.USERTYPE_DEFAULT)
                    success = self.frame.client.do_new_user_account(
                        vals["username"], vals["password"], utype,
                        user_rights=vals["rights"], note=vals["note"],
                    )
                    if success > 0:
                        wx.CallAfter(self.frame.set_status, f"Konto erstellt: {vals['username']}")
                        wx.CallAfter(self.on_load_accounts, None) # Refresh list
                    else:
                        wx.CallAfter(self.frame.set_status, f"Konto konnte nicht erstellt werden: {vals['username']}")
                except Exception as e:
                    wx.CallAfter(self.frame.set_status, f"Fehler beim Erstellen des Kontos: {e}")
                finally:
                    wx.CallAfter(self.add_account_btn.Enable)

            threading.Thread(target=worker, daemon=True).start()
        else:
            dlg.Destroy() # Destroy dialog if it's not OK.

    def on_edit_account(self, _event):
        sel = self.account_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self._accounts):
            self.frame.set_status("Bitte ein Konto auswählen")
            return
        account = self._accounts[sel]
        dlg = _AccountDialog(self, self.frame, account=account)
        accel = wx.AcceleratorTable([(wx.ACCEL_CMD, ord("W"), wx.ID_CLOSE)])
        dlg.SetAcceleratorTable(accel)
        dlg.Bind(wx.EVT_MENU, lambda e: dlg.EndModal(wx.ID_CANCEL), id=wx.ID_CLOSE)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        vals = dlg.get_values()
        dlg.Destroy()

        if not vals["username"]:
            self.frame.set_status("Benutzername ist erforderlich.")
            return

        self.edit_account_btn.Disable()
        self.frame.set_status(f"Konto wird gespeichert: {vals['username']}...")

        def worker():
            try:
                tt = self.frame.client.tt
                utype = int(tt.UserType.USERTYPE_ADMIN) if vals["admin"] else int(tt.UserType.USERTYPE_DEFAULT)
                success = self.frame.client.do_update_user_account(
                    account, vals["username"], vals["password"], user_type=utype,
                    user_rights=vals["rights"], note=vals["note"],
                )
                if success > 0:
                    wx.CallAfter(self.frame.set_status, f"Konto gespeichert: {vals['username']}")
                    wx.CallAfter(self.on_load_accounts, None) # Refresh list
                else:
                    wx.CallAfter(self.frame.set_status, f"Konto konnte nicht gespeichert werden: {vals['username']}")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Speichern des Kontos: {e}")
            finally:
                wx.CallAfter(self.edit_account_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    def on_del_account(self, _event):
        sel = self.account_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self._accounts):
            self.frame.set_status("Bitte ein Konto auswählen")
            return
        username = self.frame.tt_str(self._accounts[sel].szUsername)
        dlg = wx.MessageDialog(
            self, f"Konto '{username}' wirklich löschen?",
            "Konto löschen", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
        )
        dlg.SetYesNoLabels("Ja", "Nein")
        if dlg.ShowModal() != wx.ID_YES:
            dlg.Destroy()
            return
        dlg.Destroy()

        self.del_account_btn.Disable()
        self.frame.set_status(f"Konto wird gelöscht: {username}...")

        def worker():
            try:
                success = self.frame.client.do_delete_user_account(username)
                if success > 0:
                    wx.CallAfter(self.frame.set_status, f"Konto gelöscht: {username}")
                    wx.CallAfter(self.on_load_accounts, None) # Refresh list
                else:
                    wx.CallAfter(self.frame.set_status, f"Konto konnte nicht gelöscht werden: {username}")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Löschen des Kontos: {e}")
            finally:
                wx.CallAfter(self.del_account_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    # --- Bans ---

    def on_load_bans(self, _event):
        self.load_bans_btn.Disable()
        self.unban_btn.Disable()
        self.ban_list.Clear()
        self._bans = []
        self.frame.set_status("Sperren werden geladen...")

        def worker():
            try:
                self.frame.client.do_list_bans() # This is the blocking call
                wx.CallAfter(self.frame.set_status, "Sperren geladen")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Laden der Sperren: {e}")
            finally:
                wx.CallAfter(self.load_bans_btn.Enable)
                wx.CallAfter(self.unban_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    def add_ban_to_list(self, ban):
        tt_str = self.frame.tt_str
        self._bans.append(ban)
        label = f"{tt_str(ban.szIPAddress)}, {tt_str(ban.szUsername)}, {tt_str(ban.szBanTime)}"
        self.ban_list.Append(label)

    def on_unban(self, _event):
        sel = self.ban_list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self._bans):
            self.frame.set_status("Bitte eine Sperre auswählen")
            return
        ip = self.frame.tt_str(self._bans[sel].szIPAddress)
        
        self.unban_btn.Disable()
        self.frame.set_status(f"Sperre wird aufgehoben für:{ip}...")

        def worker():
            try:
                success = self.frame.client.do_unban_user(ip)
                if success > 0:
                    wx.CallAfter(self.frame.set_status, f"Entsperrt: {ip}")
                    wx.CallAfter(self.on_load_bans, None) # Refresh list
                else:
                    wx.CallAfter(self.frame.set_status, f"Sperre konnte nicht aufgehoben werden für:{ip}")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Aufheben der Sperre: {e}")
            finally:
                wx.CallAfter(self.unban_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    # --- Server properties ---

    def on_load_props(self, _event):
        self.load_props_btn.Disable()
        self.save_props_btn.Disable()
        self.save_config_btn.Disable()
        self.frame.set_status("Servereigenschaften werden geladen...")

        def worker():
            props = None
            try:
                props = self.frame.client.get_server_properties()
                if props is None:
                    wx.CallAfter(self.frame.set_status, "Servereigenschaften konnten nicht geladen werden")
                    return
                tt_str = self.frame.tt_str
                wx.CallAfter(self.srv_name.SetValue, tt_str(props.szServerName))
                wx.CallAfter(self.srv_motd.SetValue, tt_str(props.szMOTDRaw))
                wx.CallAfter(self.srv_maxusers.SetValue, str(int(props.nMaxUsers)))
                wx.CallAfter(self.frame.set_status, "Servereigenschaften geladen")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Laden der Servereigenschaften: {e}")
            finally:
                wx.CallAfter(self.load_props_btn.Enable)
                wx.CallAfter(self.save_props_btn.Enable)
                wx.CallAfter(self.save_config_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    def on_save_props(self, _event):
        name = self.srv_name.GetValue().strip()
        motd = self.srv_motd.GetValue().strip()
        try:
            max_u = int(self.srv_maxusers.GetValue().strip())
        except ValueError:
            max_u = 0

        self.load_props_btn.Disable()
        self.save_props_btn.Disable()
        self.save_config_btn.Disable()
        self.frame.set_status("Servereigenschaften werden gespeichert...")

        def worker():
            try:
                self.frame.client.do_update_server(server_name=name, motd=motd, max_users=max_u)
                wx.CallAfter(self.frame.set_status, "Servereigenschaften gespeichert")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Speichern der Servereigenschaften: {e}")
            finally:
                wx.CallAfter(self.load_props_btn.Enable)
                wx.CallAfter(self.save_props_btn.Enable)
                wx.CallAfter(self.save_config_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    def on_save_config(self, _event):
        self.load_props_btn.Disable()
        self.save_props_btn.Disable()
        self.save_config_btn.Disable()
        self.frame.set_status("Serverkonfiguration wird gespeichert...")

        def worker():
            try:
                self.frame.client.do_save_config()
                wx.CallAfter(self.frame.set_status, "Serverkonfiguration gespeichert")
            except Exception as e:
                wx.CallAfter(self.frame.set_status, f"Fehler beim Speichern der Serverkonfiguration: {e}")
            finally:
                wx.CallAfter(self.load_props_btn.Enable)
                wx.CallAfter(self.save_props_btn.Enable)
                wx.CallAfter(self.save_config_btn.Enable)

        threading.Thread(target=worker, daemon=True).start()

    # --- IP-Adresse bannen ---

    def on_ban_ip(self, _event):
        dlg = wx.TextEntryDialog(self, "IP-Adresse eingeben:", "IP-Adresse bannen")
        dlg.SetName("IP-Adresse bannen")
        if dlg.ShowModal() == wx.ID_OK:
            ip = dlg.GetValue().strip()
            dlg.Destroy()
            if not ip:
                self.frame.set_status("Keine IP-Adresse eingegeben")
                return
            self.ban_ip_btn.Disable()
            self.frame.set_status(f"IP-Adresse wird gebannt: {ip}...")

            def worker():
                try:
                    cmd_id = self.frame.client.do_ban_ip_address(ip)
                    if cmd_id > 0:
                        wx.CallAfter(self.frame.set_status, f"IP-Adresse gebannt: {ip}")
                        wx.CallAfter(self.on_load_bans, None)
                    else:
                        wx.CallAfter(self.frame.set_status, f"Ban fehlgeschlagen für: {ip}")
                except Exception as e:
                    wx.CallAfter(self.frame.set_status, f"Fehler beim Bannen: {e}")
                finally:
                    wx.CallAfter(self.ban_ip_btn.Enable)

            threading.Thread(target=worker, daemon=True).start()
        else:
            dlg.Destroy()



class _AccountDialog(wx.Dialog):
    """Formular zum Anlegen ODER Bearbeiten eines Benutzerkontos.

    Ohne `account` (None): leeres Formular fuer ein neues Konto.
    Mit `account` (Server-UserAccount-Struct): Formular vorausgefuellt,
    Benutzername gesperrt (Primaerschluessel, siehe
    `TeamTalkClient.do_update_user_account`), Passwort optional (leer =
    unveraendert lassen).
    """

    # (Anzeigename, UserRight-Konstantenname aus TeamTalk5.UserRight)
    _RIGHTS = [
        ("&Kanal erstellen", "USERRIGHT_CREATE_TEMPORARY_CHANNEL"),
        ("&Broadcast senden", "USERRIGHT_TEXTMESSAGE_BROADCAST"),
        ("Kanal-&Operator", "USERRIGHT_OPERATOR_ENABLE"),
        ("&Aufnahme erlaubt", "USERRIGHT_RECORD_VOICE"),
        ("&Upload erlaubt", "USERRIGHT_UPLOAD_FILES"),
        ("&Download erlaubt", "USERRIGHT_DOWNLOAD_FILES"),
    ]

    def __init__(self, parent, frame, account=None):
        title = "Konto bearbeiten" if account is not None else "Neues Benutzerkonto"
        super().__init__(parent, title=title, size=(380, 440))
        tt = frame.client.tt
        self._editing = account is not None

        sizer = wx.BoxSizer(wx.VERTICAL)
        form = wx.FlexGridSizer(cols=2, vgap=6, hgap=12)
        form.AddGrowableCol(1)

        form.Add(wx.StaticText(self, label="Benutzername"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._username = wx.TextCtrl(self)
        self._username.SetName("Benutzername")
        form.Add(self._username, 1, wx.EXPAND)

        pw_label = "Passwort (leer = unverändert)" if self._editing else "Passwort"
        form.Add(wx.StaticText(self, label=pw_label), 0, wx.ALIGN_CENTER_VERTICAL)
        self._password = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self._password.SetName(pw_label)
        form.Add(self._password, 1, wx.EXPAND)

        form.Add(wx.StaticText(self, label="Notiz"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._note = wx.TextCtrl(self)
        self._note.SetName("Notiz")
        form.Add(self._note, 1, wx.EXPAND)

        self._admin_check = wx.CheckBox(self, label="&Administrator")
        self._admin_check.SetName("Administrator")

        sizer.Add(form, 0, wx.ALL | wx.EXPAND, 12)
        sizer.Add(self._admin_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        rights_box = wx.StaticBox(self, label="Rechte")
        rights_sizer = wx.StaticBoxSizer(rights_box, wx.VERTICAL)
        self._rights_checks = []
        for label, const_name in self._RIGHTS:
            cb = wx.CheckBox(rights_box, label=label)
            cb.SetName(label.replace("&", ""))
            self._rights_checks.append((cb, int(getattr(tt.UserRight, const_name))))
            rights_sizer.Add(cb, 0, wx.ALL, 2)
        sizer.Add(rights_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)

        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 12)
        self.SetSizer(sizer)

        if account is not None:
            self._username.SetValue(frame.tt_str(account.szUsername))
            self._username.SetEditable(False)
            self._note.SetValue(frame.tt_str(account.szNote))
            utype = int(getattr(account, "uUserType", 0))
            self._admin_check.SetValue(bool(utype & int(tt.UserType.USERTYPE_ADMIN)))
            rights = int(getattr(account, "uUserRights", 0))
            for cb, bit in self._rights_checks:
                cb.SetValue(bool(rights & bit))
            self._password.SetFocus()
        else:
            self._username.SetFocus()

    def get_values(self):
        rights = 0
        for cb, bit in self._rights_checks:
            if cb.GetValue():
                rights |= bit
        return {
            "username": self._username.GetValue().strip(),
            "password": self._password.GetValue().strip(),
            "note": self._note.GetValue().strip(),
            "admin": self._admin_check.GetValue(),
            "rights": rights,
        }
