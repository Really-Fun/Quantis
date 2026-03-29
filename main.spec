# -*- mode: python ; coding: utf-8 -*-
import os
import ytmusicapi

# Вычисляем абсолютный путь к пакету ytmusicapi
ytm_path = os.path.dirname(ytmusicapi.__file__)

ytm_ru_locale = (os.path.join(ytm_path, 'locales', 'ru'), 'ytmusicapi/locales/ru')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[ytm_ru_locale], # <-- Передаем локали в сборку
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,        # <-- ДОБАВЛЕНО СЮДА
    a.datas,           # <-- ДОБАВЛЕНО СЮДА
    [],
    name='CleanPlayer', # <-- Поменял название экзешника
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None, # <-- ВАЖНЫЙ ПАРАМЕТР ДЛЯ ONEFILE
    console=False,       # Консоль отключена
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)