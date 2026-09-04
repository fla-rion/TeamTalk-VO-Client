"""TeamTalk Android SDK Wrapper via Rubicon-Java.

Drop-in-Ersatz für TeamTalkClient (src/teamtalk_client/client.py),
der intern das offizielle BearWare TeamTalk5.aar über Rubicon-Java nutzt.

Voraussetzung: TeamTalk5.aar muss in libs/ liegen und ist per
Briefcase support_libs eingebunden (siehe pyproject.toml).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from rubicon.java import JavaClass, JavaInterface, java_method

# ---------------------------------------------------------------------------
# TeamTalk Java-Klassen aus dem SDK
# ---------------------------------------------------------------------------

TeamTalk5 = JavaClass("dk/bearware/TeamTalk5")
ClientEvent = JavaClass("dk/bearware/ClientEvent")
User = JavaClass("dk/bearware/User")
Channel = JavaClass("dk/bearware/Channel")
TextMessage = JavaClass("dk/bearware/TextMessage")
ServerProperties = JavaClass("dk/bearware/ServerProperties")
FileTransfer = JavaClass("dk/bearware/FileTransfer")
RemoteFile = JavaClass("dk/bearware/RemoteFile")
UserAccount = JavaClass("dk/bearware/UserAccount")
BannedUser = JavaClass("dk/bearware/BannedUser")
SoundDevice = JavaClass("dk/bearware/SoundDevice")
TTMessage = JavaClass("dk/bearware/TTMessage")
AudioCodec = JavaClass("dk/bearware/AudioCodec")
VideoCodec = JavaClass("dk/bearware/VideoCodec")
MediaFileInfo = JavaClass("dk/bearware/MediaFileInfo")
ClientStatistics = JavaClass("dk/bearware/ClientStatistics")
EncryptionContext = JavaClass("dk/bearware/EncryptionContext")

# Konstanten-Klassen
Codec = JavaClass("dk/bearware/Codec")
ClientError = JavaClass("dk/bearware/ClientError")
TextMsgType = JavaClass("dk/bearware/TextMsgType")
StreamType = JavaClass("dk/bearware/StreamType")
UserState = JavaClass("dk/bearware/UserState")
BanType = JavaClass("dk/bearware/BanType")
UserType = JavaClass("dk/bearware/UserType")
UserRight = JavaClass("dk/bearware/UserRight")
ChannelType = JavaClass("dk/bearware/ChannelType")
Subscription = JavaClass("dk/bearware/Subscription")


# ---------------------------------------------------------------------------
# Datenklasse für Verbindungsergebnisse (identisch mit Desktop-Client)
# ---------------------------------------------------------------------------

@dataclass
class ConnectResult:
    ok: bool
    message: str
    error_code: int = 0


# ---------------------------------------------------------------------------
# Haupt-Wrapper-Klasse
# ---------------------------------------------------------------------------

class TeamTalkClientAndroid:
    """Drop-in-kompatibler Wrapper um das TeamTalk5-Java-SDK.

    Die öffentliche API spiegelt TeamTalkClient (ctypes-Variante) 1:1.
    Intern wird per Rubicon-Java auf dk.bearware.TeamTalk5 zugegriffen.
    """

    def __init__(self) -> None:
        # TeamTalk5-Instanz erstellen (benötigt Android-Context – wird von
        # Briefcase/Toga beim App-Start automatisch gesetzt)
        self._tt = TeamTalk5()
        self._connected = False
        self._event_thread: Optional[threading.Thread] = None
        self._event_stop = threading.Event()
        self._last_connect: Optional[tuple] = None

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------

    def connect_and_login(
        self,
        host: str,
        tcp_port: int,
        udp_port: int,
        nickname: str,
        username: str,
        password: str,
        client_name: str,
        encrypted: bool = False,
        verify_peer: Optional[bool] = None,
        tls_has_custom_material: bool = False,
        remember_last_connect: bool = True,
        timeout_ms: int = 8000,
        on_login_confirmed: Optional[Callable] = None,
    ) -> ConnectResult:
        if remember_last_connect:
            self._last_connect = (
                host, tcp_port, udp_port, nickname, username, password,
                client_name, encrypted, verify_peer, tls_has_custom_material,
            )

        ok = self._tt.connect(host, tcp_port, udp_port, 0, 0, encrypted)
        if not ok:
            return ConnectResult(False, "Verbindung konnte nicht gestartet werden")

        # Auf CON_SUCCESS warten (blockierender Poll im aufrufenden Thread)
        connected = self._wait_for_con_success(timeout_ms)
        if not connected:
            return ConnectResult(False, "Verbindung fehlgeschlagen: Timeout")

        cmdid = self._tt.doLogin(nickname, username, password, client_name)
        if cmdid < 0:
            return ConnectResult(False, "Login fehlgeschlagen: doLogin() zurückgewiesen")

        login_ok, err_msg = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not login_ok:
            self._tt.disconnect()
            return ConnectResult(False, f"Login fehlgeschlagen: {err_msg}")

        if on_login_confirmed:
            on_login_confirmed()

        self._connected = True
        return ConnectResult(True, "Verbunden und eingeloggt")

    def _wait_for_con_success(self, timeout_ms: int) -> bool:
        """Pollend auf CLIENTEVENT_CON_SUCCESS warten."""
        import time
        end = time.time() + timeout_ms / 1000.0
        while time.time() < end:
            msg = self._tt.getMessage(50)
            if msg is None:
                continue
            event = msg.nClientEvent
            if event == ClientEvent.CLIENTEVENT_CON_SUCCESS:
                return True
            if event in (
                ClientEvent.CLIENTEVENT_CON_FAILED,
                ClientEvent.CLIENTEVENT_CON_CRYPT_ERROR,
            ):
                return False
        return False

    def _wait_for_cmd_result(self, cmdid: int, timeout_ms: int) -> Tuple[bool, str]:
        """Warten bis CMD_SUCCESS oder CMD_ERROR für cmdid eintrifft."""
        import time
        end = time.time() + timeout_ms / 1000.0
        while time.time() < end:
            msg = self._tt.getMessage(50)
            if msg is None:
                continue
            event = msg.nClientEvent
            if event == ClientEvent.CLIENTEVENT_CMD_SUCCESS and msg.nSource == cmdid:
                return True, ""
            if event == ClientEvent.CLIENTEVENT_CMD_ERROR and msg.nSource == cmdid:
                try:
                    err_text = msg.clienterrormsg.szErrorMsg or ""
                except Exception:
                    err_text = "Unbekannter Fehler"
                return False, err_text
        return False, "Timeout"

    def reconnect(self, timeout_ms: int = 8000) -> ConnectResult:
        if not self._last_connect:
            return ConnectResult(False, "Keine gespeicherten Verbindungsdaten")
        return self.connect_and_login(*self._last_connect, timeout_ms=timeout_ms)

    def disconnect(self) -> None:
        self._connected = False
        try:
            self._tt.disconnect()
        except Exception:
            pass

    def disconnect_transport(self) -> None:
        self.disconnect()

    def is_connected(self) -> bool:
        return self._connected

    def close(self) -> None:
        self._connected = False
        self.stop_event_loop()
        try:
            self._tt.closeTeamTalk()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Kanäle
    # ------------------------------------------------------------------

    def join_root_channel(self, timeout_ms: int = 2000) -> ConnectResult:
        root_id = self._tt.getRootChannelID()
        return self.join_channel_by_id(root_id, timeout_ms=timeout_ms)

    def join_channel_by_id(self, channel_id: int, password: str = "", timeout_ms: int = 2000) -> ConnectResult:
        cmdid = self._tt.doJoinChannelByID(channel_id, password)
        ok, err = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, f"Kanalbeitritt fehlgeschlagen: {err}")
        return ConnectResult(True, "Kanalbeitritt erfolgreich")

    def join_channel_by_path(self, path: str, password: str = "", timeout_ms: int = 4000) -> ConnectResult:
        chan_id = self.get_channel_id_from_path(path)
        if chan_id and chan_id > 0:
            return self.join_channel_by_id(chan_id, password=password, timeout_ms=timeout_ms)
        return ConnectResult(False, "Kanal nicht gefunden")

    def leave_channel(self, timeout_ms: int = 2000) -> ConnectResult:
        cmdid = self._tt.doLeaveChannel()
        ok, err = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, "Kanal verlassen fehlgeschlagen")
        return ConnectResult(True, "Kanal verlassen")

    def make_channel(
        self,
        name: str,
        parent_id: int,
        topic: str = "",
        password: str = "",
        permanent: bool = False,
        channel_type: Optional[int] = None,
        audio_codec: Optional[Any] = None,
        disk_quota: Optional[int] = None,
        max_users: Optional[int] = None,
        op_password: str = "",
        timeout_ms: int = 4000,
    ) -> ConnectResult:
        ch = Channel()
        ch.nParentID = int(parent_id)
        ch.nChannelID = 0
        ch.szName = name
        ch.szTopic = topic
        if password:
            ch.szPassword = password
            ch.bPassword = True
        if channel_type is None:
            ch.uChannelType = ChannelType.CHANNEL_PERMANENT if permanent else ChannelType.CHANNEL_DEFAULT
        else:
            ch.uChannelType = int(channel_type)
        if disk_quota is not None:
            ch.nDiskQuota = int(disk_quota)
        if max_users is not None:
            ch.nMaxUsers = int(max_users)
        if op_password:
            ch.szOpPassword = op_password
        cmdid = self._tt.doMakeChannel(ch)
        ok, err = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, f"Kanal erstellen fehlgeschlagen: {err}")
        return ConnectResult(True, "Kanal erstellt")

    def make_temporary_channel(
        self,
        name: str,
        parent_id: int,
        topic: str = "",
        password: str = "",
        channel_type: Optional[int] = None,
        audio_codec: Optional[Any] = None,
        timeout_ms: int = 4000,
    ) -> ConnectResult:
        ch = Channel()
        ch.nParentID = int(parent_id)
        ch.nChannelID = 0
        ch.szName = name
        ch.szTopic = topic
        if password:
            ch.szPassword = password
            ch.bPassword = True
        if channel_type is not None:
            ch.uChannelType = int(channel_type)
        cmdid = self._tt.doJoinChannel(ch)
        ok, err = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, f"Kanal erstellen fehlgeschlagen: {err}")
        return ConnectResult(True, "Kanal erstellt (temporär)")

    def update_channel(self, channel: Any, timeout_ms: int = 4000) -> ConnectResult:
        cmdid = self._tt.doUpdateChannel(channel)
        ok, err = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, f"Kanal aktualisieren fehlgeschlagen: {err}")
        return ConnectResult(True, "Kanal aktualisiert")

    def remove_channel(self, channel_id: int, timeout_ms: int = 4000) -> ConnectResult:
        cmdid = self._tt.doRemoveChannel(int(channel_id))
        ok, err = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, f"Kanal löschen fehlgeschlagen: {err}")
        return ConnectResult(True, "Kanal gelöscht")

    # ------------------------------------------------------------------
    # Kanal-/Benutzer-Abfragen
    # ------------------------------------------------------------------

    def get_server_channels(self) -> List[Any]:
        return list(self._tt.getServerChannels() or [])

    def get_server_users(self) -> List[Any]:
        return list(self._tt.getServerUsers() or [])

    def get_channel_users(self, channel_id: int) -> List[Any]:
        return list(self._tt.getChannelUsers(channel_id) or [])

    def get_channel(self, channel_id: int) -> Any:
        return self._tt.getChannel(channel_id)

    def get_channel_path(self, channel_id: int) -> str:
        return self._tt.getChannelPath(channel_id) or ""

    def get_root_channel_id(self) -> int:
        return self._tt.getRootChannelID()

    def get_channel_id_from_path(self, path: str) -> int:
        return self._tt.getChannelIDFromPath(path)

    def get_my_channel_id(self) -> int:
        return self._tt.getMyChannelID()

    def get_my_user_id(self) -> int:
        return self._tt.getMyUserID()

    def get_my_user_type(self) -> int:
        return self._tt.getMyUserType()

    def get_my_user_rights(self) -> int:
        return int(self._tt.getMyUserRights())

    def get_user(self, user_id: int) -> Any:
        return self._tt.getUser(user_id)

    def get_user_by_username(self, username: str) -> Any:
        return self._tt.getUserByUsername(username)

    def get_server_properties(self) -> Any:
        return self._tt.getServerProperties()

    # ------------------------------------------------------------------
    # Authentifizierung & Status
    # ------------------------------------------------------------------

    def logout(self, timeout_ms: int = 2000) -> ConnectResult:
        cmdid = self._tt.doLogout()
        ok, _ = self._wait_for_cmd_result(cmdid, timeout_ms)
        if not ok:
            return ConnectResult(False, "Abmelden fehlgeschlagen")
        self._connected = False
        return ConnectResult(True, "Abmelden erfolgreich")

    def change_nickname(self, nickname: str) -> int:
        return self._tt.doChangeNickname(nickname)

    def change_status(self, mode: int, message: str) -> int:
        return self._tt.doChangeStatus(int(mode), message)

    # ------------------------------------------------------------------
    # Nachrichten
    # ------------------------------------------------------------------

    def send_channel_message(self, channel_id: int, message: str) -> bool:
        msg = TextMessage()
        msg.nMsgType = TextMsgType.MSGTYPE_CHANNEL
        msg.nChannelID = channel_id
        msg.szMessage = message
        return self._tt.doTextMessage(msg) >= 0

    def send_user_message(self, user_id: int, message: str) -> bool:
        msg = TextMessage()
        msg.nMsgType = TextMsgType.MSGTYPE_USER
        msg.nToUserID = user_id
        msg.szMessage = message
        return self._tt.doTextMessage(msg) >= 0

    def send_broadcast_message(self, message: str) -> bool:
        msg = TextMessage()
        msg.nMsgType = TextMsgType.MSGTYPE_BROADCAST
        msg.szMessage = message
        return self._tt.doTextMessage(msg) >= 0

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def get_sound_devices(self) -> List[Any]:
        return list(self._tt.getSoundDevices() or [])

    def get_default_sound_devices(self) -> Any:
        return self._tt.getDefaultSoundDevices()

    def init_sound_input_device(self, device_id: int) -> bool:
        return self._tt.initSoundInputDevice(device_id)

    def init_sound_output_device(self, device_id: int) -> bool:
        return self._tt.initSoundOutputDevice(device_id)

    def close_sound_input_device(self) -> bool:
        return self._tt.closeSoundInputDevice()

    def close_sound_output_device(self) -> bool:
        return self._tt.closeSoundOutputDevice()

    def enable_voice_transmission(self, enable: bool) -> bool:
        return self._tt.enableVoiceTransmission(enable)

    def enable_voice_activation(self, enable: bool) -> bool:
        return self._tt.enableVoiceActivation(enable)

    def set_voice_activation_level(self, level: int) -> bool:
        return self._tt.setVoiceActivationLevel(level)

    def set_sound_input_gain(self, level: int) -> bool:
        return self._tt.setSoundInputGainLevel(level)

    def set_sound_output_volume(self, level: int) -> bool:
        return self._tt.setSoundOutputVolume(level)

    def set_sound_output_mute(self, enabled: bool) -> bool:
        return self._tt.setSoundOutputMute(bool(enabled))

    def get_sound_input_level(self) -> int:
        return self._tt.getSoundInputLevel()

    def restart_sound_system(self) -> bool:
        try:
            return self._tt.restartSoundSystem()
        except Exception:
            return False

    def set_user_volume(self, user_id: int, stream_type: int, volume: int) -> bool:
        return self._tt.setUserVolume(user_id, stream_type, volume)

    def set_user_mute(self, user_id: int, stream_type: int, mute: bool) -> bool:
        return self._tt.setUserMute(user_id, stream_type, mute)

    def set_user_position(self, user_id: int, stream_type: int, x: float, y: float, z: float) -> bool:
        return self._tt.setUserPosition(int(user_id), int(stream_type), float(x), float(y), float(z))

    # ------------------------------------------------------------------
    # Medien-Streaming (auf Android eingeschränkt verfügbar)
    # ------------------------------------------------------------------

    def get_media_file_info(self, filepath: str) -> Any:
        info = MediaFileInfo()
        ok = self._tt.getMediaFileInfo(filepath, info)
        return info if ok else None

    def start_streaming_media_to_channel(self, filepath: str, offset_ms: int = 0, preamp_gain: float = 1.0) -> bool:
        # Auf Android ist MediaFile-Streaming über das Java-SDK möglich,
        # aber Codec-Konfiguration weicht von der ctypes-API ab.
        try:
            return self._tt.startStreamingMediaFileToChannel(filepath, None)
        except Exception:
            return False

    def stop_streaming_media(self) -> bool:
        try:
            return self._tt.stopStreamingMediaFileToChannel()
        except Exception:
            return False

    def update_streaming_media(self, paused: bool = False, offset_ms: Optional[int] = 0, preamp_gain: float = 1.0) -> bool:
        try:
            return self._tt.updateStreamingMediaFileToChannel(paused, offset_ms or 0)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Dateiübertragung
    # ------------------------------------------------------------------

    def get_channel_files(self, channel_id: int) -> List[Any]:
        return list(self._tt.getChannelFiles(channel_id) or [])

    def send_file(self, channel_id: int, local_path: str) -> int:
        return self._tt.doSendFile(channel_id, local_path)

    def recv_file(self, channel_id: int, file_id: int, local_path: str) -> int:
        return self._tt.doRecvFile(channel_id, file_id, local_path)

    def delete_file(self, channel_id: int, file_id: int) -> int:
        return self._tt.doDeleteFile(channel_id, file_id)

    def get_file_transfer_info(self, transfer_id: int) -> Any:
        ft = FileTransfer()
        ok = self._tt.getFileTransferInfo(transfer_id, ft)
        return ft if ok else None

    def cancel_file_transfer(self, transfer_id: int) -> bool:
        return self._tt.cancelFileTransfer(transfer_id)

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def do_subscribe(self, user_id: int, subscriptions: int) -> int:
        return self._tt.doSubscribe(user_id, subscriptions)

    def do_unsubscribe(self, user_id: int, subscriptions: int) -> int:
        return self._tt.doUnsubscribe(user_id, subscriptions)

    # ------------------------------------------------------------------
    # Kanal-Operator / Kick / Ban
    # ------------------------------------------------------------------

    def do_channel_op(self, channel_id: int, user_id: int, make_op: bool) -> int:
        return self._tt.doChannelOp(user_id, channel_id, make_op)

    def is_channel_operator(self, channel_id: int, user_id: int) -> bool:
        return self._tt.isChannelOperator(channel_id, user_id)

    def do_kick_user(self, user_id: int, channel_id: int) -> int:
        return self._tt.doKickUser(user_id, channel_id)

    def do_channel_user_transmit(self, user_id: int, channel_id: int, stream_types: int) -> int:
        return self._tt.doChannelUserTransmit(int(user_id), int(channel_id), int(stream_types))

    def do_ban_user_ex(self, user_id: int, ban_types: int) -> int:
        return self._tt.doBanUserEx(user_id, int(ban_types))

    def do_ban_ip_address(self, ip_address: str, channel_id: int = 0) -> int:
        return self._tt.doBanIPAddress(ip_address, channel_id)

    def do_move_user(self, user_id: int, channel_id: int) -> int:
        return self._tt.doMoveUser(int(user_id), int(channel_id))

    # ------------------------------------------------------------------
    # Administration
    # ------------------------------------------------------------------

    def do_list_user_accounts(self, offset: int = 0, count: int = 100) -> int:
        return self._tt.doListUserAccounts(offset, count)

    def do_new_user_account(self, username: str, password: str, user_type: int, user_rights: int = 0, note: str = "") -> int:
        account = UserAccount()
        account.szUsername = username
        account.szPassword = password
        account.uUserType = user_type
        account.uUserRights = user_rights
        account.szNote = note
        return self._tt.doNewUserAccount(account)

    def do_delete_user_account(self, username: str) -> int:
        return self._tt.doDeleteUserAccount(username)

    def do_ban_user(self, channel_id: int, user_id: int) -> int:
        return self._tt.doBanUser(user_id, channel_id)

    def do_unban_user(self, ip_addr: str, ban_type: int = 0) -> int:
        return self._tt.doUnBanUser(ip_addr, ban_type)

    def do_list_bans(self, channel_id: int = 0, offset: int = 0, count: int = 100) -> int:
        return self._tt.doListBans(channel_id, offset, count)

    def do_update_server(self, server_name: str = "", motd: str = "", max_users: int = 0) -> int:
        props = self._tt.getServerProperties()
        if server_name:
            props.szServerName = server_name
        if motd:
            props.szMOTDRaw = motd
        if max_users > 0:
            props.nMaxUsers = max_users
        return self._tt.doUpdateServer(props)

    def do_save_config(self) -> int:
        return self._tt.doSaveConfig()

    def do_query_server_stats(self) -> int:
        return self._tt.doQueryServerStats()

    def get_client_statistics(self) -> Any:
        stats = ClientStatistics()
        ok = self._tt.getClientStatistics(stats)
        return stats if ok else None

    def get_error_message(self, error_no: int) -> str:
        return self._tt.getErrorMessage(error_no) or ""

    def set_user_media_storage_dir(self, user_id: int, folder_path: str, filename_vars: str, audio_format: int) -> bool:
        return self._tt.setUserMediaStorageDir(int(user_id), folder_path, filename_vars, audio_format)

    # ------------------------------------------------------------------
    # Event-Loop
    # ------------------------------------------------------------------

    def start_event_loop(self, handler: Callable[[str], None], poll_ms: int = 200) -> None:
        """Startet einen Hintergrund-Thread, der SDK-Events in EventBus-Namen übersetzt."""
        if self._event_thread and self._event_thread.is_alive():
            return
        self._event_stop.clear()

        def loop():
            while not self._event_stop.is_set():
                msg = self._tt.getMessage(min(poll_ms, 100))
                if msg is None:
                    continue
                event = msg.nClientEvent
                if event == ClientEvent.CLIENTEVENT_NONE:
                    continue
                event_name = self._event_to_name(event)
                handler(event_name, msg=msg)

        self._event_thread = threading.Thread(target=loop, daemon=True)
        self._event_thread.start()

    def stop_event_loop(self) -> None:
        self._event_stop.set()

    def stop_event_loop_and_wait(self, timeout: float = 0.4) -> None:
        self._event_stop.set()
        if self._event_thread and self._event_thread.is_alive():
            self._event_thread.join(timeout)
        self._event_thread = None

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _event_to_name(event_int: int) -> str:
        """Wandelt numerischen SDK-Event in lesbaren Event-Bus-Namen um."""
        _map = {
            # Verbindung
            200: "con_success",
            201: "con_failed",
            202: "con_lost",
            203: "con_crypt_error",
            # Befehle
            300: "cmd_success",
            301: "cmd_error",
            302: "cmd_processing",
            # Server
            400: "cmd_server_update",
            # Benutzer
            500: "cmd_user_loggedin",
            501: "cmd_user_loggedout",
            502: "cmd_user_update",
            503: "cmd_user_joined",
            504: "cmd_user_left",
            505: "cmd_user_textmessage",
            506: "cmd_myself_loggedin",
            507: "cmd_myself_kicked",
            # Kanäle
            600: "cmd_channel_new",
            601: "cmd_channel_update",
            602: "cmd_channel_remove",
            # Dateiübertragung
            700: "file_transfer",
            # Stream
            800: "user_statechange",
            801: "user_videoframe",
            802: "user_mediafile_video",
            803: "user_desktopwindow",
            804: "user_desktopcursor",
            805: "user_desktopinput",
            # Audio
            900: "hotkey",
            901: "hotkey_test",
            # Statistik
            1000: "clientevent_stats",
        }
        return _map.get(event_int, f"event_{event_int}")
