"""Composition root: сборка зависимостей без AppContext."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quantis.controllers.playback_controller import PlaybackController
from quantis.controllers.playback_history_watcher import PlaybackHistoryWatcher
from quantis.core.async_bridge import AsyncBridge
from quantis.core.plugin_host import PluginHost
from quantis.player.factory import create_media_engine
from quantis.player.player import Player
from quantis.plugins.event_bus import EventBus
from quantis.providers import PlaylistManager
from quantis.services.music_service import MusicService
from quantis.services.track_history import TrackHistoryService

logger = logging.getLogger(__name__)


@dataclass
class ApplicationBundle:
    """Объекты, собранные при старте. Используется только в main и MainWindow."""

    async_bridge: AsyncBridge
    event_bus: EventBus
    player: Player
    music: MusicService
    playlists: PlaylistManager
    playback: PlaybackController
    history: TrackHistoryService
    history_watcher: PlaybackHistoryWatcher
    plugin_host: PluginHost


def build_application(bridge: AsyncBridge) -> ApplicationBundle:
    from quantis.providers import PathProvider
    from quantis.utils import app_paths

    app_paths.migrate_legacy_data()
    app_paths.ensure_dirs()
    PathProvider.ensure_storage_dirs()
    logger.info("Каталог данных: %s", app_paths.data_dir())
    event_bus = EventBus()
    player = Player(engine=create_media_engine())
    music = MusicService()
    playlists = PlaylistManager()
    history = TrackHistoryService()
    playback = PlaybackController(
        player=player,
        playlist_manager=playlists,
        music_service=music,
        event_bus=event_bus,
        history=history,
        async_bridge=bridge,
    )
    plugin_host = PluginHost(
        event_bus=event_bus,
        playback=playback,
        music=music,
        async_bridge=bridge,
    )

    wire_player_events(player, event_bus, playback, bridge)
    wire_event_bus_navigation(event_bus, playback, bridge)
    history_watcher = PlaybackHistoryWatcher(player, history, event_bus, bridge)

    return ApplicationBundle(
        async_bridge=bridge,
        event_bus=event_bus,
        player=player,
        music=music,
        playlists=playlists,
        playback=playback,
        history=history,
        history_watcher=history_watcher,
        plugin_host=plugin_host,
    )


def wire_player_events(
    player: Player,
    event_bus: EventBus,
    playback: PlaybackController,
    bridge: AsyncBridge,
) -> None:
    player.on_playback_paused(event_bus.playback_paused.emit)
    player.on_playback_resumed(event_bus.playback_resumed.emit)
    player.on_track_finished(event_bus.track_finished.emit)

    def schedule_auto_next() -> None:
        if playback.playlist_manager.current_playlist is None:
            return
        bridge.schedule(playback.handle_track_finished())

    def schedule_next() -> None:
        bridge.schedule(playback.play_next())

    def schedule_previous() -> None:
        bridge.schedule(playback.play_previous())

    player.on_next_requested(schedule_next)
    player.on_previous_requested(schedule_previous)
    player.on_track_finished(schedule_auto_next)
    player.on_stream_error(playback.handle_stream_error)


def wire_event_bus_navigation(
    event_bus: EventBus,
    playback: PlaybackController,
    bridge: AsyncBridge,
) -> None:
    event_bus.next_requested.connect(lambda: bridge.schedule(playback.play_next()))
    event_bus.previous_requested.connect(
        lambda: bridge.schedule(playback.play_previous())
    )


def shutdown_application(bundle: ApplicationBundle) -> None:
    from quantis.plugins import PluginRegistry

    registry = PluginRegistry.instance()
    future = __import__("asyncio").run_coroutine_threadsafe(
        registry.unload_all(),
        bundle.async_bridge._loop,
    )
    try:
        future.result(timeout=3)
    except Exception:
        pass
    bundle.music.shutdown()
