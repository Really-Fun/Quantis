"""Урезанное колесо PySide6 для APK: только то, что нужно приложению.

Колесо PySide6 для Android — весь Qt (3D, Designer, WebView, Charts…),
~250 МБ в распакованном виде. Рецепт p4a кладёт его в site-packages
целиком и ещё раз копирует Qt/lib в lib/ APK. Здесь остаётся:

- Python-модули из MODULES и те, что инструмент добавит по зависимостям;
- QML-модули, до которых дотягиваются импорты приложения (по qmldir и
  import в .qml самих модулей), стили только Basic и Material;
- плагины из PLUGINS;
- из Qt/lib — только библиотеки, нужные всему этому (DT_NEEDED по
  цепочке) и перечисленные в *-android-dependencies.xml оставленных модулей.

Заодно правятся файлы зависимостей: без FFmpeg (на телефоне играет
системный MediaPlayer, QT_MEDIA_BACKEND=android) и без разрешений
камеры, микрофона и Bluetooth, которые тянет QtMultimedia.

Запуск: python slim_wheel.py <колесо> <результат> <llvm-readelf> <qml-каталог>
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

# Модули, которые инструмент так или иначе возьмёт: импорты приложения,
# --extra-modules и их зависимости (рецепт копирует Qt<Модуль>.abi3.so —
# файл обязан быть в колесе).
MODULES = {
    "Core", "Gui", "Network", "Concurrent", "OpenGL", "Svg",
    "Qml", "Quick", "QuickControls2", "Multimedia",
}
# Плагины Qt: окно Android, SVG/JPEG для значков и обложек, звук через
# системный MediaPlayer.
PLUGINS = {
    "platforms/qtforandroid",
    "imageformats/qsvg",
    "imageformats/qjpeg",
    "iconengines/qsvgicon",
    "multimedia/androidmediaplugin",
}
# Стили Controls, кроме этих, не нужны (Material + Basic как запасной).
STYLES = {"Basic", "Material"}
# Разрешения, которые QtMultimedia просит «на всякий случай».
DROP_PERMISSIONS = {"CAMERA", "RECORD_AUDIO", "BLUETOOTH"}

PREFIX = "PySide6/"
QT = PREFIX + "Qt/"
_FFMPEG_LIB = re.compile(
    r'\s*<lib file="(?:lib/lib(?:avcodec|avformat|avutil|swscale|swresample)_[^"]*'
    r'|lib/libQt6FFmpegStub-[^"]*|plugins/multimedia/libplugins_multimedia_ffmpeg[^"]*)'
    r'\.so"\s*/>'
)
_PERMISSION = re.compile(r'\s*<permission name="android\.permission\.(\w+)"\s*/>')
_QML_IMPORT = re.compile(r"^\s*import\s+([A-Za-z][\w.]*)", re.M)


def _qmldir_imports(text: str) -> set[str]:
    """Обязательные импорты из qmldir (optional/default — не тянем)."""
    found = set()
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] in {"import", "depends"}:
            found.add(words[1])
    return found


def _module_dir(module: str) -> str:
    return QT + "qml/" + module.replace(".", "/") + "/"


def _keep_qml(names: list[str], zin: zipfile.ZipFile, app_qml: Path) -> set[str]:
    """Файлы Qt/qml/, нужные импортам приложения."""
    qml = [n for n in names if n.startswith(QT + "qml/")]
    module_dirs = {n[: -len("qmldir")] for n in qml if n.endswith("/qmldir")}

    todo = set()
    for path in app_qml.rglob("*.qml"):
        todo |= set(_QML_IMPORT.findall(path.read_text(encoding="utf-8")))
    seen: set[str] = set()
    keep: set[str] = {QT + "qml/builtins.qmltypes", QT + "qml/jsroot.qmltypes"}
    while todo:
        module = todo.pop()
        if module in seen:
            continue
        seen.add(module)
        mdir = _module_dir(module)
        if mdir not in module_dirs:
            continue  # модуль без своего каталога (встроенный) или не из Qt
        if mdir.count("/Controls/") and mdir.split("/Controls/")[1].split("/")[0] not in (
            STYLES | {"impl", ""}
        ):
            continue
        for name in qml:
            if not name.startswith(mdir) or name.endswith("/"):
                continue
            rest = name[len(mdir):]
            # файлы во вложенных каталогах, которые сами модули, — отдельно;
            # каталоги без qmldir (картинки, шрифты стиля) — часть модуля
            parts = rest.split("/")
            sub_module = any(
                mdir + "/".join(parts[: i + 1]) + "/" in module_dirs
                for i in range(len(parts) - 1)
            )
            if sub_module or "designer" in parts[:-1]:
                continue
            keep.add(name)
            if rest == "qmldir":
                todo |= _qmldir_imports(zin.read(name).decode("utf-8"))
            elif rest.endswith(".qml"):
                todo |= set(_QML_IMPORT.findall(zin.read(name).decode("utf-8")))
    return keep


def _needed(readelf: str, data: bytes) -> set[str]:
    with tempfile.NamedTemporaryFile(suffix=".so") as tmp:
        tmp.write(data)
        tmp.flush()
        out = subprocess.run(
            [readelf, "--dynamic", tmp.name], capture_output=True, text=True, check=True
        ).stdout
    return set(re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out))


def slim(src: Path, dst: Path, readelf: str, app_qml: Path) -> None:
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        arch = re.search(r"_(arm64-v8a|x86_64|armeabi-v7a|x86)\.so$", next(
            n for n in names if n.startswith(QT + "lib/libQt6Core_")
        )).group(1)
        libs = {PurePosixPath(n).name: n for n in names if n.startswith(QT + "lib/")}

        keep_qml = _keep_qml(names, zin, app_qml)
        plugin_files = {
            f"{QT}plugins/{p.split('/')[0]}/libplugins_{p.replace('/', '_')}_{arch}.so"
            for p in PLUGINS
        }
        # Python-модули: заданные + те, чьи библиотеки окажутся в сборке
        # (инструмент находит такие сам и требует их .abi3.so).
        bindings = {
            m for m in (PurePosixPath(n).name for n in names if n.startswith(PREFIX))
            if re.fullmatch(r"Qt\w+\.abi3\.so", m)
        }
        modules = set(MODULES)
        keep_libs: set[str] = set()

        def dep_xml_libs(module: str) -> set[str]:
            xml = libs.get(f"Qt6{module}_{arch}-android-dependencies.xml")
            if not xml:
                return set()
            text = _FFMPEG_LIB.sub("", zin.read(xml).decode("utf-8"))
            return {
                PurePosixPath(f).name
                for f in re.findall(r'<lib file="lib/([^"]+\.so)"', text)
            }

        roots = [PREFIX + "libpyside6.abi3.so", PREFIX + "libpyside6qml.abi3.so"]
        roots += sorted(plugin_files)
        roots += sorted(n for n in keep_qml if n.endswith(".so"))
        changed = True
        while changed:
            changed = False
            todo = list(roots) + [PREFIX + f"Qt{m}.abi3.so" for m in modules]
            todo += [libs[lib] for m in modules for lib in dep_xml_libs(m) if lib in libs]
            todo += [libs[f"libQt6{m}_{arch}.so"] for m in modules
                     if f"libQt6{m}_{arch}.so" in libs]
            seen: set[str] = set()
            while todo:
                path = todo.pop()
                if path in seen:
                    continue
                seen.add(path)
                if path.startswith(QT + "lib/"):
                    keep_libs.add(path)
                for lib in _needed(readelf, zin.read(path)):
                    if lib in libs:
                        todo.append(libs[lib])
            for path in keep_libs:
                m = re.fullmatch(rf"libQt6(\w+?)_{arch}\.so", PurePosixPath(path).name)
                if m and f"Qt{m.group(1)}.abi3.so" in bindings and m.group(1) not in modules:
                    modules.add(m.group(1))
                    changed = True

        def wanted(name: str) -> bool:
            rel = name[len(PREFIX):] if name.startswith(PREFIX) else None
            if rel is None:
                return True  # dist-info
            if name.endswith(".pyi") or rel.split("/")[0] in {
                "include", "typesystems", "glue", "scripts", "examples", "QtAsyncio",
            }:
                return False
            if re.fullmatch(r"Qt\w+\.abi3\.so", rel):
                return rel[2:-len(".abi3.so")] in modules
            if rel.startswith("Qt/lib/"):
                return name in keep_libs or name.endswith("-android-dependencies.xml")
            if rel.startswith("Qt/plugins/"):
                return name in plugin_files
            if rel.startswith("Qt/qml/"):
                return name in keep_qml
            if rel.startswith("Qt/translations/"):
                return False
            return True

        kept = dropped = 0
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if not wanted(item.filename):
                    dropped += item.file_size
                    continue
                data = zin.read(item.filename)
                if item.filename.endswith("-android-dependencies.xml"):
                    text = _FFMPEG_LIB.sub("", data.decode("utf-8"))
                    text = _PERMISSION.sub(
                        lambda m: "" if m.group(1) in DROP_PERMISSIONS else m.group(0), text
                    )
                    data = text.encode("utf-8")
                kept += len(data)
                zout.writestr(item, data)
    print(
        f"slim_wheel: оставлено {kept / 2**20:.0f} МБ, убрано {dropped / 2**20:.0f} МБ; "
        f"модули: {','.join(sorted(modules))}"
    )


if __name__ == "__main__":
    slim(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
