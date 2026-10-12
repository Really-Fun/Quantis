from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QPointF, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.models.repeat_mode import RepeatMode
from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.services.liked_tracks import LikedTracksService
from quantis.services.music_service import MusicService
from quantis.ui import resources
from quantis.ui.accent import AccentStyles
from quantis.ui.cover_accent import CoverPalette
from quantis.ui.cover_prefetch import schedule_cover_prefetch
from quantis.ui.live_palette import LivePalette
from quantis.ui.playlist_actions import show_add_to_playlist_menu
from quantis.ui.preferences import UiPreferences
from quantis.ui.ui_extensions import PlayerActionExtension, UiExtensionHost
from quantis.ui.viewmodels.player_vm import PlayerViewModel
from quantis.ui.views.widgets.cover_art import load_cover_pixmap
from quantis.ui.views.widgets.elided_label import ElidedLabel
from quantis.ui.views.widgets.glass import install_glass
from quantis.ui.views.widgets.source_badge import paint_source_badge
from quantis.ui.views.widgets.waveform_seek import WaveformSeekSlider

logger = logging.getLogger(__name__)

COVER_SIZE = 56
COVER_GAP = 12
HALO_RADIUS = 38
"""Ореол акцента вокруг Play."""

_CINEMATIC_CARD_QSS = (
    "QFrame#PlayMenu { background: rgba(0, 0, 0, 0.38); border: none;}"
)
_REPEAT_LOOK = {
    RepeatMode.PLAYLIST: ("repeat.svg", "Повтор плейлиста"),
    RepeatMode.TRACK: ("repeat-one.svg", "Повтор трека"),
}


