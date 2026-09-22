"""Интеграционный тест поиска через SearchViewModel + AsyncBridge."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from quantis.controllers.playback_controller import PlaybackController
from quantis.core.async_bridge import AsyncBridge
from quantis.player import Player, QtMediaEngine
from quantis.providers import PlaylistManager
from quantis.services.async_finder import AsyncFinder
from quantis.services.music_service import MusicService
from quantis.ui.viewmodels.search_vm import SearchViewModel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# Настоящий поиск по API Яндекса/YouTube: без сети и токена модель пуста.
@pytest.mark.network
def test_search_vm_populates_model(qapp):
    bridge = AsyncBridge()
    bridge.setParent(qapp)
    finder = AsyncFinder()
    music = MusicService(finder=finder)
    playback = PlaybackController(
        player=Player(engine=QtMediaEngine()),
        playlist_manager=PlaylistManager(),
        music_service=music,
        async_bridge=bridge,
    )
    vm = SearchViewModel(finder, playback, bridge)

    loop = QEventLoop()
    results: list[int] = []

    def on_results():
        results.append(vm.model.rowCount())
        loop.quit()

    vm.results_changed.connect(on_results)
    vm.search("radiohead")
    vm.search_now()

    QTimer.singleShot(30000, loop.quit)
    loop.exec()

    bridge.shutdown()
    finder.shutdown()
    music.shutdown()

    assert results, "results_changed не вызван"
    assert results[-1] > 0, f"модель пуста: {results[-1]}"
