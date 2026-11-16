"""Звук прекращается до длительной выгрузки сервисов при выходе."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from quantis.core.bootstrap import shutdown_application
from quantis.plugins import PluginRegistry


def test_shutdown_stops_playback_before_unloading_plugins(monkeypatch) -> None:
    calls: list[str] = []
    player = Mock()
    player.stop.side_effect = lambda **kwargs: calls.append("stop")
    music = Mock()
    music.shutdown.side_effect = lambda: calls.append("music")
    bundle = SimpleNamespace(
        player=player,
        music=music,
        async_bridge=SimpleNamespace(_loop=object()),
    )

    async def unload_all() -> None:
        pass

    monkeypatch.setattr(PluginRegistry, "instance", lambda: SimpleNamespace(unload_all=unload_all))

    def schedule(coro, loop):
        coro.close()
        calls.append("unload")
        return SimpleNamespace(result=lambda timeout: None)

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", schedule)

    shutdown_application(bundle)

    assert calls == ["stop", "unload", "music"]
    player.stop.assert_called_once_with(quiet=True)
