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


def _update_config(self) -> None:
    for key, value in EXTRA.items():
        self.set_value("app", key, value, raise_warning=False)
        print(f"[quantis] buildozer {key} = {self.get_value('app', key)}")
    _original_update(self)


buildozer.BuildozerConfig.update_config = _update_config

script = SCRIPTS / "android_deploy.py"
sys.argv = [str(script), *sys.argv[1:]]
runpy.run_path(str(script), run_name="__main__")
