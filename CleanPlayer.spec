# -*- mode: python ; coding: utf-8 -*-
# Сборка CleanPlayer для Windows.
# Локали ytmusicapi (в т.ч. RU) подхватываются через collect_all.

import os
from PyInstaller.utils.hooks import collect_all

# Подтянуть все данные ytmusicapi (локали, в т.ч. ru)
ytmusic_datas, ytmusic_binaries, ytmusic_hidden = collect_all('ytmusicapi')

# Файлы приложения: тема, assets
app_datas = [
    ('user_theme.xml', '.'),
    ('assets', 'assets'),
]

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ytmusic_binaries,
    datas=ytmusic_datas + app_datas,
    hiddenimports=[
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
    console=False,  # GUI — без консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
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
