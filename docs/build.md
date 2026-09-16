# Сборка Quantis

Версия приложения живёт **только** в `pyproject.toml` (`[project].version`).
Её подхватывают UI и установщик Inno Setup.

```bash
poetry version 0.2.1    # поставить конкретную
poetry version patch    # 0.2.1 → 0.2.2
```

Собираются два варианта приложения — они отличаются только медиадвижком.
На Linux есть третий: тот же Qt/VLC, но с MPRIS в бандле (`--mpris`).

| Сборка | Движок | Артефакт |
|--------|--------|----------|
| **qt** | Qt Multimedia (FFmpeg) | `dist\Quantis\Quantis.exe` |
| **vlc** | libVLC (`python-vlc`) | `dist\Quantis-VLC\Quantis-VLC.exe` |
| **qt --mpris** | Qt + `mpris_server` | `dist/Quantis/Quantis` |

## Windows

```bat
REM Qt (по умолчанию)
poetry install --with dev
poetry run python packaging/scripts/build_exe.py qt

REM VLC — нужен установленный VideoLAN VLC (для libvlc.dll + plugins)
poetry install --with dev,vlc
set VLC_HOME=C:\Program Files\VideoLAN\VLC
poetry run python packaging/scripts/build_exe.py vlc
```

То же через PowerShell:

```powershell
.\packaging\scripts\build.ps1 -Backend qt
.\packaging\scripts\build.ps1 -Backend vlc -VlcHome "C:\Program Files\VideoLAN\VLC"
```

Каталог VLC можно передать и аргументом, минуя переменную окружения:

```bat
poetry run python packaging/scripts/build_exe.py vlc --vlc-home "C:\Program Files\VideoLAN\VLC"
```

`packaging/scripts/build_exe.py` — тонкая обёртка над PyInstaller: выставляет
`QUANTIS_MEDIA_BACKEND`, запускает `packaging/pyinstaller/main.spec` и раскладывает
результат по `dist/` (рабочие файлы — в `build/pyi-<backend>/`). Выбор движка на
этапе сборки читают rthook'и из `packaging/pyinstaller/hooks/`.

В сборку **Quantis-VLC** дополнительно копируются `libvlc.dll` и `plugins/`
из `VLC_HOME`.

### VERSIONINFO (Windows)

При сборке `packaging/pyinstaller/main.spec` пишет
`packaging/pyinstaller/quantis_version_info.txt` из `[project]` в
`pyproject.toml` (версия, описание, автор → CompanyName) и передаёт его в
`EXE(..., version=...)`. В проводнике это поля Properties → Details у
`Quantis.exe`.

### Свой PyInstaller bootloader (меньше AV false positives)

Стоковый `runw.exe` из релиза PyInstaller общий у тысяч неподписанных
сборок — эвристики часто помечают такой PE как dropper. Локальная
пересборка stub’а меняет отпечаток.

Нужны: Git, VS Build Tools 2017+ (MSVC C++) **или** MinGW-w64
(например `C:\msys64\ucrt64\bin`). Скрипт сам выбирает MinGW, если MSVC нет.

```powershell
# Клонирует pyinstaller/pyinstaller (тег = установленная версия),
# собирает bootloader через waf и подменяет runw.exe / run.exe
# в активном PyInstaller (у нас часто это ./PyInstaller/).
.\packaging\scripts\rebuild_pyi_bootloader.ps1

# Явный тег / MinGW / каталог назначения
.\packaging\scripts\rebuild_pyi_bootloader.ps1 -Tag v6.22.2
.\packaging\scripts\rebuild_pyi_bootloader.ps1 -Gcc
.\packaging\scripts\rebuild_pyi_bootloader.ps1 -Dest "C:\projects\Quantis\PyInstaller"
```

Исходники временно лежат в `build/pyinstaller-src/` (уже в `.gitignore`
через `build/`). Не коммитьте развёрнутый tree `PyInstaller/` из wheel —
в нём нет `bootloader/src`, только готовые бинарники.

