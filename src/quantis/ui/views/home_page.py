from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QStyle,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.config.credentials import yandex_token
from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track, UserPlaylist
from quantis.models.playlist import Playlist
from quantis.ui.async_ui import schedule
from quantis.ui.models import TrackListModel
from quantis.ui.playlist_actions import (
    create_playlist_and_add,
    show_add_to_playlist_menu,
)
from quantis.ui.preferences import UiPreferences
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.views.widgets.now_playing_stage import (
    NowPlayingStage,
    UpNextItem,
    UpNextPanel,
)
from quantis.ui.views.widgets.playlist_card import PlaylistShelf, QuickPickShelf
from quantis.ui.views.widgets.track_card import TrackCardDelegate

_MAX_VISIBLE_TRACKS = 12
_SIDE_MARGIN = 28
_STAGE_GAP = 24
_STAGE_TEXT_MIN = 240
"""Колонка названия трека — уже этого сцена не сжимается."""
_STAGE_SHARE = 0.5
"""Сцена — не выше половины страницы: под ней должны быть видны полки."""
_UP_NEXT_BESIDE_ROWS = 3


class HomePage(QWidget):
    playlist_open_requested = Signal(object)
    search_requested = Signal()
    queue_requested = Signal()
    """«Вся очередь» на панели «Дальше» — открыть играющий плейлист."""
    up_next_activated = Signal(int)
    """Трек из «Дальше»: индекс в играющем плейлисте."""

    def __init__(
        self,
        view_model: HomeViewModel,
        bridge: AsyncBridge | None = None,
        preferences: UiPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._bridge = bridge
        self._prefs = preferences or UiPreferences()
        self.setObjectName("homePage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content.setObjectName("homeScrollContent")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(_SIDE_MARGIN, 20, _SIDE_MARGIN, 40)
        self._layout.setSpacing(26)

        # Сцена «Сейчас играет» и «Дальше». «Продолжить слушать» — состояние
        # сцены, «Моя волна» — первая плитка быстрого доступа.
        self._now_track: Track | None = None
        self._playing = False
        # «Дальше» справа от сцены, а на узком окне — под ней (_relayout_stage)
        stage_row = QGridLayout()
        stage_row.setSpacing(_STAGE_GAP)
        self._stage_row = stage_row
        self._up_next_below: bool | None = None
        self._stage = NowPlayingStage()
        self._stage.resume_requested.connect(lambda: self._on_featured_play(0))
        self._stage.wave_requested.connect(self._on_wave_play)
        self._stage.search_requested.connect(self.search_requested.emit)
        stage_row.addWidget(self._stage, 0, 0, Qt.AlignmentFlag.AlignTop)
        self._up_next = UpNextPanel()
        self._up_next.track_activated.connect(self.up_next_activated.emit)
        self._up_next.queue_requested.connect(self.queue_requested.emit)
        self._layout.addLayout(stage_row)

        self._quick_section = HomeSection("Быстрый доступ")
        self._quick_shelf = QuickPickShelf()
        self._quick_shelf.playlist_activated.connect(self._on_playlist)
        self._quick_shelf.wave_play_requested.connect(self._on_wave_play)
        self._quick_section.add_widget_block(self._quick_shelf)
        self._layout.addWidget(self._quick_section)

        self._library_section = HomeSection("Плейлисты")
        create_btn = QToolButton()
        create_btn.setObjectName("homeSectionAction")
        create_btn.setText("+ Плейлист")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setToolTip("Создать плейлист")
        create_btn.clicked.connect(self._on_create_playlist)
        self._library_section.set_header_action(create_btn)
        self._playlist_shelf = PlaylistShelf()
        self._playlist_shelf.playlist_activated.connect(self._on_playlist)
        self._library_section.add_widget_block(self._playlist_shelf)
        self._layout.addWidget(self._library_section)

        self._recommend_section = HomeSection(
            "Рекомендации",
            "5 треков с YouTube · в конце подгрузим ещё",
        )
        listen_btn = QToolButton()
        listen_btn.setObjectName("homeSectionAction")
        listen_btn.setText("▶ Слушать")
        listen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        listen_btn.setToolTip("Слушать поток рекомендаций")
        listen_btn.clicked.connect(self._on_recommendations_play)
        self._recommend_section.set_header_action(listen_btn)
        self._recommend_list = self._make_track_table(self._vm.recommendation_model)
        self._recommend_empty = QLabel("Включи любой трек — соберём поток из истории")
        self._recommend_empty.setObjectName("homeEmptyHint")
        self._recommend_empty.setWordWrap(True)
        rec_host = QWidget()
        rec_host_layout = QVBoxLayout(rec_host)
        rec_host_layout.setContentsMargins(0, 0, 0, 0)
        rec_host_layout.setSpacing(0)
        rec_host_layout.addWidget(self._recommend_list)
        rec_host_layout.addWidget(self._recommend_empty)
        self._recommend_section.add_widget_block(rec_host)
        self._layout.addWidget(self._recommend_section)

        self._recent_section = HomeSection("Недавнее")
        self._recent_list = self._make_track_table(
            self._vm.recent_model,
            on_download=self._on_download_recent,
        )
        self._recent_empty = QLabel("Пока тихо — самое время начать")
        self._recent_empty.setObjectName("homeEmptyHint")
        self._recent_empty.setWordWrap(True)
        recent_host = QWidget()
        recent_host_layout = QVBoxLayout(recent_host)
        recent_host_layout.setContentsMargins(0, 0, 0, 0)
        recent_host_layout.setSpacing(0)
        recent_host_layout.addWidget(self._recent_list)
        recent_host_layout.addWidget(self._recent_empty)
        self._recent_section.add_widget_block(recent_host)
        self._layout.addWidget(self._recent_section)

        self._layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self._scroll = scroll

        self._vm.home_changed.connect(self._rebuild)
        self._vm.recent_changed.connect(self._on_recent_changed)
        self._sync_stage()

    def _make_track_table(
        self,
        model: TrackListModel,
        *,
        on_download=None,
    ) -> QTableView:
        table = QTableView()
        table.setObjectName("homeTrackList")
        table.setModel(model)
        table.verticalHeader().hide()
        table.horizontalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.verticalHeader().setDefaultSectionSize(TrackCardDelegate.CARD_HEIGHT)
        table.setShowGrid(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setItemDelegate(TrackCardDelegate(table, on_download=on_download))
        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table, m=model: self._on_track_context(t, m, pos)
        )
        table.doubleClicked.connect(
            lambda index, m=model: self._on_play_model(m, index.row()),
        )
        model.modelReset.connect(lambda: self._sync_table_height(table, model))
        model.rowsInserted.connect(lambda *_: self._sync_table_height(table, model))
        model.rowsRemoved.connect(lambda *_: self._sync_table_height(table, model))
        self._sync_table_height(table, model)
        return table

    @staticmethod
    def _sync_table_height(table: QTableView, model: TrackListModel) -> None:
        rows = min(model.rowCount(), _MAX_VISIBLE_TRACKS)
        if rows <= 0:
            table.setFixedHeight(0)
            table.hide()
            return
        table.show()
        table.setFixedHeight(rows * TrackCardDelegate.CARD_HEIGHT + 4)

    def _rebuild(self) -> None:
        snap = self._vm.snapshot
        self._stage.set_greeting(snap.greeting)

        has_token = bool(yandex_token())
        self._quick_shelf.set_wave_state(
            available=has_token,
            track_count=snap.wave_track_count,
            loading=has_token and not snap.wave_ready,
        )

        self._quick_shelf.set_playlists(list(snap.quick_playlists))
        self._quick_section.setVisible(bool(snap.quick_playlists))

        user_playlists = [
            playlist
            for playlist in snap.library_playlists
            if isinstance(playlist, UserPlaylist)
        ]
        self._playlist_shelf.set_playlists(user_playlists)

        rec_count = len(snap.recommendation_tracks)
        self._recommend_empty.setVisible(rec_count == 0)
        recent_count = len(snap.recent_tracks)
        self._recent_empty.setVisible(recent_count == 0)
        self._sync_table_height(self._recommend_list, self._vm.recommendation_model)
        self._sync_table_height(self._recent_list, self._vm.recent_model)
        self._sync_stage()

    def _on_recent_changed(self) -> None:
        snap = self._vm.snapshot
        self._quick_shelf.set_playlists(list(snap.quick_playlists))
        self._quick_section.setVisible(bool(snap.quick_playlists))
        recent_count = len(snap.recent_tracks)
        self._recent_empty.setVisible(recent_count == 0)
        self._sync_table_height(self._recent_list, self._vm.recent_model)
        self._sync_stage()

    # --- сцена -----------------------------------------------------------

    def set_now_playing(self, track: Track | None) -> None:
        """Трек плеера (None — ничего не выбрано)."""
        self._now_track = track
        self._sync_stage()

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self._stage.set_playing(playing)

    def set_up_next(self, items: list[UpNextItem]) -> None:
        self._up_next.set_items(items)
        self._relayout_stage()

    def set_eco(self, enabled: bool) -> None:
        self._stage.set_eco(enabled)

    @property
    def stage(self) -> NowPlayingStage:
        return self._stage

    def _sync_stage(self) -> None:
        if self._now_track is not None:
            self._stage.set_track(self._now_track, mode="playing")
            self._stage.set_playing(self._playing)
            return
        model = self._vm.recent_model
        last = (
            model.data(model.index(0, 0), TrackListModel.TrackRole)
            if model.rowCount()
            else None
        )
        self._stage.set_track(last, mode="resume" if last is not None else "empty")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout_stage()

    def _relayout_stage(self) -> None:
        """Размер сцены и место «Дальше» — от ширины и высоты страницы.

        На Windows со 125–150 % окно в логических пикселях маленькое
        (1920×1080 при 150 % — 1280×720): сцена ужимается, пока колонке текста
        хватает места, дальше «Дальше» уходит под сцену."""
        bar = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        width = self.width() - 2 * _SIDE_MARGIN - bar
        stage = NowPlayingStage
        per_cover = (stage.COVER + stage.OUT + 40) / stage.COVER
        by_height = int(self.height() * _STAGE_SHARE) - stage.height_for(0)
        panel_w = max(UpNextPanel.MIN_W, min(UpNextPanel.W, int(width * 0.28)))
        stage_min = stage.MIN_COVER * per_cover + _STAGE_TEXT_MIN
        below = width - panel_w - _STAGE_GAP < stage_min
        stage_w = width if below else width - panel_w - _STAGE_GAP
        by_width = int((stage_w - _STAGE_TEXT_MIN) / per_cover)
        self._stage.set_cover_size(min(by_width, by_height))

        count = len(self._up_next.items())
        # под сценой пустая очередь только отнимает высоту
        self._up_next.setVisible(not below or count > 0)
        if below:
            self._up_next.setMinimumWidth(0)
            self._up_next.setMaximumWidth(16777215)
            cols = 2 if width >= 560 else 1
            rows = max(1, -(-min(4, count) // cols))
            self._up_next.setFixedHeight(UpNextPanel.height_for(rows))
        else:
            rows = min(_UP_NEXT_BESIDE_ROWS, max(1, count))
            self._up_next.setFixedSize(
                panel_w,
                max(self._stage.height(), UpNextPanel.height_for(rows)),
            )
        if below == self._up_next_below:
            return
        self._up_next_below = below
        self._stage_row.removeWidget(self._up_next)
        if below:
            self._stage_row.addWidget(self._up_next, 1, 0)
        else:
            self._stage_row.addWidget(self._up_next, 0, 1, Qt.AlignmentFlag.AlignTop)
        self._stage_row.setColumnStretch(0, 1)
        self._stage_row.setColumnStretch(1, 0)

    def _on_playlist(self, playlist: Playlist) -> None:
        if getattr(playlist, "kind", None) == "wave":
            self._on_wave_open()
            return
        if getattr(playlist, "kind", None) == "recommendations":
            self._on_recommendations_open()
            return
        self.playlist_open_requested.emit(self._vm.resolve_playlist(playlist))

    def _on_wave_open(self) -> None:
        if self._bridge is None:
            return
        schedule(self._open_wave_async(), self._bridge)

    def _on_wave_play(self) -> None:
        if self._bridge is None:
            return
        schedule(self._play_wave_async(), self._bridge)

    async def _open_wave_async(self) -> None:
        self._quick_shelf.set_wave_state(
            available=True,
            track_count=self._vm.snapshot.wave_track_count,
            loading=True,
        )
        playlist = await self._vm.open_wave()
        if playlist is None or not len(playlist):
            self._quick_shelf.set_wave_state(
                available=bool(yandex_token()),
                track_count=0,
                error="Не удалось загрузить волну",
            )
            return
        self._quick_shelf.set_wave_state(available=True, track_count=len(playlist))
        self.playlist_open_requested.emit(playlist)

    async def _play_wave_async(self) -> None:
        self._quick_shelf.set_wave_state(
            available=True,
            track_count=self._vm.snapshot.wave_track_count,
            loading=True,
        )
        await self._vm.play_wave()
        wave = getattr(self._vm, "_wave_playlist", None)
        count = len(wave) if wave is not None else self._vm.snapshot.wave_track_count
        self._quick_shelf.set_wave_state(
            available=bool(yandex_token()), track_count=count
        )

    def _on_recommendations_open(self) -> None:
        if self._bridge is None:
            return
        schedule(self._open_recommendations_async(), self._bridge)

    def _on_recommendations_play(self) -> None:
        if self._bridge is None:
            return
        schedule(self._play_recommendations_async(), self._bridge)

    async def _open_recommendations_async(self) -> None:
        playlist = await self._vm.open_recommendations()
        if playlist is None or not len(playlist):
            return
        self.playlist_open_requested.emit(playlist)

    async def _play_recommendations_async(self) -> None:
        await self._vm.play_recommendations()

    def _on_play_model(self, model: TrackListModel, row: int) -> None:
        if self._bridge is None:
            return
        if model is self._vm.recent_model:
            schedule(self._vm.play_recent_at(row), self._bridge)
        else:
            schedule(self._vm.play_recommendation_at(row), self._bridge)

    def _on_featured_play(self, index: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_recent_at(index), self._bridge)

    def _on_download_recent(self, row: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.download_recent_at(row), self._bridge)

    def _on_create_playlist(self) -> None:
        if self._bridge is None:
            return

        def done() -> None:
            schedule(self._vm.refresh_user_playlists(self._bridge), self._bridge)

        create_playlist_and_add(None, self._bridge, self, on_done=done)

    def _on_track_context(self, table: QTableView, model: TrackListModel, pos) -> None:
        if self._bridge is None:
            return
        index = table.indexAt(pos)
        if not index.isValid():
            return
        track = model.get_track(index.row())
        if track is None:
            return

        def done() -> None:
            schedule(self._vm.refresh_user_playlists(self._bridge), self._bridge)

        show_add_to_playlist_menu(track, bridge=self._bridge, parent=self, on_done=done)

    def refresh_featured(self) -> None:
        self._sync_stage()
