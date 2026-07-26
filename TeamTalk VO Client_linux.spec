# -*- mode: python ; coding: utf-8 -*-
# Linux-Build-Spec (x64)
# TeamTalk SDK: third_party/teamtalk/tt5sdk_v5.19a_linux_x64/
# Download: https://bearware.dk/teamtalksdk


a = Analysis(
    ['src/app.py'],
    pathex=['src', 'third_party/teamtalk/tt5sdk_v5.19a_linux_x64/Library/TeamTalkPy'],
    binaries=[],
    datas=[
        ('src/teamtalk_client', 'teamtalk_client'),
        ('src/platform_paths.py', '.'),
        ('src/ui', 'ui'),
        ('src/ui_qt', 'ui_qt'),
        ('src/chat_history.py', '.'),
        ('src/global_hotkeys.py', '.'),
        ('src/screen_capture.py', '.'),
        ('src/system_audio.py', '.'),
        ('src/screen_reader.py', '.'),
        ('licenses', 'licenses'),
        ('CHANGELOG.txt', '.'),
        ('INSTALL_macOS.md', '.'),
        ('src/manual.html', '.'),
        ('third_party/teamtalk/tt5sdk_v5.19a_linux_x64/Library/TeamTalkPy', 'TeamTalkPy'),
        ('third_party/teamtalk/tt5sdk_v5.19a_linux_x64/Library/TeamTalk_DLL', 'TeamTalk_DLL'),
        ('third_party/yt-dlp', 'yt-dlp'),
        ('third_party/librespot', 'librespot'),
        ('third_party/espeak-ng', 'espeak-ng'),
        ('third_party/sral/linux/libSRAL.so', 'sral/linux'),
        ('third_party/sral/sral.py', 'sral'),
        ('src/sounds', 'sounds'),
    ],
    hiddenimports=[
        'app_qt', 'screen_reader', 'sr_output',
        'teamtalk_client', 'teamtalk_client.tt', 'teamtalk_client.client',
        'ui.tabs.system', 'ui_qt.tabs.system', 'platform_paths', 'sound_manager',
        'chat_history', 'global_hotkeys', 'pyaudio', 'i18n',
        'mss', 'mss.tools', 'screen_capture', 'system_audio',
        'PySide6', 'PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['whisper', 'torch', 'numba', 'numba.core', 'llvmlite',
              'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public',
              'objc', 'AppKit', 'Quartz', 'win32gui', 'win32con',
              'wx', 'wx.adv', 'wx.dataview'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TeamTalk VO Client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TeamTalk VO Client',
)
