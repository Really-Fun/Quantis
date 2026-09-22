from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.ui.async_ui import schedule
from quantis.ui.playlist_actions import show_add_to_playlist_menu
from quantis.ui.viewmodels.search_vm import SearchViewModel
from quantis.ui.views.widgets.glass_panel import GlassPanel
from quantis.ui.views.widgets.track_card import TrackCardDelegate


class SearchPage(QWidget):
    def __init__(
        self,
        view_model: SearchViewModel,
        bridge: AsyncBridge | None = None,
        *,
        on_playlists_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._bridge = bridge
        self._on_playlists_changed = on_playlists_changed
        self.setObjectName("searchPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(0)

        panel = GlassPanel()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 16)
        panel_layout.setSpacing(12)

        # ── Строка поиска + кнопка расширенного режима ────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self._query = QLineEdit()
        self._query.setObjectName("searchInput")
        self._query.setPlaceholderText("Трек, артист, альбом или ссылка…")
        self._query.setClearButtonEnabled(True)
        self._query.textChanged.connect(self._vm.search)
        self._query.returnPressed.connect(self._trigger_search)
        search_row.addWidget(self._query, stretch=1)

        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setObjectName("advancedToggle")
        self._advanced_toggle.setText("Расширенный")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._advanced_toggle.toggled.connect(self._on_advanced_toggled)
        search_row.addWidget(self._advanced_toggle)

        panel_layout.addLayout(search_row)

        # ── Фильтры-источники ─────────────────────────────────────────────
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        for key, label in (
            ("all", "Все"),
            ("yandex", "Яндекс"),
            ("youtube", "YouTube"),
            ("soundcloud", "SoundCloud"),
        ):
            chip = QToolButton()
            chip.setObjectName("sourceFilterChip")
            chip.setText(label)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setProperty("filterKey", key)
            if key == "all":
                chip.setChecked(True)
            self._filter_group.addButton(chip)
            filters.addWidget(chip)
            chip.clicked.connect(
                lambda checked=False, k=key: self._vm.set_source_filter(k)
            )
        filters.addStretch()
        panel_layout.addLayout(filters)

        # ── Панель расширенного поиска (скрыта по умолчанию) ───────────────
        self._advanced_panel = self._build_advanced_panel()
        self._advanced_panel.setVisible(False)
        panel_layout.addWidget(self._advanced_panel)

        # ── Статус ────────────────────────────────────────────────────────
        self._status = QLabel("")
        self._status.setObjectName("searchStatus")
        panel_layout.addWidget(self._status)

        # ── Список результатов ─────────────────────────────────────────────
        self._list = QTableView()
        self._list.setObjectName("trackList")
        self._list.setModel(self._vm.model)
        self._list.verticalHeader().hide()
        self._list.horizontalHeader().hide()
        self._list.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._list.verticalHeader().setDefaultSectionSize(TrackCardDelegate.CARD_HEIGHT)
        self._list.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._list.setShowGrid(False)
        self._list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setItemDelegate(
            TrackCardDelegate(self._list, on_download=self._on_download)
        )
        self._list.setMouseTracking(True)
        self._list.viewport().setMouseTracking(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.doubleClicked.connect(self._on_play_index)
        panel_layout.addWidget(self._list, stretch=1)

        layout.addWidget(panel, stretch=1)

        self._vm.loading_changed.connect(self._on_loading)
        self._vm.error_occurred.connect(self._on_error)
        self._vm.results_changed.connect(self._on_results)
        self._vm.status_message.connect(self._status.setText)

    # ──────────────────────────────────────────────────────────────────────
    # Построение панели расширенного поиска
    # ──────────────────────────────────────────────────────────────────────
    def _build_advanced_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("advancedPanel")

        grid = QGridLayout(panel)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        title = QLabel("Расширенный поиск")
        title.setObjectName("advancedTitle")
        grid.addWidget(title, 0, 0, 1, 3)

        self._adv_url = QLineEdit()
        self._adv_url.setPlaceholderText(
            "Ссылка на трек (YouTube, Yandex Music или SoundCloud)"
        )
        self._adv_url.setObjectName("advancedField")

        self._adv_track_id = QLineEdit()
        self._adv_track_id.setPlaceholderText("ID трека")
        self._adv_track_id.setObjectName("advancedField")

        self._adv_source = QComboBox()
        self._adv_source.setObjectName("advancedSort")
        self._adv_source.addItem("Яндекс", "yandex")
        self._adv_source.addItem("YouTube", "youtube")
        self._adv_source.addItem("SoundCloud", "soundcloud")

        grid.addWidget(self._labeled("Ссылка", self._adv_url), 1, 0, 1, 3)
        grid.addWidget(self._labeled("ID трека", self._adv_track_id), 2, 0)
        grid.addWidget(self._labeled("Источник", self._adv_source), 2, 1, 1, 2)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()

        reset_btn = QPushButton("Сбросить")
        reset_btn.setObjectName("advancedReset")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_advanced)
        buttons.addWidget(reset_btn)

        apply_btn = QPushButton("Найти")
        apply_btn.setObjectName("advancedApply")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._run_advanced_search)
        buttons.addWidget(apply_btn)

        grid.addLayout(buttons, 3, 0, 1, 3)

        for field in (self._adv_url, self._adv_track_id):
            field.returnPressed.connect(self._run_advanced_search)

        return panel

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QWidget:
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        label = QLabel(text)
        label.setObjectName("advancedFieldLabel")
        box.addWidget(label)
        box.addWidget(widget)
        return container

    # ──────────────────────────────────────────────────────────────────────
    # Логика расширенного поиска
    # ──────────────────────────────────────────────────────────────────────
    def _on_advanced_toggled(self, checked: bool) -> None:
        self._advanced_panel.setVisible(checked)
        if checked:
            self._adv_url.setFocus(Qt.FocusReason.OtherFocusReason)

    def _reset_advanced(self) -> None:
        self._adv_url.clear()
        self._adv_track_id.clear()
        self._adv_source.setCurrentIndex(0)

    def _collect_advanced_filters(self) -> dict:
        return {
            "url": self._adv_url.text().strip() or None,
            "track_id": self._adv_track_id.text().strip() or None,
            "source": self._adv_source.currentData(),
        }

    def _run_advanced_search(self) -> None:
        filters = self._collect_advanced_filters()
        result = self._vm.search_advanced(**filters)
        # search_advanced может быть корутиной — тогда планируем через bridge
        if result is not None and self._bridge is not None:
            schedule(result, self._bridge)

    def _trigger_search(self) -> None:
        if self._advanced_toggle.isChecked():
            self._run_advanced_search()
        else:
            self._vm.search_now()

    # ──────────────────────────────────────────────────────────────────────
    # События окна / модели
    # ──────────────────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._query.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._query.text().strip():
            self._trigger_search()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._list.doItemsLayout()

    def _on_loading(self, loading: bool) -> None:
        if loading and not self._status.text():
            self._status.setText("Ищем…")

    def _on_error(self, message: str) -> None:
        self._status.setText(message)

    def _on_results(self) -> None:
        self._list.scheduleDelayedItemsLayout()
        self._list.viewport().update()

    def _on_play_index(self, index) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_track_at(index.row()), self._bridge)

    def _on_download(self, row: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.download_track_at(row), self._bridge)

    def _on_context_menu(self, pos) -> None:
        if self._bridge is None:
            return
        index = self._list.indexAt(pos)
        if not index.isValid():
            return
        track = self._vm.model.get_track(index.row())
        if track is None:
            return
        show_add_to_playlist_menu(
            track,
            bridge=self._bridge,
            parent=self,
            on_done=self._on_playlists_changed,
        )
