"""Общие pytest-фикстуры."""

from __future__ import annotations

import sys
import tempfile

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

# Тесты пишут в QSettings("ReallyFun", "Quantis") — без этого они затирали
# настоящие настройки (качество фона, FPS, громкость). На Linux и macOS
# NativeFormat — это ini-файл, и setPath уводит его во временный каталог.
_SETTINGS_DIR = tempfile.mkdtemp(prefix="quantis-test-settings-")
for _format in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
    QSettings.setPath(_format, QSettings.Scope.UserScope, _SETTINGS_DIR)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
