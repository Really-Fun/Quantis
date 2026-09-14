from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
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
from quantis.models.track import Track
from quantis.models.repeat_mode import RepeatMode
from quantis.providers.path_provider import PathProvider
from quantis.services.liked_tracks import LikedTracksService
from quantis.services.music_service import MusicService
from quantis.ui import resources
from quantis.ui.cover_prefetch import schedule_cover_prefetch
from quantis.ui.playlist_actions import show_add_to_playlist_menu
from quantis.ui.preferences import UiPreferences
from quantis.ui.ui_extensions import UiExtensionHost
from quantis.ui.viewmodels.player_vm import PlayerViewModel
from quantis.ui.views.widgets.cover_art import load_cover_pixmap
from quantis.ui.views.widgets.source_badge import paint_source_badge


class _PlayerCover(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("coverLabel")
        self.setFixedSize(56, 56)
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
    """Нижняя панель ~80px: meta | transport+seek | actions."""

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
        on_playlists_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._path_provider = path_provider
        self._bridge = bridge
        self._music = music
        self._liked = LikedTracksService()
        self._on_liked_changed = on_liked_changed
        self._on_playlists_changed = on_playlists_changed
        self._current_track: Track | None = None
        self._seeking = False
        self._is_playing = False
        self._track_liked = False
        self._plugin_buttons: list[QToolButton] = []
        self._extensions = UiExtensionHost.instance()
        self._cinematic = False
        self.setObjectName("playerDock")
        self.setFixedHeight(88)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)

        dock = QVBoxLayout(self)
        dock.setContentsMargins(10, 4, 10, 10)
        dock.setSpacing(0)

        card = QFrame()
        card.setObjectName("PlayMenu")
        self._card = card

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 10, 16, 10)
        card_layout.setSpacing(6)

        # Left: cover + meta
        self._cover = _PlayerCover()
        meta = QVBoxLayout()
        meta.setSpacing(2)
        meta.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("Выберите трек")
        self._author = QLabel("")
        self._title.setObjectName("trackTitle")
        self._author.setObjectName("trackArtist")
        self._title.setMaximumWidth(220)
        self._author.setMaximumWidth(220)
        meta.addWidget(self._title)
        meta.addWidget(self._author)

        left = QWidget()
        left.setObjectName("playerLeft")
        left.setFixedWidth(300)
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(self._cover)
        left_layout.addLayout(meta, stretch=1)

        # Center: transport + seek
        self._prev_btn = self._make_button("prev.svg", "Назад", size=40)
        self._repeat_btn = self._make_button(
            "repeat.svg",
            "Повтор плейлиста",
            size=36,
            object_name="repeatButton",
        )
        self._repeat_btn.clicked.connect(self._vm.cycle_repeat_mode)
        self._play_btn = self._make_button("play.svg", "Play", accent=True, size=40)
        self._next_btn = self._make_button("next.svg", "Далее", size=40)
        self._prev_btn.clicked.connect(self._vm.play_previous)
        self._play_btn.clicked.connect(self._vm.toggle_pause)
        self._next_btn.clicked.connect(self._vm.play_next)

        transport_host = QWidget()
        transport_host.setFixedHeight(40)
        transport = QHBoxLayout(transport_host)
        transport.setContentsMargins(0, 0, 0, 0)
        transport.setSpacing(10)
        transport.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        transport.addWidget(self._repeat_btn, 0, Qt.AlignmentFlag.AlignCenter)
        transport.addWidget(self._prev_btn, 0, Qt.AlignmentFlag.AlignCenter)
        transport.addWidget(self._play_btn, 0, Qt.AlignmentFlag.AlignCenter)
        transport.addWidget(self._next_btn, 0, Qt.AlignmentFlag.AlignCenter)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
        self._elapsed = QLabel("0:00")
        self._elapsed.setObjectName("timeLabel")
        self._elapsed.setFixedWidth(36)
        self._elapsed.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._position = QSlider(Qt.Orientation.Horizontal)
        self._position.setObjectName("seekSlider")
        self._position.setRange(0, 0)
        self._position.setFixedHeight(14)
        self._position.sliderPressed.connect(self._on_seek_start)
        self._position.sliderReleased.connect(self._on_seek_end)
        self._duration_label = QLabel("0:00")
        self._duration_label.setObjectName("timeLabel")
        self._duration_label.setFixedWidth(36)
        seek_row.addWidget(self._elapsed)
        seek_row.addWidget(self._position, stretch=1)
        seek_row.addWidget(self._duration_label)

        center = QWidget()
        center.setObjectName("playerCenter")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        center_layout.addWidget(transport_host, 0, Qt.AlignmentFlag.AlignHCenter)
        center_layout.addLayout(seek_row)

        # Right: actions
        self._like_btn = self._make_button("heart.svg", "В любимые", size=32)
        self._like_btn.clicked.connect(self._on_like_clicked)
        self._playlist_btn = self._make_button("folder.svg", "В плейлист", size=32)
        self._playlist_btn.setEnabled(False)
        self._playlist_btn.clicked.connect(self._on_add_to_playlist_clicked)
        self._download_btn = self._make_button("download.svg", "Скачать", size=32)
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._on_download_clicked)
        self._now_btn = self._make_button("radio.svg", "Now Playing", size=32)
        self._now_btn.clicked.connect(self.now_playing_toggle_requested.emit)
        self._hide_ui_btn = self._make_button(
            "hide-ui-neon.svg",
            "Скрыть интерфейс (S)",
            size=32,
        )
        self._hide_ui_btn.clicked.connect(self.hide_ui_requested.emit)
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setObjectName("volSlider")
        self._volume.setFixedWidth(72)
        self._volume.setRange(0, 100)
        self._volume.valueChanged.connect(self._vm.set_volume)

        right = QWidget()
        right.setObjectName("playerRight")
        right.setFixedWidth(300)
        self._right_layout = QHBoxLayout(right)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._right_layout.setSpacing(4)
        self._right_layout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._plugin_slot = QHBoxLayout()
        self._plugin_slot.setSpacing(2)
        self._right_layout.addLayout(self._plugin_slot)
        self._right_layout.addWidget(self._hide_ui_btn)
        self._right_layout.addWidget(self._now_btn)
        self._right_layout.addWidget(self._download_btn)
        self._right_layout.addWidget(self._playlist_btn)
        self._right_layout.addWidget(self._like_btn)
        self._right_layout.addWidget(self._volume)

        body = QGridLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(12)
        body.setColumnStretch(0, 0)
        body.setColumnStretch(1, 1)
        body.setColumnStretch(2, 0)
        body.addWidget(left, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        body.addWidget(center, 0, 1, Qt.AlignmentFlag.AlignVCenter)
        body.addWidget(right, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        card_layout.addLayout(body)
        dock.addWidget(card)

        self._extensions.player_actions_changed.connect(self._rebuild_plugin_actions)
        self._rebuild_plugin_actions()

        self._vm.track_changed.connect(self._on_track_changed)
        self._vm.is_playing_changed.connect(self._on_playing_changed)
        self._vm.position_changed.connect(self._on_position_changed)
        self._vm.duration_changed.connect(self._on_duration_changed)
        self._vm.repeat_mode_changed.connect(self._on_repeat_mode_changed)
        self._vm.volume_changed.connect(self._on_volume_changed)

        self._volume.blockSignals(True)
        saved_volume = UiPreferences().volume
        self._volume.setValue(saved_volume)
        self._volume.blockSignals(False)
        self._vm.set_volume(saved_volume)
        self._vm.sync_from_player()
        self._update_like_button()
        self._update_repeat_button(self._vm.repeat_mode)

    def _rebuild_plugin_actions(self) -> None:
        while self._plugin_slot.count():
            item = self._plugin_slot.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._plugin_buttons.clear()
        for action in self._extensions.player_actions():
            btn = QToolButton()
            btn.setObjectName("controlButton")
            btn.setProperty("plugin", True)
            btn.setIcon(action.icon or resources.load_icon("puzzle.svg"))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip(action.tooltip + " · плагин")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedSize(32, 32)
            btn.clicked.connect(action.callback)
            self._repolish(btn)
            self._plugin_slot.addWidget(btn)
            self._plugin_buttons.append(btn)

    def _make_button(
        self,
        icon_name: str,
        tooltip: str,
        *,
        accent: bool = False,
        size: int = 34,
        object_name: str = "controlButton",
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName(object_name)
        button.setProperty("accent", accent)
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

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _set_title_playing(self, playing: bool) -> None:
        self._title.setProperty("playing", playing)
        self._repolish(self._title)

    def _update_like_button(self) -> None:
        self._like_btn.setEnabled(self._current_track is not None)
        self._like_btn.setProperty("liked", self._track_liked)
        icon_name = "heart-filled.svg" if self._track_liked else "heart.svg"
        self._like_btn.setIcon(resources.load_icon(icon_name))
        self._like_btn.setToolTip(
            "Убрать из любимых" if self._track_liked else "В любимые"
        )
        self._repolish(self._like_btn)

    def _update_repeat_button(self, mode: RepeatMode) -> None:
        if mode is RepeatMode.TRACK:
            icon_name = "repeat-one.svg"
            tooltip = "Повтор трека"
            state = "track"
        else:
            icon_name = "repeat.svg"
            tooltip = "Повтор плейлиста"
            state = "playlist"
        self._repeat_btn.setIcon(resources.load_icon(icon_name))
        self._repeat_btn.setToolTip(tooltip)
        self._repeat_btn.setProperty("state", "active")
        self._repeat_btn.setProperty("repeatMode", state)
        self._repolish(self._repeat_btn)

    def _on_repeat_mode_changed(self, mode: RepeatMode) -> None:
        self._update_repeat_button(mode)

    def _apply_cover(self, track: Track) -> None:
        cover_path = Path(self._path_provider.get_cover_path(track))
        pixmap = load_cover_pixmap(cover_path, 56)
        self._cover.set_cover(
            pixmap if pixmap is not None else QPixmap(),
            str(getattr(track, "source", "") or ""),
        )

    def _on_track_changed(self, track) -> None:
        self._current_track = track
        self._title.setText(track.title)
        self._author.setText(track.author)
        self._author.setVisible(bool(track.author))
        self._apply_cover(track)
        self._download_btn.setEnabled(not bool(getattr(track, "downloaded", False)))
        self._playlist_btn.setEnabled(True)
        if self._bridge is not None and self._music is not None:
            schedule_cover_prefetch(
                [track],
                self._music.downloader,
                self._bridge,
                on_done=lambda t=track: self._apply_cover(t),
                limit=1,
            )
            self._bridge.schedule(self._sync_liked_state(track))
        else:
            self._track_liked = False
            self._update_like_button()

    async def _sync_liked_state(self, track: Track) -> None:
        liked = await self._liked.is_liked(track)
        if self._bridge is not None:
            self._bridge.invoke_main(lambda: self._set_liked_ui(liked))

    def _set_liked_ui(self, liked: bool) -> None:
        self._track_liked = liked
        self._update_like_button()

    def toggle_like(self) -> None:
        self._on_like_clicked()

    def _on_like_clicked(self) -> None:
        track = self._current_track
        if track is None or self._bridge is None:
            return
        self._bridge.schedule(self._toggle_like(track))

    def _on_add_to_playlist_clicked(self) -> None:
        track = self._current_track
        if track is None or self._bridge is None:
            return
        show_add_to_playlist_menu(
            track,
            bridge=self._bridge,
            parent=self,
            on_done=self._on_playlists_changed,
        )

    def _on_download_clicked(self) -> None:
        track = self._current_track
        if track is None or self._bridge is None or self._music is None:
            return
        if getattr(track, "downloaded", False):
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
            import logging

            logging.getLogger(__name__).exception("PlayerBar: download failed")

    async def _toggle_like(self, track: Track) -> None:
        liked = await self._liked.toggle(track)
        if self._bridge is not None:
            self._bridge.invoke_main(lambda: self._set_liked_ui(liked))
            if self._on_liked_changed is not None:
                self._bridge.invoke_main(self._on_liked_changed)

    def _on_playing_changed(self, playing: bool) -> None:
        self._is_playing = playing
        icon = "pause.svg" if playing else "play.svg"
        self._play_btn.setIcon(resources.load_icon(icon))
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
        if self._volume.value() == value:
            return
        self._volume.blockSignals(True)
        self._volume.setValue(value)
        self._volume.blockSignals(False)

    def set_cinematic(self, enabled: bool) -> None:
        if self._cinematic == enabled:
            return
        self._cinematic = enabled
        self._sync_cinematic_card()
        self.update()

    def _sync_cinematic_card(self) -> None:
        if self._cinematic:
            self._card.setStyleSheet(
                "QFrame#PlayMenu {"
                " background: rgba(0, 0, 0, 0.38);"
                " border: none;"
                "}"
            )
        else:
            self._card.setStyleSheet("")

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

    def refresh_theme(self) -> None:
        buttons = [
            self._repeat_btn,
            self._prev_btn,
            self._play_btn,
            self._next_btn,
            self._like_btn,
            self._playlist_btn,
            self._download_btn,
            self._now_btn,
            self._hide_ui_btn,
            *self._plugin_buttons,
        ]
        for button in buttons:
            self._repolish(button)
        self._set_title_playing(self._is_playing)
        self._update_like_button()
        self._update_repeat_button(self._vm.repeat_mode)
        card = self._card
        style = self.style()
        style.unpolish(card)
        style.polish(card)
        self._sync_cinematic_card()
        card.update()
        self.update()
