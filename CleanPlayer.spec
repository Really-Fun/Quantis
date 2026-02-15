# -*- mode: python ; coding: utf-8 -*-
# Сборка CleanPlayer для Windows (onedir: папка с exe, лёгкий exe).

import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

ytmusic_datas, ytmusic_binaries, ytmusic_hidden = collect_all('ytmusicapi')
certifi_datas = collect_data_files("certifi")

app_datas = [
    ('user_theme.xml', '.'),
    ('assets', 'assets'),
]

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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CleanPlayer',
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
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CleanPlayer',
)
