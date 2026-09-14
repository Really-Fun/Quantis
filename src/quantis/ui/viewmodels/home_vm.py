from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from quantis.config.credentials import yandex_token
from quantis.controllers.playback_controller import PlaybackController
from quantis.core.async_bridge import AsyncBridge
from quantis.models import (
    DownloadPlaylist,
    LikedPlaylist,
    RecentlyPlayedPlaylist,
    Track,
    UserPlaylist,
    WavePlaylist,
)
from quantis.models.playlist import Playlist, RecommendationPlaylist
from quantis.services import MusicService, TrackHistoryService
from quantis.services.liked_tracks import LikedTracksService
from quantis.services.user_playlists import UserPlaylistsService
from quantis.ui.cover_prefetch import schedule_cover_prefetch
from quantis.ui.models import TrackListModel
from quantis.ui.viewmodels.base_viewmodel import BaseViewModel
from quantis.utils import get_asset_path

logger = logging.getLogger(__name__)


class _CountedShell(Playlist):
    """Карточка плейлиста без полного списка треков (треки берутся из модели при открытии)."""

    def __init__(
        self,
        name: str,
        *,
        count: int,
        cover_path: str | None,
        kind: str,
    ) -> None:
        super().__init__(name, (), cover_path)
        self._ui_count = count
        self.kind = kind

    def get_tracks(self) -> tuple[Track, ...]:
        return ()

    def __len__(self) -> int:
        return self._ui_count


@dataclass(frozen=True)
class HomeSnapshot:
    greeting: str
    quick_playlists: tuple[Playlist, ...]
    library_playlists: tuple[Playlist, ...]
    recommendation_tracks: tuple[Track, ...]
    recent_tracks: tuple[Track, ...]
    wave_ready: bool = False
    wave_track_count: int = 0
    wave_source: str = "yandex"


