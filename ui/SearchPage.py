"""Страница поиска треков.

Строка ввода с анимированной рамкой, панель результатов с карточками.
"""

from PySide6.QtCore import QRectF, Qt, QTimeLine, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from player import Player
from services import AsyncDownloader, AsyncFinder
from ui.TrackCard import TrackCard
from utils import add_track_to_user_playlist, list_user_playlist_names

_LINE_COLOR = QColor(0, 220, 255)
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
        color = QColor(
            _LINE_COLOR.red(), _LINE_COLOR.green(), _LINE_COLOR.blue(), self._alpha
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

        self._track_list = QListView()
        self._track_list.setObjectName("ResultsList")
        self._track_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._track_list.setFrameShape(QFrame.NoFrame)
        self._track_list.setSelectionMode(QListView.NoSelection)
        self._track_list.setMouseTracking(True)
        self._track_list.setStyleSheet("""
            QListView { background: transparent; border: none; outline: none; }
            QListView::item:hover { background: transparent; }
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

        from models import TrackListModel
        from ui.delegates.TrackDelegate import TrackDelegate

        self.track_model = TrackListModel()
        self.track_delegate = TrackDelegate(self._track_list)

        self.track_delegate.signals.play_requested.connect(self._play_track)
        self.track_delegate.signals.download_requested.connect(self._download_track)
        self.track_delegate.signals.context_menu_requested.connect(
            self._on_context_menu
        )

        self._track_list.setModel(self.track_model)
        self._track_list.setItemDelegate(self.track_delegate)

        results_inner.addWidget(self._status)
        results_inner.addWidget(self._track_list)
        self._track_list.hide()

        self.main_layout.addWidget(self._results_panel, stretch=1)

    @asyncSlot(str)
    async def _do_search(self, query: str) -> None:
        self._status.setText("Поиск треков запущен...")
        self._status.show()
        self._track_list.hide()

        tracks = await self._finder.get_tracks(query, value=5)

        if not tracks:
            self._status.setText("Ничего не найдено")
            self._status.show()
            self._track_list.hide()
            return

        self._status.hide()
        self._track_list.show()

        self.track_model.set_tracks(tracks)

        # We don't need to manually trigger track cover loads here anymore,
        # the TrackDelegate handles synchronous drawing if the file exists.
        # However, to start downloading missing covers we can iterate over tracks:
        import asyncio
        import os

        from providers import PathProvider

        path_provider = PathProvider()
        for track in tracks:
            path = path_provider.get_cover_path(track)
            if not os.path.isfile(path):
                try:
                    await self._downloader.download_cover(track)
                    # Tell model data changed to repaint
                    idx = tracks.index(track)
                    self.track_model.dataChanged.emit(
                        self.track_model.index(idx), self.track_model.index(idx)
                    )
                except Exception:
                    pass
            await asyncio.sleep(0)

    @asyncSlot(object)
    async def _play_track(self, track) -> None:
        await self._player.play_track(track)
        self.track_model.set_playing_track(track)

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

        # Общий стиль для всех всплывающих окон в духе твоего интерфейса
        dialog_style = """
            QDialog, QMessageBox {
                background-color: #121212;
                border: 2px solid rgba(0, 220, 255, 80);
                border-radius: 14px;
            }
            QLabel {
                color: rgba(255, 255, 255, 220);
                font-size: 14px;
            }
            QPushButton {
                background-color: rgba(0, 220, 255, 20);
                border: 1px solid rgba(0, 220, 255, 100);
                border-radius: 8px;
                color: white;
                padding: 6px 16px;
                min-width: 80px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 220, 255, 60);
                border: 1px solid rgba(0, 220, 255, 255);
            }
            QPushButton:pressed {
                background-color: rgba(0, 220, 255, 100);
            }
            /* Стилизация выпадающего списка в QInputDialog */
            QComboBox {
                background-color: rgba(0, 0, 0, 60);
                border: 1px solid rgba(0, 220, 255, 80);
                border-radius: 8px;
                color: white;
                padding: 6px 12px;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a1a;
                color: white;
                border: 1px solid rgba(0, 220, 255, 80);
                selection-background-color: rgba(0, 220, 255, 80);
                selection-color: white;
                outline: none;
            }
            /* Убираем рамку фокуса у кнопок */
            QPushButton:focus {
                outline: none;
            }
        """

        if not names:
            msg = QMessageBox(self)
            msg.setWindowTitle("Нет плейлистов")
            msg.setText(
                "Сначала создайте пользовательский плейлист на главной странице."
            )
            msg.setIcon(QMessageBox.Information)
            msg.setStyleSheet(dialog_style)
            msg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
            msg.exec()
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Добавить в плейлист")
        dialog.setLabelText("Выберите плейлист:")
        dialog.setComboBoxItems(names)
        dialog.setOption(
            QInputDialog.UseListViewForComboBoxItems
        )  # Важно для красивого выпадающего списка
        dialog.setStyleSheet(dialog_style)

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
            msg.setStyleSheet(dialog_style)
            msg.exec()
            return

        # Финальное окно успеха
        success_msg = QMessageBox(self)
        success_msg.setStyleSheet(dialog_style)
        if added:
            success_msg.setWindowTitle("Готово")
            success_msg.setText(f"Трек добавлен в '{selected}'.")
        else:
            success_msg.setWindowTitle("Уже есть")
            success_msg.setText(f"Трек уже находится в '{selected}'.")
        success_msg.exec()
