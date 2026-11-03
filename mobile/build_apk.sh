#!/usr/bin/env bash
# Сборка APK беты Quantis Mobile (Linux).
#
# Нужно: JDK 17, колёса PySide6/shiboken6 для Android в $CACHE/wheels,
# окружение с pyside6-android-deploy в $CACHE/tool-venv (см. README.md).
# NDK r28c инструмент скачает сам в $CACHE, SDK докачает buildozer.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CACHE="${PYSIDE_ANDROID_CACHE:-$HOME/.pyside6_android_deploy}"
ARCH="${ARCH:-aarch64}"
PYSIDE_WHEEL="$CACHE/wheels/pyside6-6.12.0-6.12.0-cp310-abi3-android_${ARCH}.whl"
SHIBOKEN_WHEEL="$CACHE/wheels/shiboken6-6.12.0-6.12.0-cp310-abi3-android_${ARCH}.whl"

# yt-dlp — чистый Python: кладём исходники рядом с main.py,
# python-for-android упакует их вместе с приложением.
SITE="$("$ROOT/.venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
rm -rf "${HERE:?}/yt_dlp" "${HERE:?}/certifi"
cp -r "$SITE/yt_dlp" "$HERE/yt_dlp"
find "$HERE/yt_dlp" -name __pycache__ -type d -prune -exec rm -rf {} +

# Сертификаты — модулем .py: buildozer не упаковывает .pem, а пакет certifi
# без своего cacert.pem ломал бы yt-dlp (он грузит certifi.where()).
"$ROOT/.venv/bin/python" - "$HERE/ca_bundle.py" <<'PY'
import sys, certifi
pem = open(certifi.where(), encoding="ascii").read()
with open(sys.argv[1], "w", encoding="utf-8") as out:
    out.write('"""Сертификаты certifi, создано build_apk.sh."""\n\n')
    out.write(f"PEM = {pem!r}\n")
PY

# Как активированное окружение: buildozer ищет cython в PATH, а без
# VIRTUAL_ENV ставит зависимости p4a через pip --user, что venv запрещает.
export VIRTUAL_ENV="$CACHE/tool-venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"

cd "$HERE"
pyside6-android-deploy \
    --name QuantisMobile \
    --wheel-pyside "$PYSIDE_WHEEL" \
    --wheel-shiboken "$SHIBOKEN_WHEEL" \
    --sdk-path "$CACHE/android-sdk" \
    --extra-modules Multimedia \
    --force "$@"
