# -*- mode: python ; coding: utf-8 -*-
# Сборка CleanPlayer для Windows (onefile, как в рабочей команде с ytmusicapi).

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Локали ytmusicapi (в т.ч. ru) — collect_all + явно ru как в старой рабочей сборке
ytmusic_datas, ytmusic_binaries, ytmusic_hidden = collect_all('ytmusicapi')
certifi_datas = collect_data_files("certifi")

app_datas = [
    ('user_theme.xml', '.'),
    ('assets', 'assets'),
]

# Иконка (создай assets/icons/icon.ico при необходимости)
icon_path = 'assets/icons/icon.ico' if os.path.isfile('assets/icons/icon.ico') else None

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ytmusic_binaries,
    datas=ytmusic_datas + certifi_datas + app_datas,
    hiddenimports=[
        'certifi',
        'ytmusicapi',
        'qasync',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ] + ytmusic_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Onefile: один exe, всё внутри (как в твоей рабочей команде)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CleanPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
