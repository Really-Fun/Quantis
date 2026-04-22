# -*- mode: python ; coding: utf-8 -*-
import os
import ytmusicapi

ytm_path = os.path.dirname(ytmusicapi.__file__)
ytm_ru_locale = (os.path.join(ytm_path, 'locales', 'ru'), 'ytmusicapi/locales/ru')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # 1. ДОБАВЛЯЕМ ИКОНКУ В datas (чтобы она запаковалась внутрь exe)
    datas=[
        ytm_ru_locale,
        ('assets/icons/exe_logo.png', '.')
    ], 
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Quantis',
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
    icon='assets/icons/exe_logo.png', 
)