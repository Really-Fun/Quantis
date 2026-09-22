"""Фоновый asyncio-loop в отдельном потоке. Qt — только в главном."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)
T = TypeVar("T")


class AsyncBridge(QObject):
    """Запускает coroutine в фоне, UI-колбэки — в главном потоке Qt."""

    _main_call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._loop = asyncio.new_event_loop()
        self._main_call.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)
        self._thread = threading.Thread(
            target=self._run_loop,
            name="quantis-async",
            daemon=True,
        )
        self._thread.start()

    def invoke_main(self, callback: Callable[[], None]) -> None:
        app = QApplication.instance()
        if app is not None and QThread.currentThread() == app.thread():
            self._dispatch(callback)
            return
        try:
            QTimer.singleShot(0, self, lambda cb=callback: self._dispatch(cb))
        except RuntimeError:
            logger.debug("invoke_main пропущен: Qt-объект AsyncBridge уже удалён")

    async def call_main(self, callback: Callable[[], T]) -> T:
        """Выполняет callback в UI-потоке и возвращает результат."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()

        def wrapper() -> None:
            try:
                result = callback()
            except Exception as exc:
                loop.call_soon_threadsafe(future.set_exception, exc)
            else:
                loop.call_soon_threadsafe(future.set_result, result)

        self.invoke_main(wrapper)
        return await future

    def schedule(self, coro: Coroutine[Any, Any, T]) -> None:
        asyncio.run_coroutine_threadsafe(self._run_safe(coro), self._loop)

    def _dispatch(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            logger.exception("Ошибка UI-колбэка")

    async def _run_safe(self, coro: Coroutine[Any, Any, T]) -> None:
        try:
            await coro
        except Exception:
            logger.exception("Ошибка фоновой задачи")

    def shutdown(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
