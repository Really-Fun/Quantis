from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QImage, QImageReader
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QHBoxLayout, QWidget

from quantis.services.wallpaper_policy import (
    WALLPAPER_DEFAULT_FPS,
    wallpaper_can_apply_seek,
    wallpaper_decode_max_side,
    wallpaper_seek_target,
)
from quantis.services.wallpaper_sync import VideoState
from quantis.ui.themes import registry
from quantis.ui.themes.spec import ThemeSpec
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor
from quantis.ui.views.widgets.cover_art import load_wallpaper_pixmap

logger = logging.getLogger(__name__)

_WALLPAPER_MAX_SIDE = 1280
_SEEKABLE_STATUSES = (
    QMediaPlayer.MediaStatus.LoadedMedia,
    QMediaPlayer.MediaStatus.BufferingMedia,
    QMediaPlayer.MediaStatus.BufferedMedia,
)
# BufferingMedia у Qt значит «данных хватает, докачиваем» — это не остановка.
_STALLED_STATUSES = (
    QMediaPlayer.MediaStatus.LoadingMedia,
    QMediaPlayer.MediaStatus.StalledMedia,
)
# EndOfMedia дальше этой отметки от конца — обрыв потока, а не конец клипа.
_TRUE_END_SLOP_MS = 1500


def _media_url(url: str) -> QUrl:
    if url.startswith(("http://", "https://")):
        return QUrl(url)
    return QUrl.fromLocalFile(url)


