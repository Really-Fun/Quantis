#!/usr/bin/env python3
"""Сборка Inno Setup установщика. Версия — из pyproject.toml."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка установщика Quantis")
    parser.add_argument(
        "--backend",
        choices=("qt", "vlc"),
        default="qt",
        help="Тот же backend, что у packaging/scripts/build_exe.py",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "src"))
    from quantis.version import project_version

    version = project_version()
    if not version:
        print("Не удалось прочитать version из pyproject.toml", file=sys.stderr)
        return 1

    iscc = shutil.which("iscc") or shutil.which("ISCC")
    if iscc is None:
        print(
            "Inno Setup (iscc) не найден в PATH.\n"
            f"Вручную: iscc /DAppVersion={version} /DBackend={args.backend} "
            "packaging\\inno\\quantis.iss",
            file=sys.stderr,
        )
        return 1

    iss = ROOT / "packaging" / "inno" / "quantis.iss"
    cmd = [
        iscc,
        f"/DAppVersion={version}",
        f"/DBackend={args.backend}",
        str(iss),
    ]
    print("==> ", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
