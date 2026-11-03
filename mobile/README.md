# Quantis Mobile (бета для Android)

Маленькое отдельное приложение: поиск на YouTube, воспроизведение, пауза,
перемотка, следующий и предыдущий трек. Трек сначала скачивается в кэш
приложения, потом играет как файл: повторное прослушивание мгновенное.

Чего нет: Яндекс Музыки, SoundCloud, плейлистов, истории, игры в фоне
(свёрнутое приложение Android может остановить).

## Запуск на компьютере

    ../.venv/bin/python main.py

Окно размера телефона, те же функции.

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

    ./build_apk.sh            # телефон (aarch64)
    ARCH=x86_64 ./build_apk.sh  # эмулятор; нужны колёса x86_64

APK появляется в этой папке. Установка: `adb install -r QuantisMobile*.apk`.
