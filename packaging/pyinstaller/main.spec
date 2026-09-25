# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: Quantis с выбором медиадвижка.

Сборка Qt (по умолчанию):
    poetry run python packaging/scripts/build_exe.py qt

Сборка VLC:
    poetry install --with dev,vlc
    set VLC_HOME=C:\\Program Files\\VideoLAN\\VLC
    poetry run python packaging/scripts/build_exe.py vlc

Linux с MPRIS (кладёт mpris_server в бандл, Windows-сборка его вырезает):
    poetry run python packaging/scripts/build_exe.py qt --mpris

Или напрямую:
    set QUANTIS_MEDIA_BACKEND=qt
    poetry run pyinstaller packaging/pyinstaller/main.spec --noconfirm
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

try:
    from PyInstaller.utils.hooks import copy_metadata
except ImportError:
    copy_metadata = None

try:
    SPEC_DIR = Path(SPECPATH).resolve()
except NameError:
    SPEC_DIR = Path.cwd() / "packaging" / "pyinstaller"

# spec живёт в packaging/pyinstaller/ — корень репозитория на два уровня выше
ROOT = SPEC_DIR.parents[1]
SRC = ROOT / "src"
QUANTIS = SRC / "quantis"
HOOKS = SPEC_DIR / "hooks"

BACKEND = os.environ.get("QUANTIS_MEDIA_BACKEND", "qt").strip().lower()
if BACKEND not in ("qt", "vlc"):
    BACKEND = "qt"