class HomeViewModel(BaseViewModel):
    home_changed = Signal()
    recent_changed = Signal()
    downloaded_changed = Signal()

    def __init__(
        self,
        history: TrackHistoryService,
        playback: PlaybackController,
        music: MusicService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._history = history
        self._playback = playback
        self._music = music or playback.music
        self._recent_model = TrackListModel()
        self._downloaded_model = TrackListModel()
        self._recommendation_model = TrackListModel()
        self._liked_model = TrackListModel()
        self._liked = LikedTracksService()
        self._user_playlists = UserPlaylistsService()
        self._snapshot = HomeSnapshot(
            greeting=_greeting_text(),
            quick_playlists=(),
            library_playlists=(),
            recommendation_tracks=(),
            recent_tracks=(),
        )
        self._recommendation_playlist: RecommendationPlaylist | None = None
        self._wave_playlist: WavePlaylist | None = None
        self._load_started = False
        self._bridge: AsyncBridge | None = None

    @property
    def recent_model(self) -> TrackListModel:
        return self._recent_model

    @property
    def downloaded_model(self) -> TrackListModel:
        return self._downloaded_model

    @property
    def recommendation_model(self) -> TrackListModel:
        return self._recommendation_model

    @property
    def liked_model(self) -> TrackListModel:
        return self._liked_model

    @property
    def snapshot(self) -> HomeSnapshot:
        return self._snapshot

    def request_load(self, bridge: AsyncBridge) -> None:
        if self._load_started:
            return
        self._load_started = True
        self._bridge = bridge
        from quantis.ui.async_ui import schedule

        schedule(self._load_async(), bridge)

    def refresh(self, bridge: AsyncBridge) -> None:
        self._bridge = bridge
        from quantis.ui.async_ui import schedule

        schedule(self._load_async(), bridge)

    async def _load_async(self) -> None:
        bridge = self._bridge
        if bridge is None:
            return
        bridge.invoke_main(lambda: self.set_loading(True))
        try:
            recent_task = self._history.get_recent_playlist(limit=24)
            liked_task = self._liked.get_playlist()
            downloaded_task = asyncio.to_thread(DownloadPlaylist.get_tracks_from_music_dir)
            playlists_task = self._user_playlists.load_all(include_empty=True)
            recent, liked, downloaded, user_playlists = await asyncio.gather(
                recent_task,
                liked_task,
                downloaded_task,
                playlists_task,
            )

            recent_tracks = list(recent.tracks.values) if recent else []
            liked_tracks = list(liked.tracks.values)
            snapshot = self._build_snapshot(
                recent_tracks=recent_tracks,
                liked_tracks=liked_tracks,
                downloaded=downloaded,
                user_playlists=user_playlists,
                recommendation_tracks=(),
                wave_playlist=None,
            )

            def apply_fast() -> None:
                self._snapshot = snapshot
                self._recent_model.set_tracks(recent_tracks)
                self._liked_model.set_tracks(liked_tracks)
                self._downloaded_model.set_tracks(list(downloaded))
                self.home_changed.emit()
                self.recent_changed.emit()
                self.downloaded_changed.emit()

            bridge.invoke_main(apply_fast)
            bridge.invoke_main(lambda: self.set_loading(False))
            schedule_cover_prefetch(
                recent_tracks + liked_tracks,
                self._music.downloader,
                bridge,
                on_done=lambda: self.recent_changed.emit(),
                limit=32,
            )

            recommendation_tracks, recommendation_playlist = (
                await self._load_recommendations(recent_tracks, liked_tracks)
            )
            wave_playlist = await self._load_wave()
            full_snapshot = self._build_snapshot(
                recent_tracks=recent_tracks,
                liked_tracks=liked_tracks,
                downloaded=downloaded,
                user_playlists=user_playlists,
                recommendation_tracks=tuple(recommendation_tracks),
                wave_playlist=wave_playlist,
            )

            def apply_recommendations() -> None:
                self._snapshot = full_snapshot
                self._recommendation_playlist = recommendation_playlist
                self._recommendation_model.set_tracks(list(recommendation_tracks))
                self._wave_playlist = wave_playlist
                self.home_changed.emit()

            bridge.invoke_main(apply_recommendations)
            schedule_cover_prefetch(
                recommendation_tracks,
                self._music.downloader,
                bridge,
                on_done=lambda: self.home_changed.emit(),
                limit=16,
            )
            if wave_playlist is not None:
                schedule_cover_prefetch(
                    list(wave_playlist.tracks.values),
                    self._music.downloader,
                    bridge,
                    on_done=lambda: self.home_changed.emit(),
                    limit=12,
                )
        except Exception as exc:
            logger.exception("Не удалось загрузить главную страницу")
            message = str(exc)
            bridge.invoke_main(lambda: self.emit_error(message))
        finally:
            bridge.invoke_main(lambda: self.set_loading(False))

    def _build_snapshot(
        self,
        *,
        recent_tracks: list[Track],
        liked_tracks: list[Track],
        downloaded: list[Track] | tuple[Track, ...],
        user_playlists: list[UserPlaylist],
        recommendation_tracks: tuple[Track, ...],
        wave_playlist: WavePlaylist | None = None,
    ) -> HomeSnapshot:
        library_playlists: list[Playlist] = []

        wave = wave_playlist or self._wave_playlist
        wave_count = len(wave) if wave is not None else 0
        # Карточка волны всегда первая, если есть токен (даже до загрузки — count 0).
        if yandex_token() or wave_count:
            library_playlists.append(
                _CountedShell(
                    "Моя волна",
                    count=wave_count,
                    cover_path=get_asset_path("assets/icons/radio.svg"),
                    kind="wave",
                )
            )

        rec_count = len(recommendation_tracks)
        if rec_count:
            library_playlists.append(
                _CountedShell(
                    "Рекомендации",
                    count=rec_count,
                    cover_path=get_asset_path("assets/icons/recomendation.svg"),
                    kind="recommendations",
                )
            )

        if recent_tracks:
            library_playlists.append(
                _CountedShell(
                    "Недавно прослушанные",
                    count=len(recent_tracks),
                    cover_path=RecentlyPlayedPlaylist().cover_path,
                    kind="recent",
                )
            )
        library_playlists.append(
            _CountedShell(
                "Любимые",
                count=len(liked_tracks),
                cover_path=LikedPlaylist().cover_path,
                kind="liked",
            )
        )
        downloaded_count = len(downloaded)
        if downloaded_count:
            library_playlists.append(
                _CountedShell(
                    "Скачанные",
                    count=downloaded_count,
                    cover_path=DownloadPlaylist().cover_path,
                    kind="downloaded",
                )
            )
        library_playlists.extend(user_playlists)
        quick = list(library_playlists[:6])
        return HomeSnapshot(
            greeting=_greeting_text(),
            quick_playlists=tuple(quick),
            library_playlists=tuple(library_playlists),
            recommendation_tracks=recommendation_tracks,
            recent_tracks=tuple(recent_tracks),
            wave_ready=bool(wave_count),
            wave_track_count=wave_count,
            wave_source=(wave.source if wave is not None else "yandex"),
        )

    async def refresh_recent(self, bridge: AsyncBridge) -> None:
        """Быстрое обновление недавних треков из БД (без сетевых запросов)."""
        self._bridge = bridge
        try:
            recent = await self._history.get_recent_playlist(limit=24)
            recent_tracks = list(recent.tracks.values) if recent else []
            snap = self._snapshot
            library_playlists: list[Playlist] = []
            if recent_tracks:
                library_playlists.append(
                    _CountedShell(
                        "Недавно прослушанные",
                        count=len(recent_tracks),
                        cover_path=RecentlyPlayedPlaylist().cover_path,
                        kind="recent",
                    )
                )
            for pl in snap.library_playlists:
                if isinstance(pl, _CountedShell) and pl.kind == "recent":
                    continue
                if isinstance(pl, RecentlyPlayedPlaylist):
                    continue
                library_playlists.append(pl)
            # Гарантируем shell «Любимые», если его ещё нет в снимке.
            if not any(
                isinstance(pl, _CountedShell) and pl.kind == "liked"
                for pl in library_playlists
            ):
                library_playlists.insert(
                    1 if recent_tracks else 0,
                    _CountedShell(
                        "Любимые",
                        count=len(self._liked_model.all_tracks()),
                        cover_path=LikedPlaylist().cover_path,
                        kind="liked",
                    ),
                )
            quick = list(library_playlists[:6])
            new_snap = HomeSnapshot(
                greeting=_greeting_text(),
                quick_playlists=tuple(quick),
                library_playlists=tuple(library_playlists),
                recommendation_tracks=snap.recommendation_tracks,
                recent_tracks=tuple(recent_tracks),
                wave_ready=snap.wave_ready,
                wave_track_count=snap.wave_track_count,
                wave_source=snap.wave_source,
            )

            def apply() -> None:
                self._snapshot = new_snap
                self._recent_model.set_tracks(recent_tracks)
                # Только recent_changed — без полной пересборки карточек главной.
                self.recent_changed.emit()

            bridge.invoke_main(apply)
        except Exception:
            logger.exception("Не удалось обновить недавние треки")

    async def _load_wave(self) -> WavePlaylist | None:
        if not yandex_token():
            return None
        try:
            return await self._music.wave.start_yandex_wave()
        except Exception:
            logger.exception("Не удалось загрузить Мою волну")
            return None

    async def ensure_wave(self) -> WavePlaylist | None:
        """Вернуть загруженную волну или запросить заново."""
        if self._wave_playlist is not None and len(self._wave_playlist):
            return self._wave_playlist
        playlist = await self._load_wave()
        if playlist is not None:
            self._wave_playlist = playlist

            def apply() -> None:
                snap = self._snapshot
                # Обновляем shell «Моя волна» в снимке.
                library: list[Playlist] = []
                wave_shell = _CountedShell(
                    "Моя волна",
                    count=len(playlist),
                    cover_path=get_asset_path("assets/icons/radio.svg"),
                    kind="wave",
                )
                replaced = False
                for pl in snap.library_playlists:
                    if isinstance(pl, _CountedShell) and pl.kind == "wave":
                        library.append(wave_shell)
                        replaced = True
                    else:
                        library.append(pl)
                if not replaced:
                    library.insert(0, wave_shell)
                self._snapshot = HomeSnapshot(
                    greeting=snap.greeting,
                    quick_playlists=tuple(library[:6]),
                    library_playlists=tuple(library),
                    recommendation_tracks=snap.recommendation_tracks,
                    recent_tracks=snap.recent_tracks,
                    wave_ready=True,
                    wave_track_count=len(playlist),
                    wave_source=playlist.source,
                )
                self.home_changed.emit()

            if self._bridge is not None:
                self._bridge.invoke_main(apply)
        return playlist

    async def _load_recommendations(
        self,
        recent_tracks: list[Track],
        liked_tracks: list[Track] | None = None,
    ) -> tuple[list[Track], RecommendationPlaylist | None]:
        seeds = _unique_seeds(recent_tracks, liked_tracks or [])
        try:
            playlist = await self._music.recommendation.generate_from_history(seeds)
        except Exception:
            logger.exception("Не удалось сгенерировать рекомендации")
            if not seeds:
                return [], None
            fallback = seeds[:5]
            return fallback, RecommendationPlaylist(
                name="Рекомендации",
                tracks=fallback,
                seeds=seeds,
                infinite=True,
            )
        tracks = list(playlist.tracks.values)
        return tracks, playlist

    async def play_track(self, track: Track) -> None:
        await self._playback.play_track(track)

    async def play_recent_at(self, index: int) -> None:
        playlist = RecentlyPlayedPlaylist(tracks=self._recent_model.all_tracks())
        await self.play_playlist(playlist, start_index=index)

    async def play_recommendation_at(self, index: int) -> None:
        playlist = self._recommendation_playlist
        if playlist is not None and len(playlist):
            await self.play_playlist(playlist, start_index=index)
            return
        await self._play_from_model(self._recommendation_model, index)

    async def play_downloaded_at(self, index: int) -> None:
        playlist = DownloadPlaylist(tracks=self._downloaded_model.all_tracks())
        await self.play_playlist(playlist, start_index=index)

    async def remove_downloaded_at(self, index: int) -> bool:
        track = self._downloaded_model.get_track(index)
        if track is None:
            return False
        try:
            victim = DownloadPlaylist(tracks=[track])
            await asyncio.to_thread(victim.delete_track, track)
        except Exception as exc:
            self.emit_error(str(exc))
            return False
        self._downloaded_model.remove_track(index)
        current = self._playback.playlist_manager.current_playlist
        if isinstance(current, DownloadPlaylist):
            current.tracks.remove(track)
        self.downloaded_changed.emit()
        if self._bridge is not None:
            self.refresh(self._bridge)
        return True

    async def play_playlist(self, playlist: Playlist, start_index: int = 0) -> None:
        playlist = self.resolve_playlist(playlist)
        tracks = list(playlist.tracks.values)
        if not tracks:
            return
        index = max(0, min(start_index, len(tracks) - 1))
        if isinstance(playlist, RecentlyPlayedPlaylist):
            working = RecentlyPlayedPlaylist(name=playlist.name, tracks=tracks)
        elif isinstance(playlist, LikedPlaylist):
            working = LikedPlaylist(name=playlist.name, tracks=tracks)
        elif isinstance(playlist, DownloadPlaylist):
            working = DownloadPlaylist(name=playlist.name, tracks=tracks)
        elif isinstance(playlist, UserPlaylist):
            working = UserPlaylist(playlist.name, tracks, playlist.cover_path)
        elif isinstance(playlist, WavePlaylist):
            working = WavePlaylist(
                playlist.name,
                tracks,
                playlist.cover_path,
                source=playlist.source,
                station=playlist.station,
                batch_id=playlist.batch_id,
            )
        elif isinstance(playlist, RecommendationPlaylist):
            working = playlist
        else:
            working = RecommendationPlaylist(playlist.name, tracks, playlist.cover_path)
        working.set_current_track(index)
        self._playback.playlist_manager.set_playlist(working)
        await self._playback.play_track(tracks[index])

    def resolve_playlist(self, playlist: Playlist) -> Playlist:
        """Подставляет треки из моделей для shell-карточек главной."""
        if isinstance(playlist, _CountedShell):
            if playlist.kind == "recent":
                return RecentlyPlayedPlaylist(tracks=self._recent_model.all_tracks())
            if playlist.kind == "liked":
                return LikedPlaylist(tracks=self._liked_model.all_tracks())
            if playlist.kind == "downloaded":
                return DownloadPlaylist(tracks=self._downloaded_model.all_tracks())
            if playlist.kind == "wave":
                if self._wave_playlist is not None and len(self._wave_playlist):
                    return self._wave_playlist
                return WavePlaylist(tracks=())
            if playlist.kind == "recommendations":
                if self._recommendation_playlist is not None:
                    return self._recommendation_playlist
                return RecommendationPlaylist(
                    tracks=self._recommendation_model.all_tracks()
                )
        return playlist

    async def open_wave(self) -> WavePlaylist | None:
        """Загрузить волну (если нужно) и вернуть готовый плейлист."""
        playlist = await self.ensure_wave()
        if playlist is None or not len(playlist):
            return None
        return playlist

    async def play_wave(self) -> None:
        playlist = await self.open_wave()
        if playlist is None:
            return
        await self.play_playlist(playlist, start_index=0)

    async def ensure_recommendations(self) -> RecommendationPlaylist | None:
        current = self._recommendation_playlist
        if current is not None and len(current):
            return current
        recent = list(self._recent_model.all_tracks())
        liked = list(self._liked_model.all_tracks())
        tracks, playlist = await self._load_recommendations(recent, liked)
        if playlist is None or not tracks:
            return None
        self._recommendation_playlist = playlist
        bridge = self._bridge
        if bridge is not None:

            def apply() -> None:
                snap = self._snapshot
                self._snapshot = HomeSnapshot(
                    greeting=snap.greeting,
                    quick_playlists=snap.quick_playlists,
                    library_playlists=_replace_shell_count(
                        snap.library_playlists,
                        "recommendations",
                        len(tracks),
                    ),
                    recommendation_tracks=tuple(tracks),
                    recent_tracks=snap.recent_tracks,
                    wave_ready=snap.wave_ready,
                    wave_track_count=snap.wave_track_count,
                    wave_source=snap.wave_source,
                )
                self._recommendation_model.set_tracks(tracks)
                self.home_changed.emit()

            bridge.invoke_main(apply)
            schedule_cover_prefetch(
                tracks,
                self._music.downloader,
                bridge,
                on_done=lambda: self.home_changed.emit(),
                limit=16,
            )
        return playlist

    async def open_recommendations(self) -> RecommendationPlaylist | None:
        return await self.ensure_recommendations()

    async def play_recommendations(self) -> None:
        playlist = await self.ensure_recommendations()
        if playlist is None:
            return
        await self.play_playlist(playlist, start_index=0)

    def apply_queue_extended(self, playlist) -> None:
        """Очередь рекомендаций выросла — обновить модель и карточку."""
        if not isinstance(playlist, RecommendationPlaylist):
            return
        owned = self._recommendation_playlist
        if owned is not None and playlist is not owned:
            return
        self._recommendation_playlist = playlist
        tracks = list(playlist.tracks.values)
        known = self._recommendation_model.all_tracks()
        if len(tracks) > len(known):
            self._recommendation_model.append_tracks(tracks[len(known) :])
        else:
            self._recommendation_model.set_tracks(tracks)
        snap = self._snapshot
        library = _replace_shell_count(
            snap.library_playlists, "recommendations", len(tracks)
        )
        self._snapshot = HomeSnapshot(
            greeting=snap.greeting,
            quick_playlists=tuple(list(library)[:6]),
            library_playlists=tuple(library),
            recommendation_tracks=tuple(tracks),
            recent_tracks=snap.recent_tracks,
            wave_ready=snap.wave_ready,
            wave_track_count=snap.wave_track_count,
            wave_source=snap.wave_source,
        )
        self.home_changed.emit()
        if self._bridge is not None:
            new_tracks = tracks[len(known) :]
            if new_tracks:
                schedule_cover_prefetch(
                    new_tracks,
                    self._music.downloader,
                    self._bridge,
                    on_done=lambda: self.home_changed.emit(),
                    limit=16,
                )

    async def refresh_liked(self, bridge: AsyncBridge | None = None) -> None:
        bridge = bridge or self._bridge
        if bridge is None:
            return
        liked = await self._liked.get_playlist()
        liked_tracks = list(liked.tracks.values)

        def apply() -> None:
            self._liked_model.set_tracks(liked_tracks)
            snap = self._snapshot
            library: list[Playlist] = []
            for pl in snap.library_playlists:
                if isinstance(pl, _CountedShell) and pl.kind == "liked":
                    library.append(
                        _CountedShell(
                            "Любимые",
                            count=len(liked_tracks),
                            cover_path=LikedPlaylist().cover_path,
                            kind="liked",
                        )
                    )
                else:
                    library.append(pl)
            if not any(
                isinstance(pl, _CountedShell) and pl.kind == "liked" for pl in library
            ):
                library.insert(
                    1,
                    _CountedShell(
                        "Любимые",
                        count=len(liked_tracks),
                        cover_path=LikedPlaylist().cover_path,
                        kind="liked",
                    ),
                )
            self._snapshot = HomeSnapshot(
                greeting=snap.greeting,
                quick_playlists=tuple(library[:6]),
                library_playlists=tuple(library),
                recommendation_tracks=snap.recommendation_tracks,
                recent_tracks=snap.recent_tracks,
                wave_ready=snap.wave_ready,
                wave_track_count=snap.wave_track_count,
                wave_source=snap.wave_source,
            )
            self.home_changed.emit()

        bridge.invoke_main(apply)

    async def refresh_user_playlists(self, bridge: AsyncBridge | None = None) -> None:
        bridge = bridge or self._bridge
        if bridge is None:
            return
        self.refresh(bridge)

    async def create_user_playlist(self, name: str) -> None:
        await self._user_playlists.create(name)
        if self._bridge is not None:
            self.refresh(self._bridge)

    async def add_track_to_user_playlist(self, playlist_name: str, track: Track) -> bool:
        added = await self._user_playlists.add_track(playlist_name, track)
        if self._bridge is not None:
            self.refresh(self._bridge)
        return added

    async def _play_from_model(self, model: TrackListModel, index: int) -> None:
        track = model.get_track(index)
        if track is None:
            return
        tracks = model.all_tracks()
        playlist = RecommendationPlaylist(name="Главная", tracks=tracks)
        playlist.set_current_track(index)
        self._playback.playlist_manager.set_playlist(playlist)
        await self._playback.play_track(track)

    def refresh_downloaded(self, bridge: AsyncBridge) -> None:
        self._bridge = bridge
        from quantis.ui.async_ui import schedule

        schedule(self._refresh_downloaded_async(), bridge)

    async def _refresh_downloaded_async(self) -> None:
        bridge = self._bridge
        if bridge is None:
            return
        downloaded = await asyncio.to_thread(DownloadPlaylist.get_tracks_from_music_dir)

        def apply() -> None:
            self._downloaded_model.set_tracks(list(downloaded))
            self.downloaded_changed.emit()

        bridge.invoke_main(apply)
        self.refresh(bridge)

    async def download_recent_at(self, index: int) -> None:
        track = self._recent_model.get_track(index)
        if track is None or track.downloaded:
            return
        bridge = self._bridge
        if bridge is None:
            return
        downloader = self._playback.music.downloader
        bridge.invoke_main(lambda: self.set_loading(True))
        try:
            await downloader.download_track(track)
            await downloader.download_cover(track)
            track.downloaded = True

            def refresh() -> None:
                model_index = self._recent_model.index(index)
                self._recent_model.dataChanged.emit(model_index, model_index, [])
                self.downloaded_changed.emit()

            bridge.invoke_main(refresh)
            self.refresh_downloaded(bridge)
        except Exception as exc:
            logger.exception("Ошибка скачивания")
            message = str(exc)
            bridge.invoke_main(lambda: self.emit_error(message))
        finally:
            bridge.invoke_main(lambda: self.set_loading(False))


def _greeting_text() -> str:
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Доброе утро"
    if 12 <= hour < 18:
        return "Добрый день"
    if 18 <= hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def _unique_seeds(*groups: list[Track]) -> list[Track]:
    seen: set[tuple[str, str]] = set()
    seeds: list[Track] = []
    for group in groups:
        for track in group:
            key = (str(track.source), str(track.track_id))
            if key in seen:
                continue
            seen.add(key)
            seeds.append(track)
    return seeds


def _replace_shell_count(
    playlists: tuple[Playlist, ...] | list[Playlist],
    kind: str,
    count: int,
) -> list[Playlist]:
    updated: list[Playlist] = []
    found = False
    for playlist in playlists:
        if isinstance(playlist, _CountedShell) and playlist.kind == kind:
            found = True
            updated.append(
                _CountedShell(
                    playlist.name,
                    count=count,
                    cover_path=playlist.cover_path,
                    kind=kind,
                )
            )
        else:
            updated.append(playlist)
    if not found and count and kind == "recommendations":
        insert_at = 1 if updated and getattr(updated[0], "kind", None) == "wave" else 0
        updated.insert(
            insert_at,
            _CountedShell(
                "Рекомендации",
                count=count,
                cover_path=get_asset_path("assets/icons/recomendation.svg"),
                kind=kind,
            ),
        )
    return updated
