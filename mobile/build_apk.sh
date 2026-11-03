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

# В колесе 6.12.0 файл зависимостей QtMultimedia называет библиотеки FFmpeg
# libavcodec_<abi>.so, а лежат они как libavcodec.so: загрузчик Qt падал на
# старте («libswresample_arm64-v8a.so not found»). Убираем их из списка
# предзагрузки — плагин FFmpeg подтянет их сам, он ссылается на имена без
# суффикса.
mkdir -p "$(dirname "$PYSIDE_WHEEL")"
"$ROOT/.venv/bin/python" - "$ORIG_PYSIDE_WHEEL" "$PYSIDE_WHEEL" <<'PY'
import re, sys, zipfile
src, dst = sys.argv[1:]
ffmpeg = re.compile(r'\s*<lib file="lib/lib(avcodec|avformat|avutil|swscale|swresample)_[^"]*\.so"\s*/>')
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith("-android-dependencies.xml"):
            data = ffmpeg.sub("", data.decode("utf-8")).encode("utf-8")
        zout.writestr(item, data)
PY
# Список библиотек инструмент кэширует в spec: пусть считает заново.
rm -f "$HERE/pysidedeploy.spec" "$HERE/buildozer.spec"

# Плашка в шторке и служба mediaPlayback: Java-библиотека quantis-media.aar.
export QUANTIS_AAR="$("$HERE/android/build_aar.sh")"

cd "$HERE"
python "$HERE/deploy_android.py" \
    --name QuantisMobile \
    --wheel-pyside "$PYSIDE_WHEEL" \
    --wheel-shiboken "$SHIBOKEN_WHEEL" \
    --sdk-path "$CACHE/android-sdk" \
    --extra-modules Multimedia,Qml,Quick,QuickControls2,Svg \
    --force "$@"
