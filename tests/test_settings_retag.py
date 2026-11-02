"""Кнопка «Записать теги» на странице настроек."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from PySide6.QtWidgets import QPushButton

import quantis.models  # noqa: F401  (порядок импорта: циклическая зависимость)
from quantis.services import library_retag
from quantis.services.library_retag import RetagReport
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.settings_page import SettingsPage


class _Bridge:
    def schedule(self, coro) -> None:
        asyncio.run(coro)

    def invoke_main(self, callback) -> None:
        callback()


def _music():
    return SimpleNamespace(downloader=SimpleNamespace(index=object()))


def _button(page):
    return next(
        b for b in page.findChildren(QPushButton) if b.text() == "Записать теги"
    )


def _Prefs():  # noqa: N802
    return UiPreferences()  # страница только читает настройки


def test_button_hidden_without_music(qapp):
    page = SettingsPage(_Prefs(), _Bridge())
    assert _button(page).isHidden()


def test_click_runs_retag_and_shows_result(qapp, monkeypatch):
    seen = {}

    async def fake(downloader, index, on_progress=None):
        seen["during"] = _button(page).isEnabled()
        on_progress(1, 2)
        seen["status"] = page._retag_status.text()
        return RetagReport(done=2, already=3, skipped=1)

    monkeypatch.setattr(library_retag, "retag_legacy", fake)
    page = SettingsPage(_Prefs(), _Bridge(), music=_music())
    button = _button(page)
    button.click()
    assert seen["during"] is False
    assert seen["status"] == "Обработано 1 из 2"
    assert page._retag_status.text() == "Готово: 2, уже были: 3, пропущено: 1"
    assert button.isEnabled()


def test_failure_reenables_button(qapp, monkeypatch):
    async def boom(downloader, index, on_progress=None):
        raise RuntimeError("x")

    monkeypatch.setattr(library_retag, "retag_legacy", boom)
    page = SettingsPage(_Prefs(), _Bridge(), music=_music())
    _button(page).click()
    assert page._retag_status.text() == "Ошибка: не удалось записать теги"
    assert _button(page).isEnabled()
