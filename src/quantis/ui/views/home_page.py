from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QStyle,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track, UserPlaylist
from quantis.models.playlist import Playlist, RecentlyPlayedPlaylist
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
from quantis.ui.views.widgets.page_layout import PAGE_MARGINS
from quantis.ui.views.widgets.playlist_card import PlaylistShelf, QuickPickShelf
from quantis.ui.views.widgets.track_card import TrackCardDelegate
from quantis.ui.views.widgets.wave_card import WaveCard

_MAX_VISIBLE_TRACKS = 6
"""Строк в «Недавнем» и «Рекомендациях»: остальное — по «Все» и «Слушать»."""
_TWO_COLUMNS_MIN = 880
"""Уже этого «Недавнее» и «Рекомендации» встают друг под другом."""
_SIDE_MARGIN = (PAGE_MARGINS[0] + PAGE_MARGINS[2]) // 2
"""Среднее поле слева/справа — для расчёта ширины."""
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
    wave_page_requested = Signal()
    """«Настроения» на карточке волны — страница «Моя волна»."""

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
        self._layout.setContentsMargins(
            PAGE_MARGINS[0], PAGE_MARGINS[1], PAGE_MARGINS[2], 40
        )
        self._layout.setSpacing(26)

        # Сцена «Сейчас играет» и справа «Дальше». Пока очередь пуста, на месте
        # «Дальше» карточка «Моя волна» с настроениями: пустая рамка ничего не
        # давала, а волна так видна с первого экрана.
        self._now_track: Track | None = None
        self._playing = False
        # «Дальше» справа от сцены, а на узком окне — под ней (_relayout_stage)
        stage_row = QGridLayout()
        stage_row.setSpacing(_STAGE_GAP)
        self._stage_row = stage_row
        self._up_next_below: bool | None = None
        self._side: QWidget | None = None
        self._queue_elsewhere = False
        self._stage = NowPlayingStage()
        self._stage.resume_requested.connect(lambda: self._on_featured_play(0))
        self._stage.wave_requested.connect(self._on_wave_play)
        self._stage.search_requested.connect(self.search_requested.emit)
        stage_row.addWidget(self._stage, 0, 0, Qt.AlignmentFlag.AlignTop)
        self._up_next = UpNextPanel()
        self._up_next.track_activated.connect(self.up_next_activated.emit)
        self._up_next.queue_requested.connect(self.queue_requested.emit)
        self._wave_card = WaveCard()
        self._wave_card.play_requested.connect(self._on_wave_play)
        self._wave_card.open_requested.connect(self.wave_page_requested.emit)
        self._wave_card.mood_activated.connect(self._on_wave_mood)
        self._layout.addLayout(stage_row)

        self._quick_section = HomeSection("Быстрый доступ")
        self._quick_shelf = QuickPickShelf()
        self._quick_shelf.playlist_activated.connect(self._on_playlist)
        self._quick_shelf.wave_play_requested.connect(self._on_wave_play)
        self._quick_section.add_widget_block(self._quick_shelf)
        self._layout.addWidget(self._quick_section)

        self._recommend_section = HomeSection(
            "Рекомендации",
            "5 треков с YouTube · в конце подгрузим ещё",
        )
        listen_btn = QToolButton()
        listen_btn.setObjectName("homeSectionAction")
        listen_btn.setText("Слушать все")
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

        # Подзаголовок и у «Недавнего»: колонки рядом, заголовки — на одной линии.
        self._recent_section = HomeSection("Недавнее", "Последние треки из истории")
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
        self._all_recent_btn = all_recent = QToolButton()
        all_recent.setObjectName("homeSectionAction")
        all_recent.setText("Вся история")
        all_recent.setCursor(Qt.CursorShape.PointingHandCursor)
        all_recent.setToolTip("Вся история прослушивания")
        all_recent.clicked.connect(self._on_recent_open)
        self._recent_section.set_header_action(all_recent)

        # «Недавнее» и «Рекомендации» рядом: на всю ширину у строк оставалось
        # по 800 px пустоты. На узком окне — друг под другом (_relayout_lists).
        lists = QWidget()
        lists.setObjectName("homeTrackColumns")
        self._lists_grid = QGridLayout(lists)
        self._lists_grid.setContentsMargins(0, 0, 0, 0)
        self._lists_grid.setHorizontalSpacing(_STAGE_GAP)
        self._lists_grid.setVerticalSpacing(26)
        self._lists_side_by_side: bool | None = None
        self._layout.addWidget(lists)

        self._library_section = HomeSection("Плейлисты")
        create_btn = QToolButton()
        create_btn.setObjectName("homeSectionAction")
        create_btn.setText("+ Плейлист")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setToolTip("Создать плейлист")
        create_btn.clicked.connect(self._on_create_playlist)
        self._all_playlists_btn = QToolButton()
        self._all_playlists_btn.setObjectName("homeSectionAction")
        self._all_playlists_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        actions = QWidget()
        actions_row = QHBoxLayout(actions)
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)
        actions_row.addWidget(self._all_playlists_btn)
        actions_row.addWidget(create_btn)
        self._library_section.set_header_action(actions)
        self._playlist_shelf = PlaylistShelf()
        self._playlist_shelf.playlist_activated.connect(self._on_playlist)
        self._all_playlists_btn.clicked.connect(
            lambda: self._playlist_shelf.set_expanded(not self._playlist_shelf.expanded)
        )
        self._playlist_shelf.expanded_changed.connect(self._sync_all_playlists_btn)
        self._playlist_shelf.ribbon.scroll_area.horizontalScrollBar().rangeChanged.connect(
            self._sync_all_playlists_btn
        )
        self._library_section.add_widget_block(self._playlist_shelf)
        self._layout.addWidget(self._library_section)

        self._layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self._scroll = scroll

        self._vm.home_changed.connect(self._rebuild)
        self._vm.recent_changed.connect(self._on_recent_changed)
        self._vm.wave_moods_changed.connect(self._sync_wave_moods)
        self._relayout_lists()
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

        # Без токена Яндекса волна играет с YouTube — плитка доступна всегда.
        self._set_wave_state(
            available=True,
            track_count=snap.wave_track_count,
            loading=not snap.wave_ready,
        )

        self._quick_shelf.set_playlists(list(snap.quick_playlists))
        self._quick_section.setVisible(bool(snap.quick_playlists))

        user_playlists = [
            playlist
            for playlist in snap.library_playlists
            if isinstance(playlist, UserPlaylist)
        ]
        self._playlist_shelf.set_playlists(user_playlists)
        self._sync_all_playlists_btn()

        rec_count = len(snap.recommendation_tracks)
        self._recommend_empty.setVisible(rec_count == 0)
        recent_count = len(snap.recent_tracks)
        self._recent_empty.setVisible(recent_count == 0)
        self._all_recent_btn.setVisible(recent_count > 0)
        self._sync_table_height(self._recommend_list, self._vm.recommendation_model)
        self._sync_table_height(self._recent_list, self._vm.recent_model)
        self._sync_stage()

    def _on_recent_changed(self) -> None:
        snap = self._vm.snapshot
        self._quick_shelf.set_playlists(list(snap.quick_playlists))
        self._quick_section.setVisible(bool(snap.quick_playlists))
        recent_count = len(snap.recent_tracks)
        self._recent_empty.setVisible(recent_count == 0)
        self._all_recent_btn.setVisible(recent_count > 0)
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

    def set_queue_elsewhere(self, shown: bool) -> None:
        """Очередь видна в правой панели окна: «Дальше» у сцены прячем."""
        if self._queue_elsewhere == shown:
            return
        self._queue_elsewhere = shown
        self._side = None  # пересобрать ряд сцены
        self._relayout_stage()

    def set_eco(self, enabled: bool) -> None:
        self._stage.set_eco(enabled)

    @property
    def stage(self) -> NowPlayingStage:
        return self._stage

    @property
    def up_next(self) -> UpNextPanel:
        return self._up_next

    @property
    def wave_card(self) -> WaveCard:
        return self._wave_card

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
        self._relayout_lists()

    def _relayout_lists(self) -> None:
        side_by_side = self.width() - 2 * _SIDE_MARGIN >= _TWO_COLUMNS_MIN
        if side_by_side == self._lists_side_by_side:
            return
        self._lists_side_by_side = side_by_side
        grid = self._lists_grid
        for section in (self._recent_section, self._recommend_section):
            grid.removeWidget(section)
        top = Qt.AlignmentFlag.AlignTop
        grid.addWidget(self._recent_section, 0, 0, top)
        if side_by_side:
            grid.addWidget(self._recommend_section, 0, 1, top)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
        else:
            grid.addWidget(self._recommend_section, 1, 0, top)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 0)

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
        if count and self._queue_elsewhere:
            # очередь открыта в правой панели — сцене не нужен второй «Дальше»
            self._stage.set_cover_size(
                min(int((width - _STAGE_TEXT_MIN) / per_cover), by_height)
            )
            self._up_next.hide()
            self._wave_card.hide()
            return
        side = self._up_next if count else self._wave_card
        other = self._wave_card if count else self._up_next
        other.hide()
        side.show()
        if below:
            side.setMinimumWidth(0)
            side.setMaximumWidth(16777215)
            if count:
                cols = 2 if width >= 560 else 1
                rows = max(1, -(-min(4, count) // cols))
                side.setFixedHeight(UpNextPanel.height_for(rows))
            else:
                side.setFixedHeight(side.sizeHint().height())
        else:
            rows = min(_UP_NEXT_BESIDE_ROWS, max(1, count))
            side.setFixedSize(
                panel_w,
                max(self._stage.height(), UpNextPanel.height_for(rows)),
            )
        if below == self._up_next_below and side is self._side:
            return
        self._up_next_below = below
        for widget in (self._up_next, self._wave_card):
            self._stage_row.removeWidget(widget)
        self._side = side
        if below:
            self._stage_row.addWidget(side, 1, 0)
        else:
            self._stage_row.addWidget(side, 0, 1, Qt.AlignmentFlag.AlignTop)
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
        self._set_wave_state(
            available=True,
            track_count=self._vm.snapshot.wave_track_count,
            loading=True,
        )
        playlist = await self._vm.open_wave()
        if playlist is None or not len(playlist):
            self._set_wave_state(
                available=True,
                track_count=0,
                error="Не удалось загрузить волну",
            )
            return
        self._set_wave_state(available=True, track_count=len(playlist))
        self.playlist_open_requested.emit(playlist)

    async def _play_wave_async(self) -> None:
        self._set_wave_state(
            available=True,
            track_count=self._vm.snapshot.wave_track_count,
            loading=True,
        )
        await self._vm.play_wave()
        wave = getattr(self._vm, "_wave_playlist", None)
        count = len(wave) if wave is not None else self._vm.snapshot.wave_track_count
        self._set_wave_state(available=True, track_count=count)

    def _set_wave_state(self, **state) -> None:
        """Состояние волны — и на плитке быстрого доступа, и на карточке."""
        self._quick_shelf.set_wave_state(**state)
        self._wave_card.set_state(
            track_count=int(state.get("track_count") or 0),
            loading=bool(state.get("loading")),
            error=str(state.get("error") or ""),
        )

    def _sync_wave_moods(self) -> None:
        moods = self._vm.wave_moods
        self._wave_card.set_moods(
            moods,
            active_seeds=self._vm.active_wave_seeds,
            busy=self._vm.wave_mood_busy,
        )

    def _on_wave_mood(self, mood) -> None:
        if self._bridge is None:
            return
        schedule(self._vm.play_wave_mood(mood), self._bridge)

    def _sync_all_playlists_btn(self, *_: object) -> None:
        shelf = self._playlist_shelf
        expanded = shelf.expanded
        self._all_playlists_btn.setText(
            "Свернуть" if expanded else f"Все ({shelf.count()})"
        )
        self._all_playlists_btn.setToolTip(
            "Показать одной лентой" if expanded else "Показать все плейлисты сеткой"
        )
        ribbon = shelf.ribbon
        overflows = ribbon.scroll_area.horizontalScrollBar().maximum() > 0
        self._all_playlists_btn.setVisible(expanded or overflows)

    def _on_recent_open(self) -> None:
        tracks = self._vm.recent_model.all_tracks()
        if tracks:
            self.playlist_open_requested.emit(RecentlyPlayedPlaylist(tracks=tracks))

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

        create_playlist_and_add(None, self._bridge, self)

    def _on_track_context(self, table: QTableView, model: TrackListModel, pos) -> None:
        if self._bridge is None:
            return
        index = table.indexAt(pos)
        if not index.isValid():
            return
        track = model.get_track(index.row())
        if track is None:
            return

        show_add_to_playlist_menu(track, bridge=self._bridge, parent=self)

    def refresh_featured(self) -> None:
        self._sync_stage()
