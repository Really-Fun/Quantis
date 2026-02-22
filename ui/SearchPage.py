from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QLabel, QMessageBox, QSizePolicy, QScrollArea, QFrame, QInputDialog,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtCore import Qt, QTimeLine, QRectF, Signal
from qasync import asyncSlot

from services import AsyncFinder, AsyncDownloader
from player import Player
from ui.TrackCard import TrackCard
from utils import add_track_to_user_playlist, list_user_playlist_names

_LINE_COLOR = QColor(0, 220, 255)
_LINE_WIDTH = 2
_BREATH_MS = 3000
_BORDER_RADIUS = 14
_ALPHA_MIN = 30
_ALPHA_MAX = 160


class SearchBar(QWidget):
    """Search input with breathing border."""

    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Трек, исполнитель или альбом...")
        self._input.setClearButtonEnabled(True)
        self._input.returnPressed.connect(self._on_submit)
        self._input.setStyleSheet("""
            QLineEdit {
                padding: 14px 18px;
                font-size: 16px;
                color: white;
                background: rgba(0, 0, 0, 60);
                border: none;
                border-radius: 14px;
                selection-background-color: rgba(0, 220, 255, 80);
            }
            QLineEdit::placeholder {
                color: rgba(255, 255, 255, 90);
            }
        """)
        layout.addWidget(self._input)

        self._alpha = _ALPHA_MIN
        self._breath = QTimeLine(_BREATH_MS, self)
        self._breath.setFrameRange(0, 100)
        self._breath.setLoopCount(0)
        self._breath.frameChanged.connect(self._on_tick)
        self._breath.start()

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if text:
            self.search_requested.emit(text)

    def _on_tick(self, frame: int) -> None:
        t = frame / 50.0 if frame <= 50 else (100 - frame) / 50.0
        self._alpha = int(_ALPHA_MIN + (_ALPHA_MAX - _ALPHA_MIN) * t)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = QColor(_LINE_COLOR.red(), _LINE_COLOR.green(), _LINE_COLOR.blue(), self._alpha)
        pen = QPen(color)
        pen.setWidthF(_LINE_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(
            _LINE_WIDTH / 2, _LINE_WIDTH / 2,
            self.width() - _LINE_WIDTH, self.height() - _LINE_WIDTH,
        )
        painter.drawRoundedRect(rect, _BORDER_RADIUS, _BORDER_RADIUS)
        painter.end()


class SearchPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchPage")

        self._finder = AsyncFinder()
        self._player = Player()
        self._downloader = AsyncDownloader()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(12)

        # ========== SEARCH BAR ==========
        self._search_bar = SearchBar()
        self._search_bar.search_requested.connect(self._do_search)
        self.main_layout.addWidget(self._search_bar)

        # ========== RESULTS PANEL ==========
        self._results_panel = QFrame()
        self._results_panel.setObjectName("ResultsPanel")
        self._results_panel.setStyleSheet("""
            QFrame#ResultsPanel {
                background: rgba(0, 0, 0, 60);
                border-radius: 14px;
            }
        """)

        results_inner = QVBoxLayout(self._results_panel)
        results_inner.setContentsMargins(8, 8, 8, 8)
        results_inner.setSpacing(0)

        self._status = QLabel("Введите запрос и нажмите Enter")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet(
            "color: rgba(255,255,255,80); font-size: 14px; padding: 24px; background: transparent;"
        )

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; }
            QWidget#ResultsList { background: transparent; }
            QScrollBar:vertical {
                width: 6px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 220, 255, 60);
                border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self._results_container = QWidget()
        self._results_container.setObjectName("ResultsList")
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(4)
        self._results_layout.addStretch()

        self._scroll.setWidget(self._results_container)

        results_inner.addWidget(self._status)
        results_inner.addWidget(self._scroll)
        self._scroll.hide()

        self.main_layout.addWidget(self._results_panel, stretch=1)

    @asyncSlot()
    async def _do_search(self, query: str) -> None:
        self._status.setText("Ищем...")
        self._status.show()
        self._scroll.hide()

        tracks = await self._finder.get_tracks(query, value=5)

        # clear old results
        while self._results_layout.count() > 1:
            item = self._results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not tracks:
            self._status.setText("Ничего не найдено")
            self._status.show()
            self._scroll.hide()
            return

        self._status.hide()
        self._scroll.show()

        for i, track in enumerate(tracks, start=1):
            card = TrackCard(track, index=i)
            card.play_requested.connect(self._play_track)
            card.download_requested.connect(self._download_track)
            card.add_to_playlist_requested.connect(self._add_track_to_playlist)
            await card.load_cover()
            self._results_layout.insertWidget(self._results_layout.count() - 1, card)

    @asyncSlot(object)
    async def _play_track(self, track) -> None:
        await self._player.play_track(track)

    @asyncSlot(object)
    async def _download_track(self, track) -> None:
        await self._downloader.download_track(track)

    @asyncSlot(object)
    async def _add_track_to_playlist(self, track) -> None:
        names = list_user_playlist_names()
        if not names:
            QMessageBox.information(
                self,
                "Нет плейлистов",
                "Сначала создайте пользовательский плейлист на главной странице.",
            )
            return

        selected, ok = QInputDialog.getItem(
            self,
            "Добавить в плейлист",
            "Выберите плейлист:",
            names,
            0,
            False,
        )
        if not ok:
            return

        try:
            added = add_track_to_user_playlist(
                selected,
                track_id=track.track_id,
                title=track.title,
                author=track.author,
            )
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось добавить трек в плейлист.")
            return

        if added:
            QMessageBox.information(self, "Готово", f"Трек добавлен в '{selected}'.")
        else:
            QMessageBox.information(self, "Уже есть", f"Трек уже находится в '{selected}'.")
