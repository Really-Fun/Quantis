from __future__ import annotations

import asyncio
import logging

from PySide6.QtCore import QObject, QTimer, Signal

from quantis.controllers.playback_controller import PlaybackController
from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.models.playlist import RecommendationPlaylist
from quantis.services.async_finder import AsyncFinder
from quantis.ui.models import TrackListModel
from quantis.ui.viewmodels.base_viewmodel import BaseViewModel

logger = logging.getLogger(__name__)

_SOURCE_FILTERS = ("all", "yandex", "youtube", "soundcloud")
_SOURCE_LABELS = {
    "yandex": "Yandex",
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
}


def _has_yandex_token() -> bool:
    try:
        from quantis.config.credentials import yandex_token

        return bool(yandex_token())
    except Exception:
        return False


class SearchViewModel(BaseViewModel):
    results_changed = Signal()
    download_finished = Signal()
    status_message = Signal(str)

    def __init__(
        self,
        finder: AsyncFinder,
        playback: PlaybackController,
        bridge: AsyncBridge,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._finder = finder
        self._playback = playback
        self._bridge = bridge
        self._model = TrackListModel(parent=self)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._run_search)
        self._pending_query = ""
        self._search_generation = 0
        self._inflight_searches = 0
        self._all_tracks: list[Track] = []
        self._source_filter = "all"  # all | yandex | youtube | soundcloud

    @property
    def model(self) -> TrackListModel:
        return self._model

    def search(self, query: str) -> None:
        self._pending_query = query.strip()
        if not self._pending_query:
            self._debounce.stop()
            self._all_tracks = []
            self._model.set_tracks([])
            self.results_changed.emit()
            return
        self._debounce.start()

    def clear_results(self) -> None:
        """Освобождает результаты поиска при уходе со страницы."""
        self._debounce.stop()
        self._pending_query = ""
        self._search_generation += 1
        self._all_tracks = []
        self._model.clear()
        self.set_loading(False)
        self.results_changed.emit()

    def set_source_filter(self, source: str) -> None:
        key = (source or "all").lower()
        if key not in _SOURCE_FILTERS:
            key = "all"
        if self._source_filter == key:
            return
        self._source_filter = key
        self._apply_filter()

    @property
    def source_filter(self) -> str:
        return self._source_filter

    def _filtered_tracks(self) -> list[Track]:
        if self._source_filter == "all":
            return list(self._all_tracks)
        return [
            t for t in self._all_tracks if str(t.source).lower() == self._source_filter
        ]

    def _apply_filter(self) -> None:
        filtered = self._filtered_tracks()
        self._model.set_tracks(filtered)
        self.results_changed.emit()
        if self._all_tracks:
            counts = {
                name: sum(1 for t in self._all_tracks if str(t.source).lower() == name)
                for name in _SOURCE_LABELS
            }
            shown = len(filtered)
            if self._source_filter == "all":
                parts = ", ".join(
                    f"{label}: {counts[name]}" for name, label in _SOURCE_LABELS.items()
                )
                self.status_message.emit(f"Найдено: {shown} ({parts})")
            else:
                label = _SOURCE_LABELS.get(self._source_filter, self._source_filter)
                self.status_message.emit(f"{label}: {shown} из {len(self._all_tracks)}")

    def search_now(self) -> None:
        self._debounce.stop()
        self._run_search()

    def _run_search(self) -> None:
        query = self._pending_query.strip()
        if not query:
            self._model.set_tracks([])
            self.results_changed.emit()
            return

        from quantis.ui.async_ui import schedule

        self._search_generation += 1
        generation = self._search_generation
        self._inflight_searches += 1
        self.set_loading(True)
        schedule(self._search_async(query, generation), self._bridge)

    async def _search_async(self, query: str, generation: int) -> None:
        bridge = self._bridge
        try:
            logger.info("Поиск: %s", query)
            from quantis.services.url_resolver import parse_track_id

            if parse_track_id(query) is not None:
                tracks = await self._finder.resolve_tracks(url=query)
                if generation != self._search_generation:
                    return

                snapshot = list(tracks)
                status = f"Найдено: {len(snapshot)}" if snapshot else ""

                def apply_url(
                    items: list[Track] = snapshot,
                    message: str = status,
                ) -> None:
                    self._all_tracks = items
                    self._model.set_tracks(self._filtered_tracks())
                    self.results_changed.emit()
                    if message:
                        self.status_message.emit(message)
                    elif not items:
                        self.status_message.emit("По ссылке ничего не найдено.")

                bridge.invoke_main(apply_url)
                logger.info("Найдено треков: %d", len(tracks))
                return

            tracks: list[Track] = []
            counts = {name: 0 for name in _SOURCE_LABELS}
            done_sources: set[str] = set()
            has_yandex = _has_yandex_token()

            async for source, batch in self._finder.iter_track_batches(query):
                if generation != self._search_generation:
                    return

                tracks.extend(batch)
                if source in counts:
                    counts[source] = len(batch)
                done_sources.add(source)

                snapshot = list(tracks)
                pending = [
                    _SOURCE_LABELS[name]
                    for name in AsyncFinder.SEARCH_SOURCES
                    if name not in done_sources and (name != "yandex" or has_yandex)
                ]
                if pending:
                    label = _SOURCE_LABELS.get(source, source)
                    if source == "yandex" and not has_yandex:
                        status = f"Ищем {' и '.join(pending)}…"
                    else:
                        status = (
                            f"{label}: {counts.get(source, 0)} — "
                            f"ищем {' и '.join(pending)}…"
                        )
                elif snapshot:
                    parts = ", ".join(
                        f"{label}: {counts[name]}"
                        for name, label in _SOURCE_LABELS.items()
                    )
                    status = f"Найдено: {len(snapshot)} ({parts})"
                else:
                    status = ""

                def apply(
                    items: list[Track] = snapshot,
                    message: str = status,
                ) -> None:
                    self._all_tracks = items
                    self._model.set_tracks(self._filtered_tracks())
                    self.results_changed.emit()
                    if message:
                        self.status_message.emit(message)

                bridge.invoke_main(apply)

            if generation != self._search_generation:
                return
            logger.info("Найдено треков: %d", len(tracks))

            if not tracks:

                def show_empty() -> None:
                    hint = "Ничего не найдено. Попробуйте другой запрос."
                    if not _has_yandex_token():
                        hint += (
                            " Токен Yandex в Настройках добавит выдачу Яндекс.Музыки."
                        )
                    self.status_message.emit(hint)

                bridge.invoke_main(show_empty)
        except (GeneratorExit, asyncio.CancelledError):
            raise
        except Exception as exc:
            logger.exception("Ошибка поиска")
            if generation == self._search_generation:
                message = str(exc)

                def show_err() -> None:
                    self.emit_error(message)

                bridge.invoke_main(show_err)
        finally:

            def finish() -> None:
                self._inflight_searches = max(0, self._inflight_searches - 1)
                if self._inflight_searches == 0:
                    self.set_loading(False)

            bridge.invoke_main(finish)

    def _tracks_snapshot(self) -> list[Track]:
        return self._filtered_tracks()

    async def play_track(self, track: Track) -> None:
        tracks = self._tracks_snapshot()
        if not tracks:
            await self._playback.play_track(track)
            return
        try:
            index = tracks.index(track)
        except ValueError:
            index = 0
            tracks = [track]
        playlist = RecommendationPlaylist(name="Поиск", tracks=tracks)
        playlist.set_current_track(index)
        self._playback.playlist_manager.set_playlist(playlist)
        await self._playback.play_track(track)

    async def play_track_at(self, index: int) -> None:
        track = self._model.get_track(index)
        if track is not None:
            await self.play_track(track)

    async def download_track_at(self, index: int) -> None:
        track = self._model.get_track(index)
        if track is None or track.downloaded:
            return
        bridge = self._bridge
        downloader = self._playback.music.downloader
        bridge.invoke_main(lambda: self.set_loading(True))
        try:
            await downloader.download_track(track)
            await downloader.download_cover(track)
            track.downloaded = True

            def refresh() -> None:
                model_index = self._model.index(index)
                self._model.dataChanged.emit(model_index, model_index, [])
                self.download_finished.emit()

            bridge.invoke_main(refresh)
        except Exception as exc:
            logger.exception("Ошибка скачивания")
            message = str(exc)
            bridge.invoke_main(lambda: self.emit_error(message))
        finally:
            bridge.invoke_main(lambda: self.set_loading(False))

    async def search_advanced(
        self,
        url: str = "",
        track_id: str = "",
        source: str = "",
    ) -> None:
        """Расширенный поиск: по прямой ссылке или ID трека из источника.

        Использует отдельный метод AsyncFinder.resolve_track(), в отличие
        от обычного текстового поиска через iter_track_batches().
        """
        url = (url or "").strip()
        track_id = (track_id or "").strip()
        source = (source or "").strip().lower()

        if not url and not track_id:
            self.status_message.emit("Укажите ссылку или ID трека.")
            return

        bridge = self._bridge
        self._debounce.stop()
        self._search_generation += 1
        generation = self._search_generation
        self._inflight_searches += 1
        bridge.invoke_main(lambda: self.set_loading(True))

        try:
            logger.info(
                "Расширенный поиск: url=%r id=%r source=%r", url, track_id, source
            )
            bridge.invoke_main(lambda: self.status_message.emit("Определяем трек…"))

            tracks = await self._finder.resolve_tracks(
                url=url or None,
                track_id=track_id or None,
                source=source or None,
            )

            if generation != self._search_generation:
                return

            def apply(items: list[Track] = tracks) -> None:
                self._all_tracks = items
                self._model.set_tracks(self._filtered_tracks())
                self.results_changed.emit()
                if items:
                    self.status_message.emit(f"Найдено: {len(items)}")
                else:
                    self.status_message.emit("По ссылке ничего не найдено.")

            bridge.invoke_main(apply)

        except (GeneratorExit, asyncio.CancelledError):
            raise
        except Exception as exc:
            logger.exception("Ошибка расширенного поиска")
            if generation == self._search_generation:
                message = str(exc)
                bridge.invoke_main(lambda: self.emit_error(message))
        finally:

            def finish() -> None:
                self._inflight_searches = max(0, self._inflight_searches - 1)
                if self._inflight_searches == 0:
                    self.set_loading(False)

            bridge.invoke_main(finish)
