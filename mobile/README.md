# Quantis Mobile (бета для Android)

Отдельное небольшое приложение, а не настольный Quantis. Интерфейс на
Qt Quick (QML, Material, тёмная тема) в `qml/`, логика — `backend.py`.

Что умеет:

- **Яндекс Музыка** (вход по токену, поиск, игра потоком по прямой ссылке)
  и **YouTube** (поиск через yt-dlp, игра сразу через локальный прокси
  `stream_proxy.py`);
- **«Моя волна»** Яндекса с настроениями (`wave.py`): следующие треки
  подгружаются заранее, Яндекс узнаёт о пропусках и дослушанных;
- полноэкранный плеер с пластинкой и цветом от обложки, жесты (свайп по
  обложке — соседний трек, по пластинке — перемотка), мини-плеер;
- медиатека Яндекса: «Мне нравится» и свои плейлисты (кэш на телефоне,
  обновляются в фоне);
- очередь, «Любимое», история, недавние запросы, меню «⋮» у трека,
  таймер сна, перемешивание и повтор;
- кнопки в шторке и игра в фоне (служба `mediaPlayback`, Java-часть в
  `android/`, вызывается из Python через JNI в `android_media.py`).

Чего нет: SoundCloud, скачивания для офлайна, текстов песен; лайк в
приложении не попадает в «Мне нравится» Яндекса (он хранится на телефоне).

## Запуск на компьютере

    ../.venv/bin/python main.py

Окно размера телефона, те же функции (кроме шторки).

## Сборка APK (Linux)

Один раз:

    CACHE=~/.pyside6_android_deploy
    uv venv --python 3.14 $CACHE/tool-venv
    VIRTUAL_ENV=$CACHE/tool-venv uv pip install pyside6==6.12.0 \
        -r .venv/lib/python3.14/site-packages/PySide6/scripts/requirements-android.txt
    mkdir -p $CACHE/wheels && cd $CACHE/wheels
    for p in pyside6 shiboken6; do
        curl -LO https://download.qt.io/official_releases/QtForPython/$p/$p-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl
    done

Нужен JDK 17. NDK r28c `pyside6-android-deploy` скачает сам в
`~/.pyside6_android_deploy`, недостающие части SDK докачает buildozer.

Сборка:

    ./build_apk.sh              # телефон (aarch64)
    ./build_apk.sh --clean      # с нуля, без кэша
    ARCH=x86_64 ./build_apk.sh  # эмулятор; нужны колёса x86_64

APK появляется в этой папке. Установка: `adb install -r QuantisMobile*.apk`.

Первая сборка идёт с нуля (Python, OpenSSL и рецепты python-for-android
собираются из исходников). Дальше сборка p4a хранится в
`~/.pyside6_android_deploy/build-<arch>` и повторная сборка только
перепаковывает приложение. С нуля скрипт собирает сам, если поменялись
колёса, `deploy_android.py` или список модулей Qt (или QML-импорты, от
которых зависит урезанное колесо).

Вес: `slim_wheel.py` оставляет из колеса PySide6 только нужные модули,
QML-модули, плагины и библиотеки, без FFmpeg (звук идёт через системный
MediaPlayer) и без разрешений камеры, микрофона и Bluetooth. Если новый
код импортирует другой модуль Qt или QML, добавьте его в `MODULES`
в `slim_wheel.py` (QML-импорты из `qml/` находятся сами).
