#!/usr/bin/env bash
# Проверка собранного dist/Quantis изнутри (Linux), см. packaging/smoke/plugin.py.
#     packaging/scripts/smoke_bundle.sh [путь к бинарнику] [каталог с mp3/m4a/webm]
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
APP=${1:-$ROOT/dist/Quantis/Quantis}
MEDIA=${2:-$ROOT/music}
BOX=$(mktemp -d -t quantis-smoke-XXXX)
mkdir -p "$BOX/home/.config/ReallyFun" "$BOX/data/plugins_dir/bundle_smoke" "$BOX/media"
printf '[plugins]\nenabled=bundle_smoke\n' > "$BOX/home/.config/ReallyFun/Quantis.conf"
for ext in mp3 m4a webm; do
  f=$(ls "$MEDIA"/*."$ext" 2>/dev/null | head -1)
  [ -n "$f" ] && cp "$f" "$BOX/media/sample.$ext"
done
cp "$ROOT/packaging/smoke/plugin.py" "$BOX/data/plugins_dir/bundle_smoke/plugin.py"
echo '{"id": "bundle_smoke", "name": "smoke"}' > "$BOX/data/plugins_dir/bundle_smoke/manifest.json"
HOME=$BOX/home XDG_CONFIG_HOME=$BOX/home/.config XDG_DATA_HOME=$BOX/home/.local/share \
XDG_CACHE_HOME=$BOX/home/.cache QUANTIS_DATA_DIR=$BOX/data QUANTIS_ENABLE_ADAPTER=0 \
QT_QPA_PLATFORM=offscreen SMOKE_MEDIA=$BOX/media SMOKE_OUT=$BOX/result.json \
  timeout 60 "$APP" > "$BOX/app.log" 2>&1
code=$?
if [ ! -f "$BOX/result.json" ]; then
  echo "FAIL: проверка не отработала (код $code), лог: $BOX/app.log"; tail -20 "$BOX/app.log"; exit 1
fi
cat "$BOX/result.json"; echo
exec python3 "$ROOT/packaging/smoke/verdict.py" "$BOX/result.json"
