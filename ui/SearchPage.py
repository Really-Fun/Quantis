"""Страница поиска треков.

Строка ввода с анимированной рамкой, панель результатов с карточками.
"""

import asyncio
import os

from PySide6.QtCore import QRectF, Qt, QTimeLine, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from player import Player
from providers import PathProvider
from services import AsyncDownloader, AsyncFinder
from ui.ThemeManager import ThemeManager
from ui.TrackCard import TrackCard
from utils import add_track_to_user_playlist, list_user_playlist_names

_LINE_WIDTH = 2
_BREATH_MS = 3000
_BORDER_RADIUS = 14
_ALPHA_MIN = 30
_ALPHA_MAX = 160


class SearchBar(QWidget):
    """Поле поиска с пульсирующей рамкой."""

    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._input = QLineEdit()
        self._input.setObjectName("searchInput")
        self._input.setPlaceholderText("Трек, исполнитель или альбом...")
        self._input.setClearButtonEnabled(True)
        self._input.returnPressed.connect(self._on_submit)
        
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
        
        base_color = ThemeManager.get_color("search_line")
        color = QColor(
            base_color.red(), base_color.green(), base_color.blue(), self._alpha
        )
        pen = QPen(color)
        pen.setWidthF(_LINE_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(
            _LINE_WIDTH / 2,
            _LINE_WIDTH / 2,
            self.width() - _LINE_WIDTH,
            self.height() - _LINE_WIDTH,
        )
        painter.drawRoundedRect(rect, _BORDER_RADIUS, _BORDER_RADIUS)
        painter.end()


class SearchPage(QWidget):
    """Страница поиска по трекам и исполнителям."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchPage")

        self._finder = AsyncFinder()
        self._player = Player()
        self._downloader = AsyncDownloader()
        self._path_provider = PathProvider()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.main_layout.setSpacing(12)

        # Поиск сверху
        self._search_bar = SearchBar()
        self._search_bar.search_requested.connect(self._do_search)
        self.main_layout.addWidget(self._search_bar)

        # Результирующая панель
        self._results_panel = QFrame()
        self._results_panel.setObjectName("ResultsPanel")

        results_inner = QVBoxLayout(self._results_panel)
        results_inner.setContentsMargins(8, 8, 8, 8)
        results_inner.setSpacing(0)

        self._status = QLabel("Введите запрос и нажмите Enter")
        self._status.setObjectName("searchStatusLabel")
        self._status.setAlignment(Qt.AlignCenter)

        # === ВОЗВРАЩАЕМ QScrollArea ===
        self._scroll_area = QScrollArea()
        self._scroll_area.setObjectName("settingsScroll")
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._tracks_container = QWidget()
        self._tracks_container.setObjectName("_sc")
        self._tracks_layout = QVBoxLayout(self._tracks_container)
        self._tracks_layout.setContentsMargins(0, 0, 0, 0)
        self._tracks_layout.setSpacing(8)
        self._tracks_layout.addStretch()

        self._scroll_area.setWidget(self._tracks_container)

        results_inner.addWidget(self._status)
        results_inner.addWidget(self._scroll_area)
        self._scroll_area.hide()

        self.main_layout.addWidget(self._results_panel, stretch=1)

    @asyncSlot(str)
    async def _do_search(self, query: str) -> None:
        self._status.setText("Поиск...")
        self._status.show()
        self._scroll_area.hide()

        for i in reversed(range(self._tracks_layout.count())):
            item = self._tracks_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
            elif item.spacerItem():
                self._tracks_layout.removeItem(item)

        index = 0
        tasks = []
        for finder in self._finder.get_all_finders():
            tracks = await finder.get_tracks(query, 20)
            for track in tracks:
                card = TrackCard(track=track, index=index+1)
                index += 1
                
                card.play_requested.connect(self._play_track)
                card.download_requested.connect(self._download_track)
                
                if hasattr(card, 'context_menu_requested'):
                    card.context_menu_requested.connect(self._on_context_menu)

                self._tracks_layout.addWidget(card)
                tasks.append(asyncio.create_task(self._load_and_set_cover(card, track)))

            self._tracks_layout.addStretch()
        
            self._status.hide()
            self._scroll_area.show()
        await asyncio.gather(*tasks)

    async def _load_and_set_cover(self, card: TrackCard, track: YoutubeTrack) -> None:
        """Вспомогательная корутина для фонового скачивания и обновления UI"""
        path = self._path_provider.get_cover_path(track)
        
        if not os.path.isfile(path):
            try:
                await self._downloader.download_cover(track)
            except Exception as e:
                print(f"Ошибка загрузки обложки: {e}")
                return

        try:
            card_index = getattr(card, '_index', 0)
            card.load_cover()
        except RuntimeError:
            pass

    @asyncSlot(object)
    async def _play_track(self, track) -> None:
        await self._player.play_track(track)

    @asyncSlot(object)
    async def _download_track(self, track) -> None:
        await self._downloader.download_track(track)

    @asyncSlot(object, object)
    async def _on_context_menu(self, track, global_pos):
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        play_action = menu.addAction("Играть")
        add_action = menu.addAction("Добавить в плейлист")
        download_action = menu.addAction("Скачать")

        chosen = menu.exec(global_pos)
        if chosen == play_action:
            await self._play_track(track)
        elif chosen == add_action:
            await self._add_track_to_playlist(track)
        elif chosen == download_action:
            await self._download_track(track)

    @asyncSlot(object)
    async def _add_track_to_playlist(self, track) -> None:
        names = list_user_playlist_names()

        if not names:
            msg = QMessageBox(self)
            msg.setWindowTitle("Нет плейлистов")
            msg.setText(
                "Сначала создайте пользовательский плейлист на главной странице."
            )
            msg.setIcon(QMessageBox.Information)
            msg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            msg.exec()
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Добавить в плейлист")
        dialog.setLabelText("Выберите плейлист:")
        dialog.setComboBoxItems(names)
        dialog.setOption(
            QInputDialog.UseListViewForComboBoxItems
        )

        ok = dialog.exec()
        selected = dialog.textValue()

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
            msg = QMessageBox(self)
            msg.setWindowTitle("Ошибка")
            msg.setText("Не удалось добавить трек в плейлист.")
            msg.setIcon(QMessageBox.Warning)
            msg.exec()
            return

        success_msg = QMessageBox(self)
        if added:
            success_msg.setWindowTitle("Готово")
            success_msg.setText(f"Трек добавлен в '{selected}'.")
        else:
            success_msg.setWindowTitle("Уже есть")
            success_msg.setText(f"Трек уже находится в '{selected}'.")
        success_msg.exec()