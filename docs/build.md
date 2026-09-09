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
poetry run python scripts/build_exe.py qt

REM VLC — нужен установленный VideoLAN VLC (для libvlc.dll + plugins)
poetry install --with dev,vlc
set VLC_HOME=C:\Program Files\VideoLAN\VLC
poetry run python scripts/build_exe.py vlc
```

То же через PowerShell:

```powershell
.\scripts\build.ps1 -Backend qt
.\scripts\build.ps1 -Backend vlc -VlcHome "C:\Program Files\VideoLAN\VLC"
```

Каталог VLC можно передать и аргументом, минуя переменную окружения:

```bat
poetry run python scripts/build_exe.py vlc --vlc-home "C:\Program Files\VideoLAN\VLC"
```

`scripts/build_exe.py` — тонкая обёртка над PyInstaller: выставляет
`QUANTIS_MEDIA_BACKEND`, запускает `main.spec` и раскладывает результат по
`dist/` (рабочие файлы — в `build/pyi-<backend>/`). Выбор движка на этапе
сборки читают rthook'и из `packaging/`.

В сборку **Quantis-VLC** дополнительно копируются `libvlc.dll` и `plugins/`
из `VLC_HOME`.

## Linux (MPRIS)

Обычная сборка `qt` / `vlc` **вырезает** `mpris_server` (он нужен только
на Linux и тянет PyGObject). Вариант с медиа-клавишами:

```bash
# нужен системный PyGObject, на Arch: pacman -S python-gobject
poetry install --with dev
poetry run python scripts/build_exe.py qt --mpris
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

Готовый скрипт — [installer/quantis.iss](../installer/quantis.iss). Ему нужен
уже собранный onedir-каталог из `dist/`:

```bat
poetry run python scripts/build_exe.py qt
poetry run python scripts/build_installer.py

REM VLC-сборка
poetry run python scripts/build_exe.py vlc
poetry run python scripts/build_installer.py --backend vlc
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
