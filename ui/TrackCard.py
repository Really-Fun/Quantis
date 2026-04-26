"""Карточка трека

Используется в поиске, плейлистах и везде, где нужно отобразить трек.
Показывает: обложку, название, автора, бейдж источника.
При наведении: кнопка play поверх обложки, кнопка скачивания справа.
Клик по карточке — воспроизведение.

Сигналы:
  play_requested(Track)
  download_requested(Track)
  add_to_playlist_requested(Track)
  remove_from_playlist_requested(Track)
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from models import Track
from providers import PathProvider
from services import AsyncDownloader
from utils import asset_path

_COVER_SIZE = 48
_CARD_HEIGHT = 60
_BORDER_RADIUS = 10


class _PlayOverlay(QToolButton):
    """Кнопка воспроизведения поверх обложки."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("playOverlayBtn")
        self.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self.setIconSize(QSize(22, 22))
        self.setIcon(QIcon(asset_path("assets/icons/play.png")))
        self.setCursor(Qt.PointingHandCursor)
        self.hide()


class _DownloadButton(QToolButton):
    """Кнопка скачивания, видима при наведении."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("downloadBtn")
        self.setFixedSize(28, 28)
        self.setIconSize(QSize(16, 16))
        self.setIcon(QIcon(asset_path("assets/icons/download.png")))
        self.setCursor(Qt.PointingHandCursor)
        self.hide()


class TrackCard(QWidget):
    """Карточка трека: обложка | название + автор | source.

    При ховере: play поверх обложки, download справа.
    Клик на карточку (не на кнопки) = play.
    """

    play_requested = Signal(object)
    download_requested = Signal(object)
    add_to_playlist_requested = Signal(object)
    remove_from_playlist_requested = Signal(object)
    _shared_downloader: AsyncDownloader | None = None

    def __init__(
        self,
        track: Optional[Track] = None,
        index: int = 0,
        allow_remove_from_playlist: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)

        # Применяем общий стиль к карточке, который спустится на все дочерние элементы
        # self.setStyleSheet(_TRACKCARD_QSS)

        self._track: Optional[Track] = None
        self._index = index
        self._is_playing = False
        self._hovered = False
        self._allow_remove_from_playlist = allow_remove_from_playlist
        self._path_provider = PathProvider()
        
        if TrackCard._shared_downloader is None:
            TrackCard._shared_downloader = AsyncDownloader()
        self._downloader = TrackCard._shared_downloader

        self.setObjectName("TrackCard")
        self.setFixedHeight(_CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # --- layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        # --- index number ---
        self._num_label = QLabel()
        self._num_label.setObjectName("trackIndex")
        self._num_label.setProperty("state", "normal") # Начальное состояние
        self._num_label.setFixedWidth(22)
        self._num_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._num_label)

        # --- cover (container for overlay) ---
        self._cover_container = QWidget()
        self._cover_container.setFixedSize(_COVER_SIZE, _COVER_SIZE)

        self._cover = QLabel(self._cover_container)
        self._cover.setObjectName("trackCover")
        self._cover.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self._cover.setAlignment(Qt.AlignCenter)

        self._play_btn = _PlayOverlay(self._cover_container)
        self._play_btn.clicked.connect(self._on_play)

        layout.addWidget(self._cover_container)

        # --- text block ---
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self._title = QLabel()
        self._title.setObjectName("trackTitle")
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._title.setWordWrap(False)

        self._author = QLabel()
        self._author.setObjectName("trackAuthor")

        text_layout.addWidget(self._title)
        text_layout.addWidget(self._author)
        layout.addLayout(text_layout, stretch=1)

        # --- source badge ---
        self._source_badge = QLabel()
        self._source_badge.setObjectName("trackSourceBadge")
        self._source_badge.setFixedHeight(22)
        self._source_badge.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._source_badge)

        # --- download button (hover only) ---
        self._dl_btn = _DownloadButton()
        self._dl_btn.clicked.connect(self._on_download)
        layout.addWidget(self._dl_btn)

        if track is not None:
            self.set_track(track, index)
        else:
            self._update_index_label()

    # --- public API ---

    def set_track(self, track: Track, index: int = 0) -> None:
        """Устанавливает или обновляет отображаемый трек."""
        self._track = track
        self._index = index
        self._update_index_label()
        self._title.setText(track.title)
        self._author.setText(self._build_meta_line(track))

        self._source_badge.setText(track.source)
        
        # Задаем свойство для цвета бейджа (обрабатывается в QSS)
        source_prop = track.source if track.source in ["yandex", "youtube"] else "default"
        self._source_badge.setProperty("source", source_prop)
        self._source_badge.style().unpolish(self._source_badge)
        self._source_badge.style().polish(self._source_badge)
        self._source_badge.adjustSize()

    @staticmethod
    def _build_meta_line(track: Track) -> str:
        """Формирует строку автора и количества прослушиваний."""
        listens = max(0, int(getattr(track, "listen_count", 0)))
        if listens == 0:
            return track.author
        return f"{track.author} · {TrackCard._format_listens(listens)}"

    @staticmethod
    def _format_listens(listens: int) -> str:
        """Возвращает фразу с корректным склонением слова 'прослушивание'."""
        tail_100 = listens % 100
        tail_10 = listens % 10
        if 11 <= tail_100 <= 14:
            word = "прослушиваний"
        elif tail_10 == 1:
            word = "прослушивание"
        elif 2 <= tail_10 <= 4:
            word = "прослушивания"
        else:
            word = "прослушиваний"
        return f"{listens} {word}"

    def set_playing(self, is_playing: bool) -> None:
        """Включает или выключает подсветку воспроизводимого трека."""
        self._is_playing = is_playing
        
        # Обновляем состояние метки индекса для QSS
        state = "playing" if is_playing else "normal"
        self._num_label.setProperty("state", state)
        self._num_label.style().unpolish(self._num_label)
        self._num_label.style().polish(self._num_label)

        self.setProperty("playing", "true" if is_playing else "false")
        self.style().unpolish(self)
        self.style().polish(self)

        self._update_index_label()

    @asyncSlot()
    async def load_cover(self) -> None:
        """Асинхронно загружает обложку, при необходимости скачивает."""
        if self._track is None:
            return
        path = self._path_provider.get_cover_path(self._track)
        if not os.path.exists(path):
            await self._downloader.download_cover(self._track)
        if os.path.exists(path):
            pixmap = QPixmap(path).scaled(
                _COVER_SIZE,
                _COVER_SIZE,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self._cover.setPixmap(pixmap)

    @property
    def track(self) -> Optional[Track]:
        return self._track

    def _update_index_label(self) -> None:
        if self._is_playing:
            self._num_label.setText("▶")
        else:
            self._num_label.setText(str(self._index) if self._index else "")

    # --- slots ---

    def _on_play(self) -> None:
        if self._track is not None:
            self.play_requested.emit(self._track)

    def _on_download(self) -> None:
        if self._track is not None:
            self.download_requested.emit(self._track)

    # --- events ---

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._play_btn.show()
        self._dl_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._play_btn.hide()
        self._dl_btn.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._track is not None:
            self.play_requested.emit(self._track)
        elif event.button() == Qt.RightButton and self._track is not None:
            self._show_context_menu(event.globalPos())
        super().mousePressEvent(event)

    def _show_context_menu(self, global_pos) -> None:
        """Открывает контекстное меню действий с треком."""
        menu = QMenu(self)
        play_action = menu.addAction("Играть")
        add_action = menu.addAction("Добавить в плейлист")
        remove_action = None
        if self._allow_remove_from_playlist:
            remove_action = menu.addAction("Удалить из плейлиста")
        download_action = menu.addAction("Скачать")

        chosen = menu.exec(global_pos)
        if chosen == play_action:
            self._on_play()
        elif chosen == add_action and self._track is not None:
            self.add_to_playlist_requested.emit(self._track)
        elif (
            remove_action is not None
            and chosen == remove_action
            and self._track is not None
        ):
            self.remove_from_playlist_requested.emit(self._track)
        elif chosen == download_action:
            self._on_download()