class _VideoFeed(QObject):
    """Кадры видео через QVideoSink → компоновщик фона (сам ничего не рисует)."""

    def __init__(self, compositor: BackdropCompositor, parent: QObject | None = None):
        super().__init__(parent)
        self._compositor = compositor
        self._sink = QVideoSink(self)
        self._source = QImage()
        self._last_frame_at = 0.0
        self._min_interval = 1.0 / WALLPAPER_DEFAULT_FPS
        self._max_side = wallpaper_decode_max_side(360)
        self._sink.videoFrameChanged.connect(self._on_frame)

    @property
    def sink(self) -> QVideoSink:
        return self._sink

    @property
    def max_side(self) -> int:
        return self._max_side

    @property
    def fps(self) -> float:
        return 1.0 / self._min_interval

    def is_empty(self) -> bool:
        return self._source.isNull()

    def set_limits(self, *, fps: int, max_side: int) -> None:
        self._min_interval = 1.0 / max(1, int(fps))
        self._max_side = max(320, int(max_side))

    def clear(self) -> None:
        self._source = QImage()
        self._last_frame_at = 0.0
        self._compositor.set_video_frame(None)

    def set_still(self, image: QImage) -> None:
        if image.isNull():
            return
        self._last_frame_at = 0.0
        self._push(image)

    def _on_frame(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
        now = monotonic()
        if now - self._last_frame_at < self._min_interval:
            return
        self._last_frame_at = now

        if not frame.map(QVideoFrame.MapMode.ReadOnly):
            return
        try:
            image = frame.toImage()
        finally:
            frame.unmap()

        if not image.isNull():
            self._push(image)

    def _push(self, image: QImage) -> None:
        self._source = self._compact_frame(image)
        self._compositor.set_video_frame(self._source)

    def _compact_frame(self, image: QImage) -> QImage:
        """Даунскейл + RGB32: отцепляемся от буфера кадра, без альфы."""
        if image.isNull():
            return image
        downscaled = max(image.width(), image.height()) > self._max_side
        if downscaled:
            image = image.scaled(
                self._max_side,
                self._max_side,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        if image.format() != QImage.Format.Format_RGB32:
            return image.convertToFormat(QImage.Format.Format_RGB32)
        return image if downscaled else image.copy()


class WallpaperBackdrop(QWidget):
    """Источник обоев: статичный jpg или видео-клип. Сам не рисует — картинку и
    кадры отдаёт ``BackdropCompositor``, а тот рисует фон под всем окном.

    Видео здесь только исполняет команды: когда и куда перематывать, решает
    ``WallpaperSync`` в контроллере.
    """

    stream_stalled = Signal()
    # Длительность известна — можно перематывать и синхронизировать.
    media_ready = Signal()

    def __init__(
        self,
        wallpaper: str | Path | None = None,
        theme: ThemeSpec | None = None,
        parent: QWidget | None = None,
        compositor: BackdropCompositor | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("wallpaperBackdrop")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()
        self._theme = theme or registry.default()
        self._compositor = compositor or BackdropCompositor(self._theme, self)
        self._wallpaper_path: str | None = str(wallpaper) if wallpaper else None
        self._dynamic_enabled = False
        self._file_loop: str | None = None
        self._wallpaper_loaded = False
        self._video_active = False
        self._streaming = False
        self._current_source: str | None = None
        self._loop_enabled = False
        self._stall_notified = False
        self._host_player: QMediaPlayer | None = None

        self._video_feed = _VideoFeed(self._compositor, self)

        self._video_player: QMediaPlayer | None = None
        self._video_audio: QAudioOutput | None = None

        if self._wallpaper_path:
            self._load_wallpaper()

    @property
    def compositor(self) -> BackdropCompositor:
        return self._compositor

    def _silence_video_audio(self) -> None:
        if self._video_audio is None:
            return
        self._video_audio.setMuted(True)
        self._video_audio.setVolume(0.0)

    def _ensure_video_player(self) -> QMediaPlayer:
        if self._video_player is None:
            self._video_player = QMediaPlayer(self)
            self._video_audio = QAudioOutput(self)
            self._silence_video_audio()
            self._video_player.setAudioOutput(self._video_audio)
            self._video_player.setVideoSink(self._video_feed.sink)
            self._video_player.mediaStatusChanged.connect(self._on_video_status)
            self._video_player.durationChanged.connect(self._on_duration_ready)
            self._video_player.errorOccurred.connect(self._on_video_error)
        elif self._host_player is None:
            self._video_player.setVideoSink(self._video_feed.sink)
        return self._video_player

    def is_following_audio_player(self) -> bool:
        return self._host_player is not None

    def follow_media_player(self, player: QMediaPlayer | None) -> None:
        """Кадры с плеера трека: без второго googlevideo и без рассинхрона."""
        if not self._dynamic_enabled:
            return
        if player is self._host_player and player is not None:
            self._set_video_active(True)
            return
        self._detach_host()
        if self._video_player is not None:
            self._video_player.stop()
            self._video_player.setVideoSink(None)
            self._video_player.setSource(QUrl())
        if player is None:
            return
        self._host_player = player
        self._loop_enabled = False
        self._streaming = False
        self._stall_notified = False
        self._current_source = "host-player"
        player.setVideoSink(self._video_feed.sink)
        self._set_video_active(True)

    def _detach_host(self) -> None:
        if self._host_player is None:
            return
        self._host_player.setVideoSink(None)
        self._host_player = None

    def _set_video_active(self, active: bool) -> None:
        self._video_active = active
        self._compositor.set_video_active(active)

    def set_theme(self, theme: ThemeSpec) -> None:
        if self._theme is not theme:
            self._theme = theme
            self._compositor.set_theme(theme)

    def set_wallpaper(self, path: str | Path | None) -> None:
        new_path = str(path) if path else None
        if new_path == self._wallpaper_path and self._wallpaper_loaded:
            return
        self._wallpaper_path = new_path
        self._load_wallpaper()

    def _load_wallpaper(self) -> None:
        image = QImage()
        if self._wallpaper_path:
            pixmap = load_wallpaper_pixmap(self._wallpaper_path, _WALLPAPER_MAX_SIDE)
            if not pixmap.isNull():
                image = pixmap.toImage()
        self._wallpaper_loaded = not image.isNull()
        self._compositor.set_wallpaper(image)

    def set_dynamic_wallpaper_enabled(self, enabled: bool) -> None:
        self._dynamic_enabled = enabled
        if not enabled and self._file_loop is None:
            self.stop_video()

    def play_file_loop(self, path: str) -> None:
        """Свой видеофайл фоном: по кругу, без звука и без синхронизации с
        треком. Клипы треков в это время выключены, контроллер его не трогает."""
        if not path or (path == self._file_loop and self._video_active):
            return
        self._file_loop = path
        self._detach_host()
        self._loop_enabled = True
        self._streaming = False  # синхронизатору трека этот плеер не отдаём
        self._stall_notified = False
        self._set_video_active(True)
        player = self._ensure_video_player()
        self._current_source = path
        self._silence_video_audio()
        player.setPlaybackRate(1.0)
        player.setSource(_media_url(path))
        player.play()

    def stop_file_loop(self) -> None:
        if self._file_loop is not None:
            self._file_loop = None
            self.stop_video()

    def set_file_loop_paused(self, paused: bool) -> None:
        """Эко-режим: свой клип стоит, как и клипы треков."""
        if self._file_loop is None or self._video_player is None:
            return
        if paused:
            self._video_player.pause()
        else:
            self._video_player.play()

    def set_video_limits(self, *, fps: int, max_side: int) -> None:
        self._video_feed.set_limits(fps=fps, max_side=max_side)
        self._compositor.set_video_fps(fps)

    def set_cinematic(self, enabled: bool) -> None:
        self._compositor.set_cinematic(enabled)

    def play_video_url(
        self, url: str, *, loop: bool = False, autoplay: bool = False
    ) -> None:
        """Грузит видео. Без autoplay стоит на паузе, пока синхронизатор не
        перемотает его к позиции звука — первый кадр сразу совпадает с треком."""
        if not self._dynamic_enabled or not url:
            return
        self._detach_host()
        self._loop_enabled = loop
        self._stall_notified = False
        self._streaming = True
        self._set_video_active(True)
        player = self._ensure_video_player()
        if url == self._current_source and player.playbackState() in (
            QMediaPlayer.PlaybackState.PlayingState,
            QMediaPlayer.PlaybackState.PausedState,
        ):
            if autoplay:
                player.play()
            return
        self._current_source = url
        self._silence_video_audio()
        player.setPlaybackRate(1.0)
        player.setSource(_media_url(url))
        if autoplay:
            player.play()
        else:
            player.pause()

    def show_still(self, path: str) -> None:
        """Обложка вместо клипа (грузится или не нашёлся): компоновщик рисует её
        размытой и дрейфующей, как режим «Обложка», а не резким кадром."""
        if not self._dynamic_enabled or not path:
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        original = reader.size()
        max_side = self._video_feed.max_side
        if original.isValid():
            w, h = original.width(), original.height()
            longest = max(w, h)
            if longest > max_side:
                scale = max_side / longest
                reader.setScaledSize(
                    QSize(max(1, int(w * scale)), max(1, int(h * scale)))
                )
        image = reader.read()
        if image.isNull():
            return
        self._loop_enabled = False
        self._streaming = False
        self._stall_notified = False
        self._current_source = path
        if self._video_player is not None:
            self._video_player.stop()
            self._video_player.setSource(QUrl())
        self._video_feed.clear()
        self._compositor.set_cover(image)
        self._set_video_active(True)

    def has_picture(self) -> bool:
        return self._video_active and not self._video_feed.is_empty()

    def is_video_playing(self) -> bool:
        if self._host_player is not None:
            return self._video_active
        if self._video_player is None:
            return False
        return self._video_active and self._video_player.playbackState() in (
            QMediaPlayer.PlaybackState.PlayingState,
            QMediaPlayer.PlaybackState.PausedState,
        )

    def current_video_url(self) -> str | None:
        return self._current_source if self._streaming else None

    def video_state(self) -> VideoState | None:
        """Снимок своего видеоплеера; None — синхронизировать нечего."""
        player = self._video_player
        if player is None or self._host_player is not None:
            return None
        if not (self._video_active and self._streaming):
            return None
        status = player.mediaStatus()
        return VideoState(
            position_ms=max(0, int(player.position())),
            duration_ms=max(0, int(player.duration())),
            playing=player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
            buffering=status in _STALLED_STATUSES,
            seekable=status in _SEEKABLE_STATUSES,
        )

    def seek_ms(self, position_ms: int) -> None:
        player = self._streaming_player()
        if player is None:
            return
        duration = int(player.duration())
        if not wallpaper_can_apply_seek(duration_ms=duration, media_ready=True):
            return
        player.setPosition(wallpaper_seek_target(position_ms, duration))

    def set_playback_rate(self, rate: float) -> None:
        player = self._streaming_player()
        if player is not None and abs(player.playbackRate() - rate) > 1e-3:
            player.setPlaybackRate(rate)

    def pause_video(self) -> None:
        player = self._streaming_player()
        if player is not None:
            player.pause()

    def resume_video(self) -> None:
        player = self._streaming_player()
        if player is not None and self._dynamic_enabled:
            player.play()

    def _streaming_player(self) -> QMediaPlayer | None:
        if self._host_player is not None or not self._video_active:
            return None
        if not self._streaming:
            return None
        return self._video_player

    def stop_video(self) -> None:
        self._set_video_active(False)
        self._streaming = False
        self._current_source = None
        self._loop_enabled = False
        self._stall_notified = False
        self._detach_host()
        if self._video_player is not None:
            self._video_player.setVideoSink(self._video_feed.sink)
            self._video_player.stop()
        self._video_feed.clear()

    def _is_http_source(self) -> bool:
        source = self._current_source or ""
        return source.startswith(("http://", "https://"))

    def _on_duration_ready(self, duration: int) -> None:
        if duration > 0 and self._streaming:
            self.media_ready.emit()

    def _notify_stall(self) -> None:
        if self._stall_notified or not self._is_http_source():
            return
        self._stall_notified = True
        self.stream_stalled.emit()

    def _on_video_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._video_player is None:
            return
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self._streaming and self._video_player.duration() > 0:
                self.media_ready.emit()
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._loop_enabled:
            self._video_player.setPosition(0)
            self._video_player.play()
            return
        self._video_player.pause()
        duration = int(self._video_player.duration())
        position = int(self._video_player.position())
        # Клип честно кончился раньше трека — замираем на последнем кадре.
        if duration > 0 and position >= duration - _TRUE_END_SLOP_MS:
            return
        self._notify_stall()

    def _on_video_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        logger.warning("Видео-фон: %s", message)
        if self._video_player is not None:
            self._video_player.pause()
        self._notify_stall()


class BodyWithWallpaper(QWidget):
    """Контентная зона: обои/видео сзади, nav + страницы спереди."""

    def __init__(
        self,
        wallpaper: str | Path | None = None,
        theme: ThemeSpec | None = None,
        parent: QWidget | None = None,
        compositor: BackdropCompositor | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("bodyWithWallpaper")
        self._backdrop = WallpaperBackdrop(wallpaper, theme, self, compositor)
        self._layer_host = QWidget(self)
        self._layer_host.setObjectName("backgroundLayerHost")
        self._layer_host.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._layer_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._layer_host.setAutoFillBackground(False)
        self._layer_host.setStyleSheet(
            "#backgroundLayerHost { background: transparent; }"
        )
        self._foreground = QWidget(self)
        self._foreground.setObjectName("bodyForeground")
        self._foreground.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._foreground.setAutoFillBackground(False)
        self._foreground.setStyleSheet("#bodyForeground { background: transparent; }")
        self._layout = QHBoxLayout(self._foreground)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    @property
    def backdrop(self) -> WallpaperBackdrop:
        return self._backdrop

    @property
    def layout_host(self):
        return self._layout

    def add_background_layer(self, widget: QWidget) -> None:
        """Монтирует слой поверх обоев, но под интерфейсом."""
        widget.setParent(self._layer_host)
        widget.setGeometry(self._layer_host.rect())
        widget.show()
        self._restack()

    def remove_background_layer(self, widget: QWidget) -> None:
        if widget.parent() is not self._layer_host:
            return
        widget.hide()
        widget.setParent(None)

    def _restack(self) -> None:
        self._backdrop.lower()
        self._layer_host.stackUnder(self._foreground)
        self._foreground.raise_()

    def set_theme(self, theme: ThemeSpec) -> None:
        self._backdrop.set_theme(theme)

    def set_wallpaper(self, path: str | Path | None) -> None:
        self._backdrop.set_wallpaper(path)

    def set_theater_mode(self, enabled: bool) -> None:
        """Видео на весь контент. Шапка и плеер остаются снаружи."""
        self._wake_background_layers()
        self._backdrop.set_cinematic(enabled)
        self._restack()

    def _wake_background_layers(self) -> None:
        self._layer_host.show()
        for child in self._layer_host.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            refresh = getattr(child, "_refresh_timer", None)
            if callable(refresh):
                refresh()

    def _sync_content_rect(self) -> None:
        origin = self.mapTo(self.window(), QPoint(0, 0))
        self._backdrop.compositor.set_content_rect(QRect(origin, self.size()))

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._sync_content_rect()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_content_rect()
        rect = self.rect()
        self._backdrop.setGeometry(rect)
        self._layer_host.setGeometry(rect)
        self._foreground.setGeometry(rect)
        for child in self._layer_host.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            child.setGeometry(rect)
        self._restack()
