"""Запуск coroutine из UI."""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from quantis.core.async_bridge import AsyncBridge


def schedule(
    coro: Coroutine[Any, Any, Any],
    bridge: AsyncBridge | None = None,
) -> None:
    if bridge is None:
        raise RuntimeError("AsyncBridge не передан в schedule()")
    bridge.schedule(coro)