class _PlayerCover(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("coverLabel")
        self.setFixedSize(COVER_SIZE, COVER_SIZE)
        self._pixmap = QPixmap()
        self._source: str | None = None

    def set_cover(self, pixmap: QPixmap | None, source: str | None) -> None:
        self._pixmap = pixmap if pixmap is not None else QPixmap()
        self._source = source
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.setClipPath(path)
        if not self._pixmap.isNull():
            painter.drawPixmap(rect, self._pixmap)
        else:
            painter.fillPath(path, QColor(255, 255, 255, 16))
        painter.setClipping(False)
        if self._source:
            paint_source_badge(painter, rect, self._source, size=14)
        painter.end()


class PlayerBar(QFrame):
    """Нижняя панель 88 px — плавающая стеклянная капсула:
    обложка и название | транспорт и волна перемотки | действия."""

    SIDE, MIN_SIDE = 300, 220
    """Ширина колонок обложки и кнопок; на узком окне — до MIN_SIDE."""
    CENTER_RESERVE = 700
    """Сколько ширины панели оставляем середине прежде, чем отдать колонкам."""

    now_playing_toggle_requested = Signal()
    hide_ui_requested = Signal()

    def __init__(
        self,
        view_model: PlayerViewModel,
        path_provider: PathProvider,
        *,
        bridge: AsyncBridge | None = None,
        music: MusicService | None = None,
        on_liked_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._path_provider = path_provider
        self._bridge = bridge
        self._music = music
        self._liked = LikedTracksService()
        self._on_liked_changed = on_liked_changed
        self._extensions = UiExtensionHost.instance()
        self._palette = LivePalette.instance().current
        self._current_track: Track | None = None
        self._seeking = False
        self._is_playing = False
        self._track_liked = False
        self._cinematic = False

        self.setObjectName("playerDock")
        self.setFixedHeight(88)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)

        self._card = self._build_card()
        dock = QVBoxLayout(self)
        dock.setContentsMargins(10, 4, 10, 10)
        dock.setSpacing(0)
        dock.addWidget(self._card)

        self._connect_signals()
        self._rebuild_plugin_actions()  # заодно подгоняет ширину колонок
        self._restore_state()

    # ---------------------------------------------------------------- layout

    def _build_card(self) -> QFrame:
        # Отсвет акцента слева и ореол Play рисуются поверх стекла (без
        # QGraphicsDropShadowEffect — капсула перерисовывается вместе с фоном
        # на каждом кадре клипа).
        card = QFrame()
        card.setObjectName("PlayMenu")
        install_glass(card, "QFrame#PlayMenu", overlay=self._paint_capsule)

        body = QGridLayout(card)
        body.setContentsMargins(14, 8, 20, 8)
        body.setHorizontalSpacing(12)
        body.setColumnStretch(1, 1)
        body.addWidget(
            self._build_meta(),
            0,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        body.addWidget(self._build_center(), 0, 1, Qt.AlignmentFlag.AlignVCenter)
        body.addWidget(
            self._build_actions(),
            0,
            2,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        return card

    def _build_meta(self) -> QWidget:
        """Слева: обложка, название и исполнитель."""
        self._cover = _PlayerCover()
        self._title = ElidedLabel("Ничего не играет", max_lines=1)
        self._title.setObjectName("trackTitle")
        AccentStyles.instance().bind(self._title, resources.ACCENT_TRACK_TITLE_QSS)
        self._author = ElidedLabel("", max_lines=1)
        self._author.setObjectName("trackArtist")

        meta = QVBoxLayout()
        meta.setSpacing(2)
        meta.setContentsMargins(0, 0, 0, 0)
        meta.addWidget(self._title)
        meta.addWidget(self._author)

        self._left = QWidget()
        self._left.setObjectName("playerLeft")
        layout = QHBoxLayout(self._left)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(COVER_GAP)
        layout.addWidget(self._cover)
        layout.addLayout(meta, stretch=1)
        return self._left

    def _build_center(self) -> QWidget:
        """Одна строка, как в капсуле референса: кнопки, время, волна, время."""
        self._repeat_btn = self._make_button(
            "repeat.svg", "Повтор плейлиста", size=36, object_name="repeatButton"
        )
        self._repeat_btn.setProperty("state", "active")
        self._repeat_btn.clicked.connect(self._vm.cycle_repeat_mode)
        self._prev_btn = self._make_button("prev.svg", "Назад", size=40)
        self._prev_btn.clicked.connect(self._vm.play_previous)
        self._play_btn = self._make_button("play.svg", "Play", accent=True, size=44)
        self._play_btn.clicked.connect(self._vm.toggle_pause)
        self._refresh_play_icon()
        self._next_btn = self._make_button("next.svg", "Далее", size=40)
        self._next_btn.clicked.connect(self._vm.play_next)

        transport_host = QWidget()
        transport_host.setFixedHeight(48)
        transport = QHBoxLayout(transport_host)
        transport.setContentsMargins(0, 0, 0, 0)
        transport.setSpacing(10)
        transport.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        for button in (
            self._repeat_btn,
            self._prev_btn,
            self._play_btn,
            self._next_btn,
        ):
            transport.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)

        self._elapsed = self._make_time_label()
        self._elapsed.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._position = WaveformSeekSlider()
        self._position.setRange(0, 0)
        self._position.setFixedHeight(30)
        self._position.sliderPressed.connect(self._on_seek_start)
        self._position.sliderReleased.connect(self._on_seek_end)
        self._duration_label = self._make_time_label()

        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        seek_row.addWidget(self._elapsed)
        seek_row.addWidget(self._position, stretch=1)
        seek_row.addWidget(self._duration_label)

        center = QWidget()
        center.setObjectName("playerCenter")
        layout = QHBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(transport_host, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(seek_row, 1)
        return center

    def _build_actions(self) -> QWidget:
        """Справа: кнопки плагинов, действия с треком и громкость."""
        self._hide_ui_btn = self._make_button(
            "hide-ui-neon.svg", "Скрыть интерфейс (S)"
        )
        self._hide_ui_btn.clicked.connect(self.hide_ui_requested.emit)
        self._now_btn = self._make_button("radio.svg", "Now Playing")
        self._now_btn.clicked.connect(self.now_playing_toggle_requested.emit)
        self._download_btn = self._make_button("download.svg", "Скачать")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download_clicked)
        self._playlist_btn = self._make_button("folder.svg", "В плейлист")
        self._playlist_btn.setEnabled(False)
        self._playlist_btn.clicked.connect(self._on_add_to_playlist_clicked)
        self._like_btn = self._make_button("heart.svg", "В любимые")
        self._like_btn.clicked.connect(self.toggle_like)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setObjectName("volSlider")
        self._volume.setFixedWidth(72)
        self._volume.setRange(0, 100)
        self._volume.valueChanged.connect(self._vm.set_volume)

        self._plugin_slot = QHBoxLayout()
        self._plugin_slot.setSpacing(2)

        self._right = QWidget()
        self._right.setObjectName("playerRight")
        self._right_layout = QHBoxLayout(self._right)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_layout.setSpacing(4)
        self._right_layout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._right_layout.addLayout(self._plugin_slot)
        for widget in (
            self._hide_ui_btn,
            self._now_btn,
            self._download_btn,
            self._playlist_btn,
            self._like_btn,
            self._volume,
        ):
            self._right_layout.addWidget(widget)
        return self._right

    def _make_button(
        self,
        icon_name: str,
        tooltip: str,
        *,
        accent: bool = False,
        size: int = 32,
        object_name: str = "controlButton",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName(object_name)
        button.setProperty("accent", accent)
        button.setProperty("compact", size <= 32)  # скругление 16 px — круг
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        icon_size = 18 if accent else 16
        button.setIcon(resources.load_icon(icon_name))
        button.setIconSize(QSize(icon_size, icon_size))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(size, size)
        self._repolish(button)
        return button

    def _make_plugin_button(self, action: PlayerActionExtension) -> QToolButton:
        button = QToolButton()
        button.setObjectName("controlButton")
        button.setProperty("plugin", True)
        button.setProperty("compact", True)
        button.setIcon(action.icon or resources.load_icon("puzzle.svg"))
        button.setIconSize(QSize(16, 16))
        button.setToolTip(action.tooltip + " · плагин")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(32, 32)
        button.clicked.connect(action.callback)
        self._repolish(button)
        return button

    @staticmethod
    def _make_time_label() -> QLabel:
        label = QLabel("0:00")
        label.setObjectName("timeLabel")
        label.setFixedWidth(36)
        return label

    def _rebuild_plugin_actions(self) -> None:
        while self._plugin_slot.count():
            widget = self._plugin_slot.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        for action in self._extensions.player_actions():
            self._plugin_slot.addWidget(self._make_plugin_button(action))
        self._fit_sides()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._fit_sides()

    def _fit_sides(self) -> None:
        """Боковые колонки капсулы уже на узком окне (Windows 150 % — 1280
        логических точек и меньше): иначе волне перемотки не остаётся места."""
        side = (self.width() - self.CENTER_RESERVE) // 2
        side = max(self.MIN_SIDE, min(self.SIDE, side))
        self._left.setFixedWidth(side)
        text_width = side - COVER_SIZE - COVER_GAP
        self._title.setMaximumWidth(text_width)
        self._author.setMaximumWidth(text_width)
        need = self._right_layout.sizeHint().width()
        self._right.setFixedWidth(max(side, need))

    # ----------------------------------------------------------- view model

    def _connect_signals(self) -> None:
        self._vm.track_changed.connect(self._on_track_changed)
        self._vm.is_playing_changed.connect(self._on_playing_changed)
        self._vm.position_changed.connect(self._on_position_changed)
        self._vm.duration_changed.connect(self._on_duration_changed)
        self._vm.repeat_mode_changed.connect(self._update_repeat_button)
        self._vm.volume_changed.connect(self._on_volume_changed)
        AccentStyles.instance().accent_changed.connect(self._refresh_play_icon)
        LivePalette.instance().palette_changed.connect(self._on_palette)
        self._extensions.player_actions_changed.connect(self._rebuild_plugin_actions)

    def _restore_state(self) -> None:
        saved_volume = UiPreferences().volume
        self._on_volume_changed(saved_volume)
        self._vm.set_volume(saved_volume)
        self._vm.sync_from_player()
        self._update_like_button()
        self._update_repeat_button(self._vm.repeat_mode)

    def _on_track_changed(self, track: Track) -> None:
        self._current_track = track
        self._position.set_seed(repr(track))
        self._title.setText(track.title)
        self._author.setText(track.author)
        self._author.setVisible(bool(track.author))
        self._apply_cover(track)
        self._download_btn.setEnabled(not track.downloaded)
        self._playlist_btn.setEnabled(True)
        if self._bridge is None or self._music is None:
            self._set_liked_ui(False)
            return
        schedule_cover_prefetch(
            [track],
            self._music.downloader,
            self._bridge,
            on_done=lambda: self._apply_cover(track),
            limit=1,
        )
        self._bridge.schedule(self._sync_liked_state(track))

    def _apply_cover(self, track: Track) -> None:
        cover_path = Path(self._path_provider.get_cover_path(track))
        self._cover.set_cover(
            load_cover_pixmap(cover_path, COVER_SIZE), str(track.source)
        )

    def _on_playing_changed(self, playing: bool) -> None:
        self._is_playing = playing
        self._refresh_play_icon()
        self._set_title_playing(playing)

    def _on_position_changed(self, position_ms: int) -> None:
        self._elapsed.setText(resources.format_ms(position_ms))
        if not self._seeking:
            self._position.setValue(position_ms)

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._duration_label.setText(resources.format_ms(duration_ms))
        self._position.setRange(0, max(0, duration_ms))

    def _on_seek_start(self) -> None:
        self._seeking = True

    def _on_seek_end(self) -> None:
        self._seeking = False
        self._vm.seek(self._position.value())

    def _on_volume_changed(self, value: int) -> None:
        """Громкость в ползунок — без эха обратно в set_volume."""
        if self._volume.value() != value:
            with QSignalBlocker(self._volume):
                self._volume.setValue(value)

    def _update_repeat_button(self, mode: RepeatMode) -> None:
        icon_name, tooltip = _REPEAT_LOOK[mode]
        self._repeat_btn.setIcon(resources.load_icon(icon_name))
        self._repeat_btn.setToolTip(tooltip)
        self._repeat_btn.setProperty("repeatMode", mode.value)
        self._repolish(self._repeat_btn)

    def _refresh_play_icon(self, *_: object) -> None:
        """Play/пауза на заливке акцентом: сплошной значок, контрастный акценту."""
        icon = "pause.svg" if self._is_playing else "play.svg"
        color = resources.on_color(AccentStyles.instance().color)
        self._play_btn.setIcon(resources.load_icon(icon, color))

    def _set_title_playing(self, playing: bool) -> None:
        self._title.setProperty("playing", playing)
        self._repolish(self._title)

    # ------------------------------------------------ like, playlist, download

    def toggle_like(self) -> None:
        track = self._current_track
        if track is None or self._bridge is None:
            return
        self._bridge.schedule(self._toggle_like(track))

    async def _toggle_like(self, track: Track) -> None:
        liked = await self._liked.toggle(track)
        if self._bridge is not None:
            self._bridge.invoke_main(lambda: self._set_liked_ui(liked))
            if self._on_liked_changed is not None:
                self._bridge.invoke_main(self._on_liked_changed)

    async def _sync_liked_state(self, track: Track) -> None:
        liked = await self._liked.is_liked(track)
        if self._bridge is not None:
            self._bridge.invoke_main(lambda: self._set_liked_ui(liked))

    def _set_liked_ui(self, liked: bool) -> None:
        self._track_liked = liked
        self._update_like_button()

    def _update_like_button(self) -> None:
        liked = self._track_liked
        self._like_btn.setEnabled(self._current_track is not None)
        self._like_btn.setProperty("liked", liked)
        self._like_btn.setIcon(
            resources.load_icon("heart-filled.svg" if liked else "heart.svg")
        )
        self._like_btn.setToolTip("Убрать из любимых" if liked else "В любимые")
        self._repolish(self._like_btn)

    def _on_add_to_playlist_clicked(self) -> None:
        track = self._current_track
        if track is None or self._bridge is None:
            return
        show_add_to_playlist_menu(track, bridge=self._bridge, parent=self)

    def _on_download_clicked(self) -> None:
        track = self._current_track
        if track is None or self._bridge is None or self._music is None:
            return
        if track.downloaded:
            return
        self._bridge.schedule(self._download_track(track))

    async def _download_track(self, track: Track) -> None:
        try:
            await self._music.downloader.download_track(track)
            await self._music.downloader.download_cover(track)
            track.downloaded = True
            if self._bridge is not None:
                self._bridge.invoke_main(lambda: self._download_btn.setEnabled(False))
        except Exception:
            logger.exception("PlayerBar: download failed")

    # --------------------------------------------------- painting and theme

    def set_cinematic(self, enabled: bool) -> None:
        if self._cinematic == enabled:
            return
        self._cinematic = enabled
        self._sync_cinematic_card()
        self.update()

    def _sync_cinematic_card(self) -> None:
        self._card.setStyleSheet(_CINEMATIC_CARD_QSS if self._cinematic else "")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._cinematic:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        fade = QLinearGradient(0, 0, 0, rect.height())
        fade.setColorAt(0.0, QColor(0, 0, 0, 20))
        fade.setColorAt(0.35, QColor(0, 0, 0, 110))
        fade.setColorAt(1.0, QColor(0, 0, 0, 175))
        painter.fillRect(rect, fade)
        painter.end()

    def _on_palette(self, palette: CoverPalette) -> None:
        self._palette = palette
        self._card.update()

    def _paint_capsule(self, painter: QPainter, path: QPainterPath) -> None:
        """Поверх стекла капсулы: отсвет акцента слева и ореол вокруг Play."""
        accent = self._palette.accent
        bounds = path.boundingRect()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tint = QLinearGradient(bounds.left(), 0, bounds.right(), 0)
        start, end = QColor(accent), QColor(accent)
        start.setAlpha(0 if self._cinematic else 34)
        end.setAlpha(0)
        tint.setColorAt(0, start)
        tint.setColorAt(0.5, end)
        painter.fillPath(path, tint)
        if self._play_btn.isVisible():
            center = QPointF(
                self._play_btn.mapTo(self._card, self._play_btn.rect().center())
            )
            halo = QRadialGradient(center, HALO_RADIUS)
            glow, clear = QColor(accent), QColor(accent)
            glow.setAlpha(120)
            clear.setAlpha(0)
            halo.setColorAt(0.45, glow)
            halo.setColorAt(1.0, clear)
            painter.setClipPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(center, HALO_RADIUS, HALO_RADIUS)
        painter.restore()

    def refresh_theme(self) -> None:
        for button in self._card.findChildren(QToolButton):
            self._repolish(button)
        self._set_title_playing(self._is_playing)
        self._update_like_button()
        self._update_repeat_button(self._vm.repeat_mode)
        self._repolish(self._card)
        self._sync_cinematic_card()
        self.update()

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