После подмены пересоберите приложение:

```bat
poetry run python packaging/scripts/build_exe.py qt
```

На VirusTotal лучше заливать onedir zip или Inno-установщик, а не голый
`Quantis.exe`. Не переключайтесь на onefile ради AV — для FP он обычно хуже.

## Linux (MPRIS)

Обычная сборка `qt` / `vlc` **вырезает** `mpris_server` (он нужен только
на Linux и тянет PyGObject). Вариант с медиа-клавишами:

```bash
# нужен системный PyGObject, на Arch: pacman -S python-gobject
poetry install --with dev
poetry run python packaging/scripts/build_exe.py qt --mpris
```

Результат тот же onedir: `dist/Quantis/Quantis`.

## Переключение движка без пересборки

Для разработки движок задаётся переменной окружения:

```bat
set QUANTIS_MEDIA_BACKEND=vlc
poetry install --with vlc
poetry run quantis
```

## Установщик Inno Setup

Готовый скрипт — [packaging/inno/quantis.iss](../packaging/inno/quantis.iss). Ему нужен
уже собранный onedir-каталог из `dist/`:

```bat
poetry run python packaging/scripts/build_exe.py qt
poetry run python packaging/scripts/build_installer.py

REM VLC-сборка
poetry run python packaging/scripts/build_exe.py vlc
poetry run python packaging/scripts/build_installer.py --backend vlc
```

Версия установщика берётся из `pyproject.toml` (``poetry version``).
Результат — `dist\installer\Quantis-<версия>-setup.exe`. По умолчанию установка
идёт в `{autopf}` (Program Files при установке для всех, `%LOCALAPPDATA%\Programs`
при установке «только для меня» — тогда UAC не появляется).

При удалении установщик чистит кэш и спрашивает, удалять ли данные
пользователя. Скачанная музыка не удаляется никогда.

## Каталоги данных

Приложение **ничего не пишет в свой каталог установки** — иначе установка в
Program Files требовала бы прав администратора. Все записываемые пути выдаёт
[src/quantis/utils/app_paths.py](../src/quantis/utils/app_paths.py).

| Что | Windows | Linux |
|-----|---------|-------|
| Данные (база, плейлисты, токены, плагины, обои) | `%LOCALAPPDATA%\Quantis` | `$XDG_DATA_HOME/quantis` |
| Кэш | `%LOCALAPPDATA%\Quantis\cache` | `$XDG_CACHE_HOME/quantis` |
| Скачанная музыка | `%USERPROFILE%\Music\Quantis` | `~/Music/Quantis` |

Папку музыки можно сменить в **Настройки → Хранилище**; там же показан путь к
каталогу данных и кнопки «Открыть».

Порядок выбора каталога данных:

1. `QUANTIS_DATA_DIR` — если задан, используется как есть;
2. портативный режим — файл `portable.txt` рядом с exe или `QUANTIS_PORTABLE=1`,
   данные лежат рядом с exe (музыка тоже, в `music/`);
3. запуск из исходников — корень проекта, как было исторически;
4. иначе — каталог пользователя из таблицы выше.

Если выбранный каталог недоступен для записи (например, портативная сборка
распакована в Program Files), приложение сообщает об этом в лог и само
переезжает в каталог пользователя вместо падения с ошибкой прав.

Данные из старой раскладки (когда всё лежало рядом с exe) при первом запуске
копируются в новый каталог: `music`, `covers`, `playlists`, `playlist_covers`,
`credentials`, `plugins_dir`, `background`, `player_history.db`. Копируются, а
не переносятся — источник может быть read-only. Повторно миграция не
выполняется, признак — файл `.migrated` в каталоге данных.

## Плагины в установленной сборке

Плагины ищутся в двух местах: записываемый `plugins_dir/` в каталоге данных
(туда ставятся плагины из UI) и `plugins_dir/` рядом с exe — комплектные,
только на чтение. При совпадении имён побеждает пользовательский.
