from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.config.credentials import yandex_token
from quantis.core.async_bridge import AsyncBridge
from quantis.models import UserPlaylist
from quantis.models.playlist import Playlist
from quantis.ui.async_ui import schedule
from quantis.ui.models import TrackListModel
from quantis.ui.playlist_actions import (
    create_playlist_and_add,
    show_add_to_playlist_menu,
)
from quantis.ui.preferences import UiPreferences
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.widgets.featured_track import FeaturedTrackPanel
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.views.widgets.playlist_card import PlaylistShelf, QuickPickShelf
from quantis.ui.views.widgets.track_card import TrackCardDelegate
from quantis.ui.views.widgets.wave_promo import WavePromoCard

_MAX_VISIBLE_TRACKS = 12
_HERO_STACK_AT = 820


class _HomeHeroCluster(QWidget):
    """Featured + волна: в ряд на широком окне, столбиком на узком."""

    def __init__(
        self,
        featured: FeaturedTrackPanel,
        wave: WavePromoCard,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("homeHeroCluster")
        self._featured = featured
        self._wave = wave
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 4, 0, 0)
        self._box.setSpacing(14)
        self._box.addWidget(featured, 5)
        self._box.addWidget(wave, 3)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.sync_layout(self.width())

    def sync_layout(self, width: int | None = None) -> None:
        if width is None:
            width = self.width()
        featured_on = not self._featured.isHidden()
        stacked = (not featured_on) or width < _HERO_STACK_AT
        direction = (
            QBoxLayout.Direction.TopToBottom
            if stacked
            else QBoxLayout.Direction.LeftToRight
        )
        if self._box.direction() != direction:
            self._box.setDirection(direction)
        if stacked:
            self._wave.setMinimumHeight(80)
            self._wave.setMaximumHeight(92)
            self._featured.setMinimumHeight(148)
            self._featured.setMaximumHeight(168)
        else:
            self._wave.setMinimumHeight(148)
            self._wave.setMaximumHeight(168)
            self._featured.setMinimumHeight(148)
            self._featured.setMaximumHeight(168)


class HomePage(QWidget):
    playlist_open_requested = Signal(object)

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
        self._layout.setContentsMargins(28, 20, 28, 40)
        self._layout.setSpacing(26)

        hero = QWidget()
        hero.setObjectName("homeHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(6)

        self._kicker = QLabel("ДЛЯ ТЕБЯ")
        self._kicker.setObjectName("homeKicker")
        hero_layout.addWidget(self._kicker)

        self._greeting = QLabel()
        self._greeting.setObjectName("homeGreeting")
        hero_layout.addWidget(self._greeting)
        self._layout.addWidget(hero)

        self._featured = FeaturedTrackPanel()
        self._featured.play_requested.connect(self._on_featured_play)

        self._wave_card = WavePromoCard()
        self._wave_card.open_requested.connect(self._on_wave_open)
        self._wave_card.play_requested.connect(self._on_wave_play)

        self._hero_cluster = _HomeHeroCluster(self._featured, self._wave_card)
        self._layout.addWidget(self._hero_cluster)

        self._quick_section = HomeSection("Быстрый доступ")
        self._quick_shelf = QuickPickShelf()
        self._quick_shelf.playlist_activated.connect(self._on_playlist)
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

        self._vm.home_changed.connect(self._rebuild)
        self._vm.recent_changed.connect(self._on_recent_changed)
        self._prefs.layout_changed.connect(self._apply_featured_visibility)
        self._apply_featured_visibility()

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
        self._greeting.setText(snap.greeting)

        has_token = bool(yandex_token())
        self._wave_card.set_state(
            available=has_token,
            track_count=snap.wave_track_count,
            source=snap.wave_source,
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
        self._sync_featured()

    def _on_recent_changed(self) -> None:
        snap = self._vm.snapshot
        self._quick_shelf.set_playlists(list(snap.quick_playlists))
        self._quick_section.setVisible(bool(snap.quick_playlists))
        recent_count = len(snap.recent_tracks)
        self._recent_empty.setVisible(recent_count == 0)
        self._sync_table_height(self._recent_list, self._vm.recent_model)
        self._sync_featured()

    def _apply_featured_visibility(self) -> None:
        # Hero — центр новой главной, панель всегда на месте.
        self._featured.setVisible(True)
        self._hero_cluster.sync_layout()
        self._sync_featured()

    def _sync_featured(self) -> None:
        if not self._featured.isVisible():
            return
        model = self._vm.recent_model
        if model.rowCount() == 0:
            self._featured.set_track(None)
            return
        track = model.data(model.index(0, 0), TrackListModel.TrackRole)
        playing = bool(model.data(model.index(0, 0), TrackListModel.IsPlayingRole))
        self._featured.set_track(track, 0, playing=playing)

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
        self._wave_card.set_state(
            available=True,
            track_count=self._vm.snapshot.wave_track_count,
            loading=True,
        )
        playlist = await self._vm.open_wave()
        if playlist is None or not len(playlist):
            self._wave_card.set_state(
                available=bool(yandex_token()),
                track_count=0,
                error="Не удалось загрузить волну. Проверь токен Yandex.",
            )
            return
        self._wave_card.set_state(
            available=True,
            track_count=len(playlist),
            source=getattr(playlist, "source", "yandex"),
        )
        self.playlist_open_requested.emit(playlist)

    async def _play_wave_async(self) -> None:
        self._wave_card.set_state(
            available=True,
            track_count=self._vm.snapshot.wave_track_count,
            loading=True,
        )
        await self._vm.play_wave()
        wave = getattr(self._vm, "_wave_playlist", None)
        count = len(wave) if wave is not None else self._vm.snapshot.wave_track_count
        self._wave_card.set_state(
            available=bool(yandex_token()),
            track_count=count,
            source=self._vm.snapshot.wave_source,
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
        self._sync_featured()
