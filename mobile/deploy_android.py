"""pyside6-android-deploy с нашими настройками buildozer.

Инструмент сам пишет buildozer.spec и сразу запускает buildozer, а ключи,
которые нам нужны, не пробрасывает. Запускаем его скрипт в этом процессе
и дописываем ключи перед записью spec:

- android.meta_data: android.app.background_running=true — без него Qt
  останавливает цикл событий в свёрнутом приложении (не включался
  следующий трек, не работали бы кнопки плашки);
- android.add_aars: quantis-media.aar (MediaBridge + служба mediaPlayback)
  и репозиторий flatDir, через который Gradle его находит.

Запуск: tool-venv/bin/python deploy_android.py <аргументы pyside6-android-deploy>
Переменная QUANTIS_AAR — путь к собранному AAR.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

import PySide6

SCRIPTS = Path(PySide6.__file__).parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from deploy_lib.android import buildozer  # noqa: E402

EXTRA = {
    "android.meta_data": "android.app.background_running=true",
    "android.add_aars": os.environ["QUANTIS_AAR"],
    # p4a кладёт AAR в libs/ и подключает как name:/ext:, а репозитория
    # flatDir в его шаблоне нет: Gradle писал «Could not find :quantis-media:».
    "android.add_gradle_repositories": "flatDir { dirs 'libs' }",
}

_original_update = buildozer.BuildozerConfig.update_config


# Загрузчик Qt грузит --qt-libs по порядку, а инструмент собирает их через
# set(): порядок случайный от сборки к сборке. Когда Multimedia шла раньше
# Core, её JNI_OnLoad падал (QJniEnvironment::getJniEnv, null) до старта
# Python. Ставим модули в порядке зависимостей.
_QT_ORDER = ["Core", "Gui", "Network", "Concurrent", "Widgets", "Multimedia"]


def _ordered(names: list[str], key) -> list[str]:
    return sorted(names, key=lambda n: (key(n), n))


def _fix_load_order(extra_args: str) -> str:
    parts = []
    for part in extra_args.split():
        if "=" not in part:
            parts.append(part)
            continue
        option, _, value = part.partition("=")
        names = [n for n in value.split(",") if n]
        if option == "--qt-libs":
            names = _ordered(
                names,
                lambda n: _QT_ORDER.index(n) if n in _QT_ORDER else len(_QT_ORDER),
            )
        elif option == "--load-local-libs":
            # платформенный плагин — первым: остальным нужен готовый Qt
            names = _ordered(names, lambda n: 0 if "platforms" in n else 1)
        parts.append(f"{option}={','.join(names)}")
    return " ".join(parts)


def _update_config(self) -> None:
    for key, value in EXTRA.items():
        self.set_value("app", key, value, raise_warning=False)
        print(f"[quantis] buildozer {key} = {self.get_value('app', key)}")
    extra_args = self.get_value("app", "p4a.extra_args") or ""
    fixed = _fix_load_order(extra_args)
    self.set_value("app", "p4a.extra_args", fixed, raise_warning=False)
    print(f"[quantis] buildozer p4a.extra_args = {fixed}")
    _original_update(self)


buildozer.BuildozerConfig.update_config = _update_config

script = SCRIPTS / "android_deploy.py"
sys.argv = [str(script), *sys.argv[1:]]
runpy.run_path(str(script), run_name="__main__")
