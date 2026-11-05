"""Правая выдвижная панель: очередь и текст песни (вкладки).

Открывается кнопкой «Очередь» в плеере, сдвигает страницу (а не лежит
поверх неё) и заменяет прежнюю колонку «Сейчас»: та дублировала плеер.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.ui import resources
from quantis.ui.corners import corner
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.cover_art import load_cover_pixmap
from quantis.ui.views.widgets.elided_label import ElidedLabel
from quantis.ui.views.widgets.glass import install_glass
from quantis.ui.views.widgets.lyrics_view import LyricsView
from quantis.ui.views.widgets.now_playing_stage import UpNextItem, UpNextPanel

PANEL_W = 340
_NOW_COVER = 48


class _NowCover(QWidget):
    """Обложка текущего трека со скруглением; без обложки — подложка."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_NOW_COVER, _NOW_COVER)
        self._pixmap = QPixmap()

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = pixmap if pixmap is not None else QPixmap()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), corner(9), corner(9))
        if self._pixmap.isNull():
            painter.fillPath(path, QColor(128, 136, 160, 46))
        else:
            painter.setClipPath(path)
            painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()


class _QueueList(UpNextPanel):
    """Список «Дальше» без своей рамки: рамка — у панели."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidePanelQueue")
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def columns(self) -> int:
        return 1

    def _link_rect(self) -> QRectF:
        return QRectF()  # вся очередь и так перед глазами

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = UiPreferences().theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_content(painter, theme, QRectF(self.rect()))
        painter.end()


class SidePanel(QFrame):
    """Выдвижная панель справа (ширина анимируется 0 ↔ PANEL_W)."""

    close_requested = Signal()
    track_activated = Signal(int)
    """Индекс трека в текущем плейлисте."""
    queue_page_requested = Signal()
    tab_requested = Signal(str)
    """Клик по вкладке: "queue" или "lyrics"."""
    seek_requested = Signal(int)

    QUEUE_COUNT = 12

    def __init__(self, path_provider: PathProvider, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidePanelHost")
        self._path_provider = path_provider
        self._open = False
        self._width = 0.0
        self.setFixedWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        # Содержимое фиксированной ширины: при анимации обрезается, а не
        # пересобирается на каждом кадре.
        self._card = QFrame(self)
        self._card.setObjectName("sidePanel")
        install_glass(self._card, "QFrame#sidePanel")

        col = QVBoxLayout(self._card)
        col.setContentsMargins(16, 14, 10, 12)
        col.setSpacing(10)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(4)
        self._tabs: dict[str, QToolButton] = {}
        for key, text in (("queue", "Очередь"), ("lyrics", "Текст")):
            tab = QToolButton(self._card)
            tab.setObjectName("sidePanelTab")
            tab.setText(text)
            tab.setCheckable(True)
            tab.setAutoExclusive(False)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setAccessibleName(text)
            tab.clicked.connect(lambda _=False, k=key: self.tab_requested.emit(k))
            head.addWidget(tab)
            self._tabs[key] = tab
        head.addStretch(1)
        self._open_page_btn = self._tool("Открыть как страницу", "chevron-right.svg")
        self._open_page_btn.clicked.connect(self.queue_page_requested.emit)
        head.addWidget(self._open_page_btn)
        self._close_btn = self._tool("Закрыть панель", "close.svg")
        self._close_btn.clicked.connect(self.close_requested.emit)
        head.addWidget(self._close_btn)
        col.addLayout(head)

        self._pages = QStackedWidget()
        col.addWidget(self._pages, 1)
        queue_page = QWidget()
        queue_col = QVBoxLayout(queue_page)
        queue_col.setContentsMargins(0, 0, 0, 0)
        queue_col.setSpacing(10)
        self._pages.addWidget(queue_page)
        self._lyrics = LyricsView()
        self._lyrics.seek_requested.connect(self.seek_requested.emit)
        self._pages.addWidget(self._lyrics)

        self._now_label = QLabel("Сейчас")
        self._now_label.setObjectName("sidePanelEyebrow")
        self._now_label.setContentsMargins(6, 6, 0, 0)
        queue_col.addWidget(self._now_label)

        now = QFrame()
        now.setObjectName("sidePanelNow")
        row = QHBoxLayout(now)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(12)
        self._cover = _NowCover()
        row.addWidget(self._cover)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._title = ElidedLabel("Ничего не играет", max_lines=1)
        self._title.setObjectName("sidePanelNowTitle")
        self._artist = ElidedLabel("Включи трек или волну", max_lines=1)
        self._artist.setObjectName("sidePanelNowArtist")
        texts.addWidget(self._title)
        texts.addWidget(self._artist)
        row.addLayout(texts, 1)
        queue_col.addWidget(now)

        self._queue = _QueueList()
        self._queue.track_activated.connect(self.track_activated.emit)
        queue_col.addWidget(self._queue, 1)
        self.set_tab("queue")

        self._anim = QPropertyAnimation(self, b"panelWidth", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)
        self.hide()

        UiPreferences().theme_changed.connect(self._refresh_icons)
        self._refresh_icons()

    def _tool(self, tip: str, icon: str) -> QToolButton:
        button = QToolButton(self._card)
        button.setObjectName("sidePanelTool")
        button.setProperty("iconName", icon)
        button.setToolTip(tip)
        button.setAccessibleName(tip)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(32, 32)
        button.setIconSize(QSize(14, 14))
        return button

    def _refresh_icons(self) -> None:
        color = qcolor(UiPreferences().theme.colors.text_soft)
        for button in (self._open_page_btn, self._close_btn):
            button.setIcon(resources.load_icon(button.property("iconName"), color))

    # ------------------------------------------------------------ width anim

    def _get_width(self) -> float:
        return self._width

    def _set_width(self, value: float) -> None:
        self._width = value
        self.setFixedWidth(round(value))

    panelWidth = Property(float, _get_width, _set_width)

    def is_open(self) -> bool:
        return self._open

    def set_open(self, open_: bool, *, animate: bool = True) -> None:
        if open_ == self._open and (animate or self.width() == round(self._target())):
            return
        self._open = open_
        target = self._target()
        if open_:
            self.show()
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._width)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_width(target)
            self._on_anim_finished()

    def _target(self) -> float:
        return float(PANEL_W if self._open else 0)

    def _on_anim_finished(self) -> None:
        if not self._open:
            self.hide()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        # карточка прижата к правому краю: выезжает справа
        self._card.setGeometry(
            self.width() - PANEL_W, 0, PANEL_W - 10, max(0, self.height() - 10)
        )

    # ----------------------------------------------------------------- data

    def set_track(self, track: Track | None) -> None:
        if track is None:
            self._title.setText("Ничего не играет")
            self._artist.setText("Включи трек или волну")
            self._cover.set_pixmap(None)
            return
        self._title.setText(track.title)
        self._artist.setText(track.author)
        path = Path(self._path_provider.get_cover_path(track))
        self._cover.set_pixmap(load_cover_pixmap(path, _NOW_COVER))

    def set_queue(self, items: list[UpNextItem]) -> None:
        self._queue.set_items(items)

    @property
    def queue(self) -> UpNextPanel:
        return self._queue

    @property
    def lyrics(self) -> LyricsView:
        return self._lyrics

    def tab(self) -> str:
        return "lyrics" if self._pages.currentWidget() is self._lyrics else "queue"

    def set_tab(self, key: str) -> None:
        self._pages.setCurrentIndex(1 if key == "lyrics" else 0)
        for name, button in self._tabs.items():
            button.setChecked(name == key)
        # «открыть очередь страницей» — только на вкладке очереди
        self._open_page_btn.setVisible(key != "lyrics")
