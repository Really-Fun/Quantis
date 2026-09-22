#!/usr/bin/env python3
"""Сборка Quantis.exe с выбранным медиадвижком.

Примеры:
    python packaging/scripts/build_exe.py qt
    python packaging/scripts/build_exe.py vlc
    python packaging/scripts/build_exe.py vlc --vlc-home "C:\\Program Files\\VideoLAN\\VLC"
    python packaging/scripts/build_exe.py qt --mpris
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packaging" / "pyinstaller" / "main.spec"


def _leaked_user_data(root: Path) -> list[str]:
    """Имена файлов, которые нельзя отдавать вместе с exe."""
    sys.path.insert(0, str(ROOT / "packaging" / "pyinstaller"))
    from collect_datas import USER_DATA_DIR_NAMES, USER_DATA_FILE_NAMES

    leaked: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in USER_DATA_DIR_NAMES for part in rel.parts):
            leaked.append(rel.as_posix())
        elif path.name in USER_DATA_FILE_NAMES:
            leaked.append(rel.as_posix())
    return leaked


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка Quantis (qt | vlc)")
    parser.add_argument(
        "backend",
        choices=("qt", "vlc"),
        help="Медиадвижок: qt = Qt Multimedia, vlc = python-vlc/libVLC",
    )
    parser.add_argument(
        "--vlc-home",
        default=os.environ.get("VLC_HOME", ""),
        help="Каталог установки VLC (для bundling libvlc.dll + plugins)",
    )
    parser.add_argument(
        "--noconfirm",
        action="store_true",
        default=True,
        help="Перезаписать dist без вопросов (по умолчанию)",
    )
    parser.add_argument(
        "--mpris",
        action="store_true",
        help="Linux: положить mpris_server в бандл (по умолчанию он вырезан)",
    )
    args = parser.parse_args()

    env = os.environ.copy()
    env["QUANTIS_MEDIA_BACKEND"] = args.backend
    if args.backend == "vlc" and args.vlc_home:
        env["VLC_HOME"] = args.vlc_home
    if args.mpris:
        env["QUANTIS_BUNDLE_MPRIS"] = "1"

    work = f"pyi-{args.backend}"
    if args.mpris:
        work += "-mpris"

    name = "Quantis" if args.backend == "qt" else "Quantis-VLC"
    # When PyInstaller lives at <repo>/PyInstaller, HOMEPATH is the repo root.
    # PyInstaller then rewrites --distpath <repo>/dist -> <repo>/<spec>/dist
    # (building/build_main.py). Nest under dist/_bundle so dirname != HOMEPATH.
    dist_bundle = ROOT / "dist" / "_bundle"
    final_dir = ROOT / "dist" / name

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--distpath",
        str(dist_bundle),
        "--workpath",
        str(ROOT / "build" / work),
    ]

    print(f"==> Building Quantis backend={args.backend}")
    if args.backend == "vlc":
        print(f"    VLC_HOME={env.get('VLC_HOME') or '(auto)'}")
    if args.mpris:
        print("    MPRIS=bundled")
    print("   ", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        return result.returncode

    built = dist_bundle / name
    if not built.is_dir():
        # HOMEPATH rewrite fallback (spec-relative dist/...)
        alt = ROOT / "packaging" / "pyinstaller" / "dist" / name
        if alt.is_dir():
            built = alt
        else:
            legacy_alt = ROOT / "main" / "dist" / name
            if legacy_alt.is_dir():
                built = legacy_alt
            else:
                print(
                    f"ERROR: expected onedir missing: {dist_bundle / name}",
                    file=sys.stderr,
                )
                return 1

    if final_dir.exists():
        shutil.rmtree(final_dir)
    shutil.move(str(built), str(final_dir))
    try:
        dist_bundle.rmdir()
    except OSError:
        pass
    leaked = _leaked_user_data(final_dir)
    if leaked:
        print("ERROR: в бандл попали пользовательские данные:", file=sys.stderr)
        for rel in leaked:
            print(f"    {rel}", file=sys.stderr)
        return 1
    for leftover, prune_parent in (
        (ROOT / "main" / "dist", True),
        (ROOT / "packaging" / "pyinstaller" / "dist", False),
    ):
        if leftover.is_dir() and not any(leftover.iterdir()):
            leftover.rmdir()
            if prune_parent:
                try:
                    leftover.parent.rmdir()
                except OSError:
                    pass

    print(f"==> OK: dist/{name}/{name}.exe")
    if args.mpris:
        print("    bundled mpris_server")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
