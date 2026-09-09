from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.ui.async_ui import schedule
from quantis.ui.models import TrackListModel
from quantis.ui.viewmodels.stats_vm import StatsViewModel
from quantis.ui.views.widgets.glass_panel import GlassPanel
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.views.widgets.listen_bars import ListenBars
from quantis.ui.views.widgets.track_card import TrackCardDelegate
from quantis.utils import get_ru_words_for_number


def _ru_times(count: int) -> str:
    n10 = count % 10
    n100 = count % 100
    if n10 == 1 and n100 != 11:
        word = "раз"
    elif n10 in (2, 3, 4) and n100 not in (12, 13, 14):
        word = "раза"
    else:
        word = "раз"
    return f"{count} {word}"


def _format_span(ms: int) -> str:
    """Часы до двух суток, затем дни — чтобы карточка не резала «1 д 12 ч»."""
    total_min = max(0, int(ms)) // 60_000
    if total_min < 60:
        return f"{total_min} мин"
    hours, minutes = divmod(total_min, 60)
    if hours < 48:
        return f"{hours} ч {minutes} мин" if minutes else f"{hours} ч"
    days, rest_hours = divmod(hours, 24)
    if rest_hours:
        return f"{days} д {rest_hours} ч"
    return f"{days} д"


class _MetricCard(QFrame):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statsMetric")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self._value = QLabel("—")
        self._value.setObjectName("statsMetricValue")
        self._value.setWordWrap(True)
        self._value.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._value)
        caption = QLabel(label)
        caption.setObjectName("statsMetricLabel")
        caption.setWordWrap(True)
        layout.addWidget(caption)

    def set_value(self, text: str) -> None:
        self._value.setText(text)
        self._value.setToolTip(text)


class StatsPage(QWidget):
    def __init__(
        self,
        view_model: StatsViewModel,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._bridge = bridge
        self.setObjectName("statsPage")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("homeScrollContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 20, 28, 40)
        root.setSpacing(24)

        hero = QWidget()
        hero.setObjectName("homeHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(6)
        kicker = QLabel("ТВОЯ СТАТИСТИКА")
        kicker.setObjectName("homeKicker")
        hero_layout.addWidget(kicker)
        title = QLabel("Прослушивания")
        title.setObjectName("homeGreeting")
        hero_layout.addWidget(title)
        self._subtitle = QLabel("Дослушай трек до конца — он попадёт в топ")
        self._subtitle.setObjectName("homeGreetingSub")
        self._subtitle.setWordWrap(True)
        hero_layout.addWidget(self._subtitle)
        root.addWidget(hero)

        metrics = QWidget()
        metrics.setObjectName("statsMetrics")
        self._metrics_grid = QGridLayout(metrics)
        self._metrics_grid.setContentsMargins(0, 0, 0, 0)
        self._metrics_grid.setHorizontalSpacing(12)
        self._metrics_grid.setVerticalSpacing(12)
        self._listens = _MetricCard("Прослушиваний")
        self._tracks = _MetricCard("Уникальных треков")
        self._time = _MetricCard("Время в эфире")
        self._artist = _MetricCard("Любимый артист")
        for index, card in enumerate(
            (self._listens, self._tracks, self._time, self._artist)
        ):
            self._metrics_grid.addWidget(card, 0, index)
            self._metrics_grid.setColumnStretch(index, 1)
        root.addWidget(metrics)

        chart_section = HomeSection("Топ треков", "По числу полных прослушиваний")
        chart_panel = GlassPanel()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(16, 14, 16, 14)
        self._bars = ListenBars()
        self._bars.track_activated.connect(self._on_play_most)
        chart_layout.addWidget(self._bars)
        chart_section.add_widget_block(chart_panel)
        root.addWidget(chart_section)

        lists = QWidget()
        lists_layout = QHBoxLayout(lists)
        lists_layout.setContentsMargins(0, 0, 0, 0)
        lists_layout.setSpacing(16)

        most_section = HomeSection("Чаще всего", "Самые заезженные")
        self._most_list = self._make_table(self._vm.most_model, self._on_play_most)
        most_section.add_widget_block(self._most_list)
        self._most_section = most_section
        lists_layout.addWidget(most_section, stretch=1)

        least_section = HomeSection("Реже всего", "Почти не слушались")
        self._least_list = self._make_table(self._vm.least_model, self._on_play_least)
        least_section.add_widget_block(self._least_list)
        self._least_section = least_section
        lists_layout.addWidget(least_section, stretch=1)

        root.addWidget(lists)
        root.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._vm.stats_changed.connect(self._rebuild)
        self._rebuild()

    def _make_table(self, model: TrackListModel, handler) -> QTableView:
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
        table.setItemDelegate(TrackCardDelegate(table))
        table.setMouseTracking(True)
        table.viewport().setMouseTracking(True)
        table.doubleClicked.connect(lambda index: handler(index.row()))
        model.modelReset.connect(lambda: self._sync_height(table, model))
        model.rowsInserted.connect(lambda *_: self._sync_height(table, model))
        model.rowsRemoved.connect(lambda *_: self._sync_height(table, model))
        self._sync_height(table, model)
        return table

    @staticmethod
    def _sync_height(table: QTableView, model: TrackListModel) -> None:
        rows = max(1, model.rowCount())
        table.setFixedHeight(rows * TrackCardDelegate.CARD_HEIGHT + 4)

    def _rebuild(self) -> None:
        snap = self._vm.snapshot
        summary = snap.summary
        self._listens.set_value(_ru_times(summary.total_listens))
        self._tracks.set_value(str(summary.unique_tracks))
        self._time.set_value(_format_span(summary.listened_ms))
        self._artist.set_value(summary.top_artist or "—")
        if summary.total_listens:
            self._subtitle.setText(
                f"{_ru_times(summary.total_listens)} · "
                f"{get_ru_words_for_number(summary.unique_tracks)}"
            )
        else:
            self._subtitle.setText("Дослушай трек до конца — он попадёт в топ")
        self._most_section.set_badge(str(len(snap.most)) if snap.most else "")
        self._least_section.set_badge(str(len(snap.least)) if snap.least else "")
        self._bars.set_tracks(list(snap.most))

    def _on_play_most(self, index: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_most_at(index), self._bridge)

    def _on_play_least(self, index: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_least_at(index), self._bridge)

    def set_playing_track(self, track) -> None:
        self._vm.set_playing_track(track)

    def set_accent(self, color) -> None:
        self._bars.set_accent(color)
