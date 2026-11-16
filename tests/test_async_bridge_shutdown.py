"""Фоновые задачи должны завершаться вместе с мостом asyncio."""

import asyncio
from threading import Event

from quantis.core.async_bridge import AsyncBridge


def test_shutdown_cancels_running_tasks_and_runs_cleanup() -> None:
    bridge = AsyncBridge()
    started = Event()
    cleaned_up = Event()

    async def worker() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned_up.set()

    bridge.schedule(worker())
    assert started.wait(2)

    bridge.shutdown()

    assert cleaned_up.is_set()
    assert not bridge._thread.is_alive()
