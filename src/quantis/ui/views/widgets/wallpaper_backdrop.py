from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QHBoxLayout, QWidget

from quantis.services.wallpaper_policy import (
    WALLPAPER_DEFAULT_FPS,
    wallpaper_can_apply_seek,
    wallpaper_decode_max_side,
    wallpaper_seek_landed,
    wallpaper_seek_target,
)
from quantis.ui.views.widgets.cover_art import load_wallpaper_pixmap

_WALLPAPER_MAX_SIDE = 1280


def _media_url(url: str) -> QUrl:
    if url.startswith(("http://", "https://")):
        return QUrl(url)
    return QUrl.fromLocalFile(url)


class _VideoSurface(QWidget):
    """Видео через QVideoSink — рисуется под UI, без нативного оверлея."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._sink = QVideoSink(self)
        self._source = QImage()
        self._scaled = QImage()
        self._opacity = 0.28
        self._cinematic = False
        self._last_frame_at = 0.0
        self._min_interval = 1.0 / WALLPAPER_DEFAULT_FPS
        self._max_side = wallpaper_decode_max_side(360)
        self._sink.videoFrameChanged.connect(self._on_frame)

    @property
    def sink(self) -> QVideoSink:
        return self._sink

    def is_empty(self) -> bool:
        return self._source.isNull() and self._scaled.isNull()

    def set_limits(self, *, fps: int, max_side: int) -> None:
        self._min_interval = 1.0 / max(1, int(fps))
        self._max_side = max(320, int(max_side))

    def set_opacity(self, value: float) -> None:
        self._opacity = max(0.05, min(1.0, value))
        self.update()

    def set_cinematic(self, enabled: bool) -> None:
        if self._cinematic == enabled:
            return
        self._cinematic = enabled
        self._opacity = 1.0 if enabled else 0.28
        self.update()

    def clear(self) -> None:
        self._source = QImage()
        self._scaled = QImage()
        self._last_frame_at = 0.0
        self.update()

    def set_still(self, image: QImage) -> None:
        if image.isNull():
            return
        self._last_frame_at = 0.0
        self._source = self._compact_frame(image)
        self._rescale()

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

        if image.isNull():
            return

        self._source = self._compact_frame(image)
        self._rescale()

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

    def _rescale(self) -> None:
        if self._source.isNull():
            return
        target = self.size()
        if target.width() <= 0 or target.height() <= 0:
            return
        self._scaled = self._source.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.FastTransformation,
        )
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def paintEvent(self, event) -> None:
        if self._scaled.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        if self._cinematic:
            painter.fillRect(rect, QColor(0, 0, 0))
        painter.setOpacity(self._opacity)
        x = (rect.width() - self._scaled.width()) // 2
        y = (rect.height() - self._scaled.height()) // 2
        painter.drawImage(x, y, self._scaled)
        painter.setOpacity(1.0)
        self._paint_dim(painter, rect)
        painter.end()

    def _paint_dim(self, painter: QPainter, rect) -> None:
        radius = max(rect.width(), rect.height()) * (0.74 if self._cinematic else 0.7)
        vignette = QRadialGradient(rect.center(), radius)
        if self._cinematic:
            painter.fillRect(rect, QColor(0, 0, 0, 28))
            vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
            vignette.setColorAt(0.42, QColor(0, 0, 0, 18))
            vignette.setColorAt(0.72, QColor(0, 0, 0, 95))
            vignette.setColorAt(1.0, QColor(0, 0, 0, 175))
            painter.fillRect(rect, vignette)
            bottom = QLinearGradient(0, rect.height() * 0.58, 0, rect.height())
            bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
            bottom.setColorAt(0.4, QColor(0, 0, 0, 55))
            bottom.setColorAt(1.0, QColor(0, 0, 0, 170))
            painter.fillRect(rect, bottom)
            return
        vignette.setColorAt(0.4, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 140))
        painter.fillRect(rect, vignette)


class WallpaperBackdrop(QWidget):
    """Слой обоев: статичный jpg или видео-клип (только в зоне контента)."""

    stream_stalled = Signal()

    def __init__(
        self,
        wallpaper: str | Path | None = None,
        variant: str = "neon",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("wallpaperBackdrop")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._variant = variant
        self._wallpaper_path: str | None = str(wallpaper) if wallpaper else None
        self._cached = QPixmap()
        self._cache_size = (0, 0)
        self._dynamic_enabled = False
        self._video_active = False
        self._current_source: str | None = None
        self._loop_enabled = False
        self._pending_start_ms = 0
        self._follow_audio = False
        self._hold_until_audio = False
        self._position_provider: Callable[[], int] | None = None
        self._stall_notified = False
        self._seeking = False
        self._host_player: QMediaPlayer | None = None

        self._video_surface = _VideoSurface(self)
        self._video_surface.hide()

        self._video_player: QMediaPlayer | None = None
        self._video_audio: QAudioOutput | None = None

        if self._wallpaper_path:
            self._rebuild_cache(force=True)

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
            self._video_player.setVideoSink(self._video_surface.sink)
            self._video_player.mediaStatusChanged.connect(self._on_video_status)
            self._video_player.durationChanged.connect(self._on_duration_ready)
            self._video_player.errorOccurred.connect(self._on_video_error)
        elif self._host_player is None:
            self._video_player.setVideoSink(self._video_surface.sink)
        return self._video_player

    def is_following_audio_player(self) -> bool:
        return self._host_player is not None

    def follow_media_player(self, player: QMediaPlayer | None) -> None:
        """Кадры с плеера трека: без второго googlevideo и без рассинхрона."""
        if not self._dynamic_enabled:
            return
        if player is self._host_player and player is not None:
            self._video_active = True
            self._video_surface.show()
            self.lower()
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
        self._follow_audio = False
        self._hold_until_audio = False
        self._pending_start_ms = 0
        self._stall_notified = False
        self._video_active = True
        self._current_source = "host-player"
        self._cached = QPixmap()
        self._cache_size = (0, 0)
        player.setVideoSink(self._video_surface.sink)
        self._video_surface.show()
        self.lower()
        self.update()

    def _detach_host(self) -> None:
        if self._host_player is None:
            return
        self._host_player.setVideoSink(None)
        self._host_player = None

    def set_variant(self, variant: str) -> None:
        if self._variant != variant:
            self._variant = variant
            self.update()

    def set_wallpaper(self, path: str | Path | None) -> None:
        new_path = str(path) if path else None
        if new_path == self._wallpaper_path and not self._cached.isNull():
            return
        self._wallpaper_path = new_path
        self._cache_size = (0, 0)
        self._cached = QPixmap()
        self._rebuild_cache(force=True)
        self.update()

    def set_dynamic_wallpaper_enabled(self, enabled: bool) -> None:
        self._dynamic_enabled = enabled
        if not enabled:
            self.stop_video()
        else:
            self._cached = QPixmap()
            self._cache_size = (0, 0)
            self.update()

    def set_video_limits(self, *, fps: int, max_side: int) -> None:
        self._video_surface.set_limits(fps=fps, max_side=max_side)

    def set_cinematic(self, enabled: bool) -> None:
        self._video_surface.set_cinematic(enabled)
        self.update()

    def set_position_provider(self, provider: Callable[[], int] | None) -> None:
        """Источник актуальной позиции аудио для старта видео «в ноль»."""
        self._position_provider = provider

    def play_video_url(
        self,
        url: str,
        *,
        loop: bool = False,
        start_ms: int = 0,
        follow_audio: bool = False,
        hold_until_audio: bool = False,
    ) -> None:
        if not self._dynamic_enabled or not url:
            return
        self._detach_host()
        self._loop_enabled = loop
        self._follow_audio = follow_audio and not loop
        self._hold_until_audio = hold_until_audio and not loop
        self._pending_start_ms = max(0, int(start_ms))
        self._stall_notified = False
        self._video_active = True
        self._cached = QPixmap()
        self._cache_size = (0, 0)
        self._video_surface.show()
        self.lower()
        player = self._ensure_video_player()
        if url == self._current_source and player.playbackState() in (
            QMediaPlayer.PlaybackState.PlayingState,
            QMediaPlayer.PlaybackState.PausedState,
        ):
            self._apply_pending_seek()
            return
        self._current_source = url
        self._silence_video_audio()
        player.setSource(_media_url(url))
        player.play()
        self.update()

    def show_still(self, path: str) -> None:
        if not self._dynamic_enabled or not path:
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        original = reader.size()
        max_side = self._video_surface._max_side
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
        self._pending_start_ms = 0
        self._follow_audio = False
        self._hold_until_audio = False
        self._stall_notified = False
        self._video_active = True
        self._current_source = path
        self._cached = QPixmap()
        self._cache_size = (0, 0)
        if self._video_player is not None:
            self._video_player.stop()
            self._video_player.setSource(QUrl())
        self._video_surface.set_still(image)
        self._video_surface.show()
        self.lower()
        self.update()

    def has_picture(self) -> bool:
        return self._video_active and not self._video_surface.is_empty()

    def is_video_playing(self) -> bool:
        if self._host_player is not None:
            return self._video_active
        if self._video_player is None:
            return False
        return self._video_active and self._video_player.playbackState() in (
            QMediaPlayer.PlaybackState.PlayingState,
            QMediaPlayer.PlaybackState.PausedState,
        )

    def position_ms(self) -> int:
        if self._video_player is None:
            return 0
        return max(0, int(self._video_player.position()))

    def seek_ms(self, position_ms: int) -> None:
        if self._host_player is not None:
            return
        if self._video_player is None or not self._video_active:
            return
        self._pending_start_ms = max(0, int(position_ms))
        self._follow_audio = False
        self._hold_until_audio = False
        self._apply_pending_seek()

    def pause_video(self) -> None:
        if self._host_player is not None:
            return
        if self._video_active and self._video_player is not None:
            self._video_player.pause()

    def resume_video(self) -> None:
        self._hold_until_audio = False
        if self._host_player is not None:
            return
        if (
            self._video_active
            and self._dynamic_enabled
            and self._video_player is not None
        ):
            self._video_player.play()
            self._apply_pending_seek()

    def stop_video(self) -> None:
        self._video_active = False
        self._current_source = None
        self._loop_enabled = False
        self._pending_start_ms = 0
        self._follow_audio = False
        self._hold_until_audio = False
        self._stall_notified = False
        self._seeking = False
        self._detach_host()
        if self._video_player is not None:
            self._video_player.setVideoSink(self._video_surface.sink)
            self._video_player.stop()
        self._video_surface.clear()
        self._video_surface.hide()
        if not self._dynamic_enabled:
            self._rebuild_cache(force=True)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._video_surface.setGeometry(self.rect())
        if not self._video_active and not self._dynamic_enabled:
            self._rebuild_cache()

    def _is_http_source(self) -> bool:
        source = self._current_source or ""
        return source.startswith(("http://", "https://"))

    def _media_ready_for_seek(self) -> bool:
        if self._video_player is None:
            return False
        status = self._video_player.mediaStatus()
        return status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        )

    def _apply_pending_seek(self) -> None:
        if self._video_player is None or self._seeking:
            return
        if not self._follow_audio and self._pending_start_ms <= 0:
            return
        position = self._pending_start_ms
        if self._follow_audio and self._position_provider is not None:
            # Пока грузился поток, трек ушёл вперёд — берём позицию на сейчас.
            position = max(0, int(self._position_provider()))
        duration = int(self._video_player.duration())
        if not wallpaper_can_apply_seek(
            duration_ms=duration, media_ready=self._media_ready_for_seek()
        ):
            return
        target = wallpaper_seek_target(position, duration)
        self._seeking = True
        try:
            playing = (
                self._video_player.playbackState()
                == QMediaPlayer.PlaybackState.PlayingState
            )
            self._video_player.setPosition(target)
            landed = wallpaper_seek_landed(self._video_player.position(), target)
            if landed:
                self._pending_start_ms = 0
                self._follow_audio = False
            if not playing and not self._hold_until_audio:
                self._video_player.play()
        finally:
            self._seeking = False

    def _on_duration_ready(self, duration: int) -> None:
        if duration > 0:
            self._apply_pending_seek()

    def _notify_stall(self) -> None:
        if self._stall_notified or not self._is_http_source():
            return
        self._stall_notified = True
        self.stream_stalled.emit()

    def _on_video_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._video_player is None:
            return
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._apply_pending_seek()
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._loop_enabled:
            self._video_player.setPosition(0)
            self._video_player.play()
            return
        self._video_player.pause()
        self._notify_stall()

    def _on_video_error(self, _error: QMediaPlayer.Error, message: str) -> None:
        import logging

        logging.getLogger(__name__).warning("Видео-фон: %s", message)
        if self._video_player is not None:
            self._video_player.pause()
        self._notify_stall()

    def _rebuild_cache(self, *, force: bool = False) -> None:
        size = self.size()
        if size.width() <= 0 or size.height() <= 0 or not self._wallpaper_path:
            self._cached = QPixmap()
            return
        if (
            not force
            and (size.width(), size.height()) == self._cache_size
            and not self._cached.isNull()
        ):
            return

        source = load_wallpaper_pixmap(self._wallpaper_path, _WALLPAPER_MAX_SIDE)
        if source.isNull():
            self._cached = QPixmap()
            return
        self._cached = source.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.FastTransformation,
        )
        self._cache_size = (size.width(), size.height())

    def _wallpaper_opacity(self) -> float:
        return {
            "classic": 0.12,
            "neon": 0.11,
            "editorial": 0.0,
            "light": 0.14,
            "yellow_dark": 0.11,
        }.get(self._variant, 0.10)

    def paintEvent(self, event) -> None:
        if self._video_active:
            return

        if self._cached.isNull() and self._wallpaper_path and not self._dynamic_enabled:
            self._rebuild_cache(force=True)

        if self._dynamic_enabled or self._variant == "editorial" or self._cached.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        painter.setOpacity(self._wallpaper_opacity())
        x = (rect.width() - self._cached.width()) // 2
        y = (rect.height() - self._cached.height()) // 2
        painter.drawPixmap(x, y, self._cached)
        painter.end()


class BodyWithWallpaper(QWidget):
    """Контентная зона: обои/видео сзади, nav + страницы спереди."""

    def __init__(
        self,
        wallpaper: str | Path | None = None,
        variant: str = "neon",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("bodyWithWallpaper")
        self._backdrop = WallpaperBackdrop(wallpaper, variant, self)
        self._layer_host = QWidget(self)
        self._layer_host.setObjectName("backgroundLayerHost")
        self._layer_host.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._layer_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._layer_host.setAutoFillBackground(False)
        self._layer_host.setStyleSheet("background: transparent;")
        self._foreground = QWidget(self)
        self._foreground.setObjectName("bodyForeground")
        self._foreground.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._foreground.setAutoFillBackground(False)
        self._foreground.setStyleSheet("background: transparent;")
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

    def set_variant(self, variant: str) -> None:
        self._backdrop.set_variant(variant)

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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        rect = self.rect()
        self._backdrop.setGeometry(rect)
        self._layer_host.setGeometry(rect)
        self._foreground.setGeometry(rect)
        for child in self._layer_host.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            child.setGeometry(rect)
        self._restack()
