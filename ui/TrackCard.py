"""Универсальная карточка трека.

Используется в поиске, плейлистах и везде, где нужно показать трек.
Показывает: обложку, название, автора, source-бейдж.
При ховере: play-кнопка поверх обложки, кнопка скачивания справа.
Клик на карточку = играть.

Сигналы:
  play_requested(Track)     — пользователь хочет проиграть трек
  download_requested(Track) — пользователь хочет скачать трек
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QSizePolicy, QToolButton,
)
from PySide6.QtGui import QPixmap, QColor, QPainter, QIcon
from PySide6.QtCore import Qt, Signal, QSize
from qasync import asyncSlot

from models import Track
from providers import PathProvider
from services import AsyncDownloader

_COVER_SIZE = 48
_CARD_HEIGHT = 60
_BORDER_RADIUS = 10
_SOURCE_COLORS = {
    "yandex": QColor(0, 220, 255, 140),
    "youtube": QColor(255, 60, 60, 140),
}
_DEFAULT_SOURCE_COLOR = QColor(160, 160, 160, 140)

_BTN_STYLE = """
    QToolButton {{
        background: rgba({bg});
        border: none;
        border-radius: {radius}px;
    }}
    QToolButton:hover {{
        background: rgba({bg_hover});
    }}
"""


class _PlayOverlay(QToolButton):
    """Play button that sits on top of the cover."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self.setIconSize(QSize(22, 22))
        self.setIcon(QIcon("assets/icons/play.png"))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_BTN_STYLE.format(
            bg="0, 0, 0, 140",
            bg_hover="0, 0, 0, 190",
            radius=_COVER_SIZE // 4,
        ))
        self.hide()


class _DownloadButton(QToolButton):
    """Small download button that appears on hover."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setIconSize(QSize(16, 16))
        self.setIcon(QIcon("assets/icons/download.png"))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_BTN_STYLE.format(
            bg="255, 255, 255, 15",
            bg_hover="0, 220, 255, 50",
            radius=14,
        ))
        self.hide()


class TrackCard(QWidget):
    """Карточка трека: обложка | название + автор | source.

    При ховере: play поверх обложки, download справа.
    Клик на карточку (не на кнопки) = play.
    """

    play_requested = Signal(object)
    download_requested = Signal(object)

    def __init__(self, track: Optional[Track] = None, index: int = 0, parent=None) -> None:
        super().__init__(parent)

        self._track: Optional[Track] = None
        self._index = index
        self._hovered = False
        self._path_provider = PathProvider()
        self._downloader = AsyncDownloader()

        self.setObjectName("TrackCard")
        self.setFixedHeight(_CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

        # --- layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        # --- index number ---
        self._num_label = QLabel(str(index) if index else "")
        self._num_label.setFixedWidth(22)
        self._num_label.setAlignment(Qt.AlignCenter)
        self._num_label.setStyleSheet(
            "color: rgba(255,255,255,80); font-size: 13px; background: transparent;"
        )
        layout.addWidget(self._num_label)

        # --- cover (container for overlay) ---
        self._cover_container = QWidget()
        self._cover_container.setFixedSize(_COVER_SIZE, _COVER_SIZE)

        self._cover = QLabel(self._cover_container)
        self._cover.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setStyleSheet(
            f"background: #1a1a1a; border-radius: {_COVER_SIZE // 4}px;"
        )

        self._play_btn = _PlayOverlay(self._cover_container)
        self._play_btn.clicked.connect(self._on_play)

        layout.addWidget(self._cover_container)

        # --- text block ---
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self._title = QLabel()
        self._title.setStyleSheet(
            "color: white; font-size: 14px; font-weight: 600; background: transparent;"
        )
        self._title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._title.setWordWrap(False)

        self._author = QLabel()
        self._author.setStyleSheet(
            "color: rgba(255,255,255,120); font-size: 12px; background: transparent;"
        )

        text_layout.addWidget(self._title)
        text_layout.addWidget(self._author)
        layout.addLayout(text_layout, stretch=1)

        # --- source badge ---
        self._source_badge = QLabel()
        self._source_badge.setFixedHeight(22)
        self._source_badge.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._source_badge)

        # --- download button (hover only) ---
        self._dl_btn = _DownloadButton()
        self._dl_btn.clicked.connect(self._on_download)
        layout.addWidget(self._dl_btn)

        if track is not None:
            self.set_track(track, index)

    # --- public API ---

    def set_track(self, track: Track, index: int = 0) -> None:
        """Set or update the displayed track."""
        self._track = track
        self._index = index

        self._num_label.setText(str(index) if index else "")
        self._title.setText(track.title)
        self._author.setText(track.author)

        color = _SOURCE_COLORS.get(track.source, _DEFAULT_SOURCE_COLOR)
        self._source_badge.setText(track.source)
        self._source_badge.setStyleSheet(f"""
            color: white; font-size: 11px; font-weight: 600;
            background: rgba({color.red()},{color.green()},{color.blue()},{color.alpha()});
            border-radius: 6px; padding: 2px 8px;
        """)
        self._source_badge.adjustSize()

    @asyncSlot()
    async def load_cover(self) -> None:
        """Load cover async (download if missing)."""
        if self._track is None:
            return
        path = self._path_provider.get_cover_path(self._track)
        if not os.path.exists(path):
            await self._downloader.download_cover(self._track)
        if os.path.exists(path):
            pixmap = QPixmap(path).scaled(
                _COVER_SIZE, _COVER_SIZE,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self._cover.setPixmap(pixmap)

    @property
    def track(self) -> Optional[Track]:
        return self._track

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
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._play_btn.hide()
        self._dl_btn.hide()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._track is not None:
            self.play_requested.emit(self._track)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if self._hovered:
            painter.setBrush(QColor(0, 220, 255, 20))
        else:
            painter.setBrush(QColor(255, 255, 255, 6))

        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), _BORDER_RADIUS, _BORDER_RADIUS)
        painter.end()

        super().paintEvent(event)