BUNDLE_MPRIS = os.environ.get("QUANTIS_BUNDLE_MPRIS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

APP_NAME = "Quantis" if BACKEND == "qt" else "Quantis-VLC"

_venv = Path(os.environ.get("VIRTUAL_ENV") or (ROOT / ".venv"))
if sys.platform == "win32":
    SITE = _venv / "Lib" / "site-packages"
else:
    SITE = (
        _venv
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )

datas: list = []
binaries: list = []
hiddenimports: list[str] = []
runtime_hooks: list[str] = []

# Версия из pyproject.toml — в бандл, чтобы exe не зависел от stale dist-info.
# VERSIONINFO (Windows Properties → Details) пишется в packaging/pyinstaller/.
_app_version = ""
_version_file = None
try:
    import tomllib

    _app_version = str(
        tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        .get("project", {})
        .get("version")
        or ""
    ).strip()
except Exception:
    _app_version = ""

try:
    import importlib.util

    _vi_path = SPEC_DIR / "version_info.py"
    _vi_spec = importlib.util.spec_from_file_location(
        "quantis_packaging_version_info", _vi_path
    )
    if _vi_spec is None or _vi_spec.loader is None:
        raise ImportError(f"cannot load {_vi_path}")
    _vi_mod = importlib.util.module_from_spec(_vi_spec)
    _vi_spec.loader.exec_module(_vi_mod)
    _version_file = _vi_mod.write_version_info(
        ROOT,
        product_name=APP_NAME,
        original_filename=f"{APP_NAME}.exe",
    )
except Exception as _ver_exc:
    print(f"[Quantis] WARNING: VERSIONINFO not generated: {_ver_exc}")
    _version_file = None

if _app_version:
    # Runtime ищет quantis/version.txt рядом с version.py. datas сохраняет
    # имя исходного файла — нельзя писать quantis_version.txt, иначе exe
    # не найдёт штамп и подхватит stale dist-info (например 0.3.0).
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from quantis.version import VERSION_STAMP_NAME

    _stamp_dir = ROOT / "build"
    _stamp_dir.mkdir(parents=True, exist_ok=True)
    _stamp = _stamp_dir / VERSION_STAMP_NAME
    _stamp.write_text(_app_version + "\n", encoding="utf-8")
    datas.append((str(_stamp), "quantis"))
    print(f"[Quantis] version {_app_version} stamp={_stamp.name}")
if _version_file is not None:
    print(f"[Quantis] VERSIONINFO {_version_file}")

rthook = HOOKS / f"rthook_backend_{BACKEND}.py"
if rthook.is_file():
    runtime_hooks.append(str(rthook))

if BACKEND == "vlc":
    vlc_hook = HOOKS / "rthook_vlc_path.py"
    if vlc_hook.is_file():
        runtime_hooks.append(str(vlc_hook))

# Ресурсы приложения. Не копируем каталог целиком: в styles/ случайно
# оказывались credentials/, player_history.db, covers/ — и уезжали в exe.
_collect_path = SPEC_DIR / "collect_datas.py"
_collect_spec = importlib.util.spec_from_file_location(
    "quantis_packaging_collect_datas", _collect_path
)
if _collect_spec is None or _collect_spec.loader is None:
    raise ImportError(f"cannot load {_collect_path}")
_collect_mod = importlib.util.module_from_spec(_collect_spec)
_collect_spec.loader.exec_module(_collect_mod)
if (QUANTIS / "assets").is_dir():
    datas += _collect_mod.collect_assets(QUANTIS / "assets")
if (QUANTIS / "styles").is_dir():
    datas += _collect_mod.collect_styles(QUANTIS / "styles")

if copy_metadata is not None:
    try:
        datas += copy_metadata("quantis")
    except Exception:
        pass

if (SITE / "ytmusicapi").is_dir():
    try:
        datas += collect_data_files("ytmusicapi", includes=["locales/**"])
    except Exception:
        pass

for pkg in ("PySide6", "shiboken6", "yt_dlp", "certifi"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

if sys.platform == "win32":
    for pkg in (
        "winrt",
        "winrt.windows.foundation",
        "winrt.windows.media",
        "winrt.windows.media.playback",
    ):
        try:
            hiddenimports += collect_submodules(pkg)
        except Exception:
            hiddenimports.append(pkg)

# Темы находятся по файлам пакета (pkgutil) — статически их никто не импортирует.
hiddenimports += collect_submodules("quantis.ui.themes")

hiddenimports += [
    "qasync",
    "aiosqlite",
    "aiohttp",
    "aiofiles",
    "keyring",
    "keyring.backends",
    "keyring.backends.Windows",
    "yandex_music",
    "ytmusicapi",
    "quantis",
    "quantis.main",
    "quantis.adapter",
    "quantis.adapter.clean_adapter",
    "quantis.adapter.windows_adapter",
    "quantis.player.factory",
    "quantis.config.media_backend",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
]

excludes = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "IPython",
    "notebook",
    "pytest",
]

if BUNDLE_MPRIS:
    print("[Quantis] bundling MPRIS (mpris_server)")
    hiddenimports += [
        "quantis.adapter.mpris_adapter",
        "mpris_server",
        "mpris_server.server",
        "mpris_server.adapters",
        "mpris_server.events",
        "mpris_server.base",
        "mpris_server.mpris",
        "mpris_server.mpris.metadata",
        "pydbus",
        "pydbus.generic",
        "gi",
        "gi.repository.GLib",
        "gi.repository.Gio",
        "gi.repository.GObject",
    ]
    for pkg in ("mpris_server", "pydbus"):
        try:
            pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
            datas += pkg_datas
            binaries += pkg_binaries
            hiddenimports += pkg_hidden
        except Exception:
            pass
else:
    excludes.append("mpris_server")

if BACKEND == "vlc":
    hiddenimports += ["vlc", "quantis.player.vlc_engine"]
    vlc_home = Path(
        os.environ.get("VLC_HOME")
        or os.environ.get("ProgramFiles", r"C:\Program Files")
    )
    if vlc_home.name != "VLC":
        candidate = vlc_home / "VideoLAN" / "VLC"
        if candidate.is_dir():
            vlc_home = candidate
    if not (vlc_home / "libvlc.dll").is_file():
        alt = Path(r"C:\Program Files\VideoLAN\VLC")
        if (alt / "libvlc.dll").is_file():
            vlc_home = alt
    if (vlc_home / "libvlc.dll").is_file():
        print(f"[Quantis] Bundling VLC from: {vlc_home}")
        for dll_name in ("libvlc.dll", "libvlccore.dll"):
            dll = vlc_home / dll_name
            if dll.is_file():
                binaries.append((str(dll), "."))
        plugins = vlc_home / "plugins"
        if plugins.is_dir():
            datas.append((str(plugins), "plugins"))
    else:
        print(
            "[Quantis] WARNING: VLC_HOME / libvlc.dll not found. "
            "Install VLC or set VLC_HOME — runtime will need system VLC."
        )
else:
    excludes.append("vlc")

icon = None
for icon_name in ("logo.ico", "logo.png"):
    icon_path = QUANTIS / "assets" / "icons" / icon_name
    if icon_path.is_file():
        icon = str(icon_path)
        break

a = Analysis(
    [str(QUANTIS / "main.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    # Windows VERSIONINFO (Properties → Details). PyInstaller API name is
    # ``version=`` (path to VSVersionInfo text), not version_file=.
    version=str(_version_file) if _version_file is not None else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
