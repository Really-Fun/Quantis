from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.database.sync_history import ListeningRhythm
from quantis.models import Track
from quantis.ui.async_ui import schedule
from quantis.ui.viewmodels.stats_vm import StatsViewModel
from quantis.ui.views.widgets.cover_art import (
    CoverDecoder,
    paint_rounded_cover,
    request_track_cover,
)
from quantis.ui.views.widgets.glass_panel import GlassPanel
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.views.widgets.listen_bars import ListenBars, RankRow
from quantis.ui.views.widgets.page_layout import PAGE_MARGINS
from quantis.ui.views.widgets.rhythm_chart import (
    WEEKDAYS_FULL,
    hour_chart,
    listens_word,
    weekday_chart,
)
from quantis.ui.views.widgets.segmented import Segmented

_EMPTY_HINT = "Дослушай трек до конца — он попадёт в топ"
_COUNTED_HINT = "Прослушивание засчитывается, когда трек дослушан до конца"


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


class _ArtistMetric(_MetricCard):
    """«Любимый артист» с круглой обложкой его самого слушаемого трека."""

    AVATAR = 46

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._track: Track | None = None
        margins = self.layout().contentsMargins()
        margins.setRight(16 + self.AVATAR + 12)
        self.layout().setContentsMargins(margins)
        CoverDecoder.instance().ready.connect(self.update)

    def set_track(self, track: Track | None) -> None:
        self._track = track
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._track is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        size = self.AVATAR
        rect = QRect(self.width() - 16 - size, (self.height() - size) // 2, size, size)
        clip = QPainterPath()
        clip.addEllipse(QRectF(rect))
        painter.setClipPath(clip)
        paint_rounded_cover(
            painter,
            rect,
            label=self._track.author or "?",
            pixmap=request_track_cover(self._track, size),
            radius=size // 2,
            with_badge=False,
        )
        painter.end()


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
        root.setContentsMargins(PAGE_MARGINS[0], PAGE_MARGINS[1], PAGE_MARGINS[2], 40)
        root.setSpacing(24)

        hero = QWidget()
        hero.setObjectName("homeHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(6)
        # Как заголовки разделов («Топ треков», «Скачанные»): у прежних
        # homeKicker/homeGreeting после редизайна не осталось стилей.
        title = QLabel("Статистика")
        title.setObjectName("pageTitle")
        hero_layout.addWidget(title)
        self._subtitle = QLabel(_EMPTY_HINT)
        self._subtitle.setObjectName("pageSubtitle")
        self._subtitle.setWordWrap(True)
        hero_layout.addWidget(self._subtitle)
        root.addWidget(hero)

        metrics = QWidget()
        metrics.setObjectName("statsMetrics")
        self._metrics_grid = QGridLayout(metrics)
        self._metrics_grid.setContentsMargins(0, 0, 0, 0)
        self._metrics_grid.setHorizontalSpacing(12)
        self._metrics_grid.setVerticalSpacing(12)
        # Прослушивание — трек, дослушанный до конца; в истории же все
        # запущенные треки, поэтому треков бывает больше, чем прослушиваний.
        self._listens = _MetricCard("Полных прослушиваний")
        self._tracks = _MetricCard("Треков в истории")
        self._time = _MetricCard("Время в эфире")
        self._artist = _ArtistMetric("Любимый артист")
        for index, card in enumerate(
            (self._listens, self._tracks, self._time, self._artist)
        ):
            self._metrics_grid.addWidget(card, 0, index)
            self._metrics_grid.setColumnStretch(index, 1)
        root.addWidget(metrics)

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        self._tabs = Segmented(["Треки", "Артисты", "Время"])
        tabs_row.addWidget(self._tabs)
        tabs_row.addStretch(1)
        root.addLayout(tabs_row)

        self._stack = QStackedWidget()
        self._stack.setObjectName("statsStack")
        self._tabs.current_changed.connect(self._on_tab)
        root.addWidget(self._stack)

        # --- Треки: топ с обложками и «реже всего» ---------------------------
        tracks_page = QWidget()
        tracks_layout = QVBoxLayout(tracks_page)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.setSpacing(24)
        top_section = HomeSection("Топ треков", "По числу полных прослушиваний")
        self._bars = ListenBars()
        self._bars.track_activated.connect(self._on_play_most)
        top_section.add_widget_block(self._panel(self._bars))
        tracks_layout.addWidget(top_section)
        self._least_section = HomeSection("Реже всего", "Почти не слушались")
        self._least_bars = ListenBars(empty_text="Пока пусто")
        self._least_bars.track_activated.connect(self._on_play_least)
        self._least_section.add_widget_block(self._panel(self._least_bars))
        tracks_layout.addWidget(self._least_section)
        self._stack.addWidget(tracks_page)

        # --- Артисты ---------------------------------------------------------
        artists_page = QWidget()
        artists_layout = QVBoxLayout(artists_page)
        artists_layout.setContentsMargins(0, 0, 0, 0)
        artists_section = HomeSection(
            "Топ артистов", "Сумма полных прослушиваний их треков"
        )
        self._artist_bars = ListenBars(
            empty_text="Дослушай пару треков — здесь появятся артисты",
            clickable=False,
        )
        artists_section.add_widget_block(self._panel(self._artist_bars))
        artists_layout.addWidget(artists_section)
        self._stack.addWidget(artists_page)

        # --- Время -----------------------------------------------------------
        time_page = QWidget()
        time_layout = QVBoxLayout(time_page)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(24)
        self._rhythm_hint = QLabel()
        self._rhythm_hint.setObjectName("pageSubtitle")
        self._rhythm_hint.setWordWrap(True)
        time_layout.addWidget(self._rhythm_hint)
        hours_section = HomeSection("По часам", "В какое время суток слушаешь")
        self._hours = hour_chart()
        hours_section.add_widget_block(self._panel(self._hours))
        time_layout.addWidget(hours_section)
        days_section = HomeSection("По дням недели")
        self._days = weekday_chart()
        days_section.add_widget_block(self._panel(self._days))
        time_layout.addWidget(days_section)
        self._stack.addWidget(time_page)
        self._stack.currentChanged.connect(lambda _i: self._schedule_fit())

        root.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._vm.stats_changed.connect(self._rebuild)
        self._rebuild()

    @staticmethod
    def _panel(widget: QWidget) -> GlassPanel:
        panel = GlassPanel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(widget)
        return panel

    def _on_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _schedule_fit(self) -> None:
        # Вложенные блоки пересчитывают размер через события — после них.
        QTimer.singleShot(0, self._fit_stack)
        QTimer.singleShot(80, self._fit_stack)

    def _fit_stack(self) -> None:
        # Стек берёт высоту самой длинной вкладки — подгоняем под текущую.
        # Скрытая вкладка ещё не пересчитала раскладку: activate() — сейчас.
        current = self._stack.currentWidget()
        if current is None:
            return
        layout = current.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
            height = layout.sizeHint().height()
        else:
            height = current.sizeHint().height()
        self._stack.setFixedHeight(height)

    def _rebuild(self) -> None:
        snap = self._vm.snapshot
        summary = snap.summary
        self._listens.set_value(str(summary.total_listens))
        self._tracks.set_value(str(summary.unique_tracks))
        self._time.set_value(_format_span(summary.listened_ms))
        self._artist.set_value(summary.top_artist or "—")
        top = next(
            (r for r in snap.artists if r.stat.author == summary.top_artist), None
        )
        self._artist.set_track(top.cover if top is not None else None)
        # Числа уже в карточках ниже: подзаголовок объясняет, что считается.
        self._subtitle.setText(_COUNTED_HINT if summary.total_listens else _EMPTY_HINT)
        self._least_section.set_badge(str(len(snap.least)) if snap.least else "")
        self._bars.set_tracks(list(snap.most))
        self._least_bars.set_tracks(list(snap.least))
        self._artist_bars.set_rows(
            [
                RankRow(
                    title=row.stat.author,
                    subtitle=_artist_meta(row.stat.tracks, row.stat.played_ms),
                    value=row.stat.listens,
                    cover_track=row.cover,
                    round_cover=True,
                )
                for row in snap.artists
            ]
        )
        rhythm = snap.rhythm
        self._hours.set_values(rhythm.hours)
        self._days.set_values(rhythm.weekdays)
        self._rhythm_hint.setText(_rhythm_text(rhythm))
        self._schedule_fit()

    def _on_play_most(self, index: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_most_at(index), self._bridge)

    def _on_play_least(self, index: int) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_least_at(index), self._bridge)

    def set_playing_track(self, track) -> None:
        self._vm.set_playing_track(track)

    def set_accent(self, color) -> None:
        for widget in (
            self._bars,
            self._least_bars,
            self._artist_bars,
            self._hours,
            self._days,
        ):
            widget.set_accent(color)


def _artist_meta(tracks: int, played_ms: int) -> str:
    from quantis.ui.views.widgets.playlist_card import playlist_tracks_label

    parts = [playlist_tracks_label(tracks)]
    if played_ms >= 60_000:
        parts.append(_format_span(played_ms))
    return " · ".join(parts)


def _rhythm_text(rhythm: ListeningRhythm) -> str:
    if rhythm.total == 0:
        return "Дослушай пару треков — здесь появится твой ритм."
    hour = max(range(24), key=lambda h: rhythm.hours[h])
    day = max(range(7), key=lambda d: rhythm.weekdays[d])
    basis = (
        f"Учтено {listens_word(rhythm.total)}."
        if rhythm.exact
        else "Пока по времени последнего прослушивания каждого трека — "
        "точнее станет со временем."
    )
    return (
        f"Чаще всего слушаешь около {hour:02d}:00, "
        f"любимый день — {WEEKDAYS_FULL[day]}. {basis}"
    )
