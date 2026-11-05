#!/usr/bin/env bash
# Собирает quantis-media.aar: MediaBridge + PlaybackService и манифест со
# службой mediaPlayback. Нужен только JDK и android.jar из SDK.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_SDK:-$HOME/.pyside6_android_deploy/android-sdk}"
API="${ANDROID_API:-35}"
ANDROID_JAR="$SDK/platforms/android-$API/android.jar"
OUT="$HERE/build"

rm -rf "$OUT"
mkdir -p "$OUT/classes" "$OUT/aar"
javac -encoding UTF-8 -source 11 -target 11 -Xlint:-options \
    -classpath "$ANDROID_JAR" -d "$OUT/classes" \
    $(find "$HERE/src" -name '*.java')
jar cf "$OUT/aar/classes.jar" -C "$OUT/classes" .
cp "$HERE/AndroidManifest.xml" "$OUT/aar/AndroidManifest.xml"
# Значки плашки (векторы): Gradle сливает res/ библиотеки с ресурсами
# приложения, Java находит их по имени (getIdentifier) — своего R нет.
cp -r "$HERE/res" "$OUT/aar/res"
: > "$OUT/aar/R.txt"
for f in "$HERE"/res/drawable/*.xml; do
    echo "int drawable $(basename "$f" .xml) 0x0" >> "$OUT/aar/R.txt"
done
(cd "$OUT/aar" && jar cfM "$OUT/quantis-media.aar" AndroidManifest.xml classes.jar R.txt res)
echo "$OUT/quantis-media.aar"
