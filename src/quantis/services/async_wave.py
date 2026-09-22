"""Моя волна — персональное радио Yandex (rotor), по примеру MarshalX Radio."""

from __future__ import annotations

import logging
import random
from typing import Any

from quantis.config.clients import Clients
from quantis.config.credentials import yandex_token
from quantis.models import Track, YandexTrack
from quantis.models.playlist import WavePlaylist
from quantis.services.yandex_finder import yandex_track_from_api

logger = logging.getLogger(__name__)

YANDEX_USER_WAVE_STATION = "user:onyourwave"
_WAVE_FROM = "mobile-home-quantis-wave"
_PLAY_FROM = "desktop_win-home-wave-default"


class AsyncWaveService:
    """Сессия «Моя волна» с feedback как в examples/radio_example/radio.py."""

    def __init__(self) -> None:
        self._station_id = YANDEX_USER_WAVE_STATION
        self._station_from = _WAVE_FROM
        self._batch_id: str | None = None
        self._play_id: str | None = None
        self._album_ids: dict[str, int] = {}
        self._durations_ms: dict[str, int] = {}

    async def start_yandex_wave(self) -> WavePlaylist | None:
        if not yandex_token():
            logger.info("Моя волна: нет токена Yandex")
            return None
        client = Clients().get_yandex_client()
        if client is None:
            logger.warning("Моя волна: клиент Yandex недоступен")
            return None

        result = await self._fetch_batch(client, queue=None)
        if result is None:
            return None
        tracks = self._tracks_from_sequence(getattr(result, "sequence", None))
        if not tracks:
            logger.warning("Моя волна: пустая последовательность треков")
            return None

        self._batch_id = getattr(result, "batch_id", None)
        await self._send_radio_started(client, self._batch_id)

        playlist = WavePlaylist(
            name="Моя волна",
            tracks=tracks,
            source="yandex",
            station=self._station_id,
            batch_id=self._batch_id,
        )
        playlist.set_current_track(0)
        return playlist

    async def notify_track_started(
        self, track: Track, playlist: WavePlaylist | None = None
    ) -> None:
        client = Clients().get_yandex_client()
        if client is None or not yandex_token():
            return
        batch_id = (playlist.batch_id if playlist else None) or self._batch_id
        self._play_id = self._generate_play_id()
        try:
            await self._send_play_start_track(client, track)
            await client.rotor_station_feedback_track_started(
                station=self._station_id,
                track_id=track.track_id,
                batch_id=batch_id,
            )
        except Exception:
            logger.debug("Моя волна: trackStarted feedback", exc_info=True)

    async def continue_after_finish(
        self,
        playlist: WavePlaylist,
        finished: Track,
        *,
        played_seconds: float,
    ) -> Track | None:
        """Feedback о конце трека + следующий трек (с подгрузкой батча при необходимости).

        Как MarshalX ``Radio.play_next``.
        """
        client = Clients().get_yandex_client()
        if client is None or not yandex_token():
            # Без API — просто следующий в уже загруженном списке
            return self._linear_next(playlist)

        batch_id = playlist.batch_id or self._batch_id
        try:
            await self._send_play_end_track(client, finished, played_seconds)
            await client.rotor_station_feedback_track_finished(
                station=self._station_id,
                track_id=finished.track_id,
                total_played_seconds=played_seconds,
                batch_id=batch_id,
            )
        except Exception:
            logger.debug("Моя волна: trackFinished feedback", exc_info=True)

        idx = playlist.tracks._index
        if idx + 1 >= len(playlist):
            result = await self._fetch_batch(client, queue=finished.track_id)
            if result is not None:
                more = self._tracks_from_sequence(getattr(result, "sequence", None))
                new_batch = getattr(result, "batch_id", None)
                if new_batch:
                    self._batch_id = new_batch
                    playlist.batch_id = new_batch
                    await self._send_radio_started(client, new_batch)
                added = playlist.append_tracks(more)
                logger.info("Моя волна: подгружено ещё %s треков", added)

        nxt = self._linear_next(playlist)
        if nxt is not None:
            await self.notify_track_started(nxt, playlist)
        return nxt

    async def fetch_more_yandex(
        self,
        *,
        queue_track_id: str | int,
        batch_id: str | None = None,
    ) -> list[YandexTrack]:
        client = Clients().get_yandex_client()
        if client is None or not yandex_token():
            return []
        result = await self._fetch_batch(client, queue=queue_track_id)
        if result is None:
            return []
        new_batch = getattr(result, "batch_id", None)
        if new_batch:
            self._batch_id = new_batch
        return self._tracks_from_sequence(getattr(result, "sequence", None))

    async def _fetch_batch(self, client, queue: str | int | None):
        try:
            return await client.rotor_station_tracks(
                self._station_id,
                settings2=True,
                queue=queue,
            )
        except Exception:
            logger.exception("Моя волна: не удалось получить треки станции")
            return None

    async def _send_radio_started(self, client, batch_id: str | None) -> None:
        try:
            await client.rotor_station_feedback_radio_started(
                station=self._station_id,
                from_=self._station_from,
                batch_id=batch_id,
            )
        except Exception:
            logger.debug("Моя волна: radioStarted feedback", exc_info=True)

    def _duration_seconds(self, track: Track) -> float:
        ms = self._durations_ms.get(str(track.track_id))
        if not ms:
            ms = int(getattr(track, "duration_ms", 0) or 0)
        if ms and ms > 0:
            return float(ms) / 1000.0
        return 0.0

    async def _send_play_start_track(self, client, track: Track) -> None:
        album_id = await self._album_id_for(client, track)
        total_seconds = self._duration_seconds(track)
        try:
            # Как в MarshalX Radio.__send_play_start_track
            await client.play_audio(
                from_=_PLAY_FROM,
                track_id=track.track_id,
                album_id=album_id,
                play_id=self._play_id,
                track_length_seconds=0,
                total_played_seconds=0,
                end_position_seconds=total_seconds,
            )
        except Exception:
            logger.debug("Моя волна: play_audio start", exc_info=True)

    async def _send_play_end_track(
        self, client, track: Track, played_seconds: float
    ) -> None:
        album_id = await self._album_id_for(client, track)
        total_seconds = self._duration_seconds(track) or max(played_seconds, 1.0)
        try:
            # Как в MarshalX Radio.__send_play_end_track
            await client.play_audio(
                from_=_PLAY_FROM,
                track_id=track.track_id,
                album_id=album_id,
                play_id=self._play_id,
                track_length_seconds=int(total_seconds),
                total_played_seconds=played_seconds,
                end_position_seconds=total_seconds,
            )
        except Exception:
            logger.debug("Моя волна: play_audio end", exc_info=True)

    async def _album_id_for(self, client, track: Track) -> int:
        key = str(track.track_id)
        if key in self._album_ids:
            return self._album_ids[key]
        try:
            infos = await client.tracks(int(track.track_id))
            if infos:
                info = infos[0]
                dur = getattr(info, "duration_ms", None)
                if dur:
                    self._durations_ms[key] = int(dur)
                albums = getattr(info, "albums", None) or []
                if albums:
                    album_id = int(albums[0].id)
                    self._album_ids[key] = album_id
                    return album_id
        except Exception:
            logger.debug("Моя волна: album_id", exc_info=True)
        return 0

    @staticmethod
    def _linear_next(playlist: WavePlaylist) -> Track | None:
        idx = playlist.tracks._index
        if idx + 1 >= len(playlist):
            return None
        playlist.set_current_track(idx + 1)
        return playlist.get_current_track()

    @staticmethod
    def _generate_play_id() -> str:
        return f"{int(random.random() * 1000)}-{int(random.random() * 1000)}-{int(random.random() * 1000)}"

    def _tracks_from_sequence(self, sequence: Any) -> list[YandexTrack]:
        if not sequence:
            return []
        tracks: list[YandexTrack] = []
        for item in sequence:
            track = getattr(item, "track", None)
            if track is None:
                continue
            try:
                yt = yandex_track_from_api(track)
                tracks.append(yt)
                key = str(yt.track_id)
                albums = getattr(track, "albums", None) or []
                if albums:
                    self._album_ids[key] = int(albums[0].id)
                dur = getattr(track, "duration_ms", None)
                if dur:
                    self._durations_ms[key] = int(dur)
            except Exception:
                logger.debug("Моя волна: пропуск трека в sequence", exc_info=True)
        return tracks
