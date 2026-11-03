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
QT_MODULES="Multimedia,Qml,Quick,QuickControls2,Svg"
CLEAN=0
ARGS=()
for arg in "$@"; do
    if [[ "$arg" == --clean ]]; then CLEAN=1; else ARGS+=("$arg"); fi
done
ORIG_PYSIDE_WHEEL="$CACHE/wheels/pyside6-6.12.0-6.12.0-cp310-abi3-android_${ARCH}.whl"
PYSIDE_WHEEL="$CACHE/wheels/patched/$(basename "$ORIG_PYSIDE_WHEEL")"
SHIBOKEN_WHEEL="$CACHE/wheels/shiboken6-6.12.0-6.12.0-cp310-abi3-android_${ARCH}.whl"

# Зависимости — чистый Python: кладём исходники рядом с main.py,
# python-for-android упакует их вместе с приложением. charset_normalizer
# не берём: он скомпилирован под компьютер, а requests работает и без него.
SITE="$("$ROOT/.venv/bin/python" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
VENDORED=(yt_dlp yandex_music requests urllib3 idna typing_extensions.py socks.py)
for item in "${VENDORED[@]}"; do
    rm -rf "${HERE:?}/$item"
    cp -r "$SITE/$item" "$HERE/$item"
done
find "$HERE" -name __pycache__ -type d -prune -exec rm -rf {} +
if find "$HERE" -name '*.so' | grep -q .; then
    echo "В зависимостях есть скомпилированные модули — на телефоне не загрузятся" >&2
    find "$HERE" -name '*.so' >&2
    exit 1
fi

# Сертификаты — модулем .py: buildozer не упаковывает .pem. Рядом лежит
# свой certifi.py: yt-dlp грузит сертификаты по его where().
"$ROOT/.venv/bin/python" -I - "$HERE/ca_bundle.py" <<'PY'
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

# Колесо PySide6 — весь Qt (~250 МБ), а приложению нужна малая часть:
# slim_wheel.py оставляет нужные модули, QML, плагины и библиотеки (по
# DT_NEEDED), убирает FFmpeg (играет системный MediaPlayer) и лишние
# разрешения. Заодно это лечит загрузчик: в колесе 6.12.0 файл зависимостей
# QtMultimedia называет библиотеки FFmpeg libavcodec_<abi>.so, а лежат они
# как libavcodec.so («libswresample_arm64-v8a.so not found» на старте).
READELF="$(find "$CACHE/android-ndk" -path '*/prebuilt/*/bin/llvm-readelf' | head -1)"
mkdir -p "$(dirname "$PYSIDE_WHEEL")"
"$ROOT/.venv/bin/python" -I "$HERE/slim_wheel.py" \
    "$ORIG_PYSIDE_WHEEL" "$PYSIDE_WHEEL" "$READELF" "$HERE/qml"

# Сборка p4a (Python, OpenSSL, рецепты, dist) живёт в кэше, а не в
# mobile/.buildozer, который инструмент удаляет: повторная сборка только
# перепаковывает приложение. С нуля — если поменялось то, из чего собраны
# рецепты (колёса, deploy_android.py, модули), или с ключом --clean.
BUILD_CACHE="$CACHE/build-$ARCH"
STAMP="$(cat "$PYSIDE_WHEEL" "$SHIBOKEN_WHEEL" "$HERE/deploy_android.py" \
    <(echo "$QT_MODULES") | sha256sum | cut -c1-16)"
if [[ "$CLEAN" == 1 || "$(cat "$BUILD_CACHE/.quantis-stamp" 2>/dev/null)" != "$STAMP" ]]; then
    echo "Сборка с нуля (кэш p4a сброшен)"
    rm -rf "$BUILD_CACHE"
fi
mkdir -p "$BUILD_CACHE"
rm -rf "$HERE/.buildozer"
ln -sfn "$BUILD_CACHE" "$HERE/.buildozer"

# Список библиотек инструмент кэширует в spec: пусть считает заново.
rm -f "$HERE/pysidedeploy.spec" "$HERE/buildozer.spec"

# Плашка в шторке и служба mediaPlayback: Java-библиотека quantis-media.aar.
export QUANTIS_AAR="$("$HERE/android/build_aar.sh")"

cd "$HERE"
touch "$BUILD_CACHE/.started"
python "$HERE/deploy_android.py" \
    --name QuantisMobile \
    --wheel-pyside "$PYSIDE_WHEEL" \
    --wheel-shiboken "$SHIBOKEN_WHEEL" \
    --sdk-path "$CACHE/android-sdk" \
    --extra-modules "$QT_MODULES" \
    --force "${ARGS[@]}"
rm -f "$HERE/.buildozer"
# Инструмент ловит исключения сам и выходит с кодом 0: смотрим на APK.
APK="$(find "$HERE" -maxdepth 1 -name 'QuantisMobile*.apk' -newer "$BUILD_CACHE/.started" | head -1)"
if [[ -z "$APK" ]]; then
    echo "APK не собран — см. вывод выше" >&2
    exit 1
fi
echo "$STAMP" > "$BUILD_CACHE/.quantis-stamp"
ls -la "$APK"
