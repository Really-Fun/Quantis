from pathlib import Path
import logging

from PySide6.QtGui import QColor, QPainter, QLinearGradient, QBrush, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QScrollArea, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QInputDialog, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from qasync import asyncSlot

from models import DownloadPlaylist, RecentlyPlayedPlaylist, UserPlaylist
from providers import PlaylistManager
from services import TrackHistoryService
from ui.PlaylistPreview import PlaylistPreview
from utils import (
    create_user_playlist_file,
    delete_user_playlist_file,
    rename_user_playlist_file,
)

_COLUMNS = 4
_CARD_SPACING = 14
_PANEL_RADIUS = 16
logger = logging.getLogger(__name__)

_SCROLL_QSS = """
    QScrollArea { background: transparent; border: none; }
    QWidget#_scrollContent { background: transparent; }
    QScrollBar:vertical {
        width: 5px; background: transparent;
    }
    QScrollBar::handle:vertical {
        background: rgba(255,255,255,30); border-radius: 2px; min-height: 30px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class HomePage(QWidget):

    playlist_opened = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pm = PlaylistManager()
        self._history_service = TrackHistoryService()
        self.setObjectName("HomePage")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # ═══════ HEADER ═══════
        header = _HeaderPanel()
        root.addWidget(header)
        root.addSpacing(12)

        # ═══════ SCROLLABLE CONTENT ═══════
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(_SCROLL_QSS)

        content = QWidget()
        content.setObjectName("_scrollContent")
        self._content_lay = QVBoxLayout(content)
        self._content_lay.setContentsMargins(0, 0, 0, 0)
        self._content_lay.setSpacing(14)

        # ── section: system playlists ──
        self._sys_section = _PlaylistSection("Библиотека", accent=True)
        self._content_lay.addWidget(self._sys_section)
        self._load_system_playlists()

        # ── section: user playlists ──
        self._user_section = _PlaylistSection("Ваши плейлисты", allow_create=True)
        self._user_section.create_requested.connect(self._create_playlist)
        self._content_lay.addWidget(self._user_section)
        self._load_user_playlists()

        self._content_lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    # ── loading ──

    def _load_system_playlists(self) -> None:
        """Загружает системные плейлисты и запускает фоновую загрузку истории."""
        try:
            dl = DownloadPlaylist.get_playlist_from_path("")
            if dl and dl.tracks.values:
                self._add_card(self._sys_section, dl)
        except Exception:
            logger.exception("Не удалось загрузить системный плейлист скачанных треков")

        QTimer.singleShot(0, self._load_recent_played_async)

    @asyncSlot()
    async def _load_recent_played_async(self) -> None:
        """Подгружает плейлист недавно прослушанных из БД."""
        try:
            recent = await self._history_service.get_recent_playlist(limit=24)
            if recent is None:
                recent = RecentlyPlayedPlaylist(tracks=())
            self._add_card(self._sys_section, recent)
        except Exception:
            logger.exception("Не удалось загрузить плейлист недавно прослушанных")

        if not self._sys_section.has_cards():
            self._sys_section.set_empty("Скачайте треки — они появятся здесь")

    def _load_user_playlists(self) -> None:
        """Загружает пользовательские плейлисты из директории `playlists/`."""
        playlists_dir = Path("playlists")
        if not playlists_dir.is_dir():
            playlists_dir.mkdir(parents=True, exist_ok=True)

        for name in sorted(playlists_dir.iterdir()) if playlists_dir.is_dir() else []:
            if name.suffix != ".json":
                continue
            try:
                playlist = UserPlaylist.get_playlist_from_path(str(name))
            except Exception:
                continue
            if playlist is None:
                continue
            self._add_card(self._user_section, playlist)

        if not self._user_section.has_cards():
            self._user_section.set_empty("Добавьте .json файл в папку playlists/")

    def _reload_user_playlists(self) -> None:
        """Перезагружает блок пользовательских плейлистов на экране."""
        self._user_section.clear_cards()
        self._load_user_playlists()

    def _create_playlist(self) -> None:
        """Открывает диалог создания нового пользовательского плейлиста."""
        name, ok = QInputDialog.getText(
            self,
            "Новый плейлист",
            "Введите название плейлиста:",
        )
        if not ok:
            return

        try:
            create_user_playlist_file(name)
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except FileExistsError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать плейлист.")
            return

        self._reload_user_playlists()

    def _add_card(self, section: "_PlaylistSection", playlist) -> None:
        card = PlaylistPreview(playlist)
        card.clicked.connect(self._on_click)
        if isinstance(playlist, UserPlaylist):
            card.rename_requested.connect(self._rename_playlist)
            card.delete_requested.connect(self._delete_playlist)
        section.add_card(card)

    @asyncSlot(object)
    async def _on_click(self, playlist) -> None:
        # Для "Недавно прослушанных" всегда загружаем свежий срез из БД.
        if isinstance(playlist, RecentlyPlayedPlaylist):
            fresh = await self._history_service.get_recent_playlist(limit=50)
            playlist = fresh if fresh is not None else RecentlyPlayedPlaylist(tracks=())
        self._pm.set_playlist(playlist)
        self.playlist_opened.emit(playlist)

    def _rename_playlist(self, playlist: UserPlaylist) -> None:
        """Переименовывает пользовательский плейлист через контекстное меню."""
        old_name = getattr(playlist, "name", "").strip()
        if not old_name:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить имя плейлиста.")
            return

        new_name, ok = QInputDialog.getText(
            self,
            "Переименовать плейлист",
            "Новое название:",
            text=old_name,
        )
        if not ok:
            return

        try:
            rename_user_playlist_file(old_name, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except FileExistsError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Не удалось переименовать плейлист.")
            return

        self._reload_user_playlists()

    def _delete_playlist(self, playlist: UserPlaylist) -> None:
        """Удаляет пользовательский плейлист через контекстное меню."""
        name = getattr(playlist, "name", "").strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить имя плейлиста.")
            return

        answer = QMessageBox.question(
            self,
            "Удаление плейлиста",
            f"Удалить плейлист '{name}'?",
        )
        if answer != QMessageBox.Yes:
            return

        try:
            delete_user_playlist_file(name)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except ValueError as exc:
            QMessageBox.warning(self, "Ошибка", str(exc))
            return
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Не удалось удалить плейлист.")
            return

        self._reload_user_playlists()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)


# ═══════════════════════════════════════════════════════
#  Internal widgets
# ═══════════════════════════════════════════════════════


class _PlaylistSection(QWidget):
    """A titled section with a grid of playlist cards inside a dark panel."""

    create_requested = Signal()

    def __init__(
        self,
        title: str,
        accent: bool = False,
        allow_create: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._cards: list[PlaylistPreview] = []
        self._accent = accent

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # dark panel
        self._panel = QFrame()
        self._panel.setObjectName("SectionPanel")

        panel_lay = QVBoxLayout(self._panel)
        panel_lay.setContentsMargins(16, 14, 16, 14)
        panel_lay.setSpacing(10)

        # title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            "color: #fff; font-size: 17px; font-weight: 700; background: transparent;"
        )
        title_row.addWidget(self._title)

        if allow_create:
            create_btn = QPushButton("+")
            create_btn.setFixedSize(22, 22)
            create_btn.setCursor(Qt.PointingHandCursor)
            create_btn.setStyleSheet(
                """
                QPushButton {
                    color: white;
                    font-size: 14px;
                    font-weight: 700;
                    border: none;
                    border-radius: 11px;
                    background: rgba(255,255,255,18);
                }
                QPushButton:hover {
                    background: rgba(0,220,255,55);
                }
                """
            )
            create_btn.clicked.connect(self.create_requested.emit)
            title_row.addSpacing(8)
            title_row.addWidget(create_btn)

        if accent:
            badge = QLabel("СИСТЕМА")
            badge.setStyleSheet(
                "color: rgba(0,220,255,180); font-size: 10px; font-weight: 700;"
                " letter-spacing: 1px; background: rgba(0,220,255,20);"
                " border-radius: 6px; padding: 2px 8px;"
            )
            title_row.addSpacing(8)
            title_row.addWidget(badge)

        title_row.addStretch()
        panel_lay.addLayout(title_row)

        # grid
        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(_CARD_SPACING)
        panel_lay.addWidget(self._grid_container)

        # empty label (hidden by default)
        self._empty = QLabel("")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet(
            "color: rgba(255,255,255,40); font-size: 13px; padding: 20px; background: transparent;"
        )
        self._empty.hide()
        panel_lay.addWidget(self._empty)

        lay.addWidget(self._panel)

    def add_card(self, card: PlaylistPreview) -> None:
        idx = len(self._cards)
        row, col = divmod(idx, _COLUMNS)
        self._grid.addWidget(card, row, col)
        self._cards.append(card)
        self._empty.hide()

    def has_cards(self) -> bool:
        return bool(self._cards)

    def clear_cards(self) -> None:
        """Очищает текущие карточки секции."""
        for card in self._cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def set_empty(self, text: str) -> None:
        self._empty.setText(text)
        self._empty.show()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)

        if self._accent:
            # slightly different tint for system section
            p.setBrush(QColor(0, 0, 0, 190))
        else:
            p.setBrush(QColor(0, 0, 0, 190))

        p.drawRoundedRect(rect, _PANEL_RADIUS, _PANEL_RADIUS)

        # subtle top border for accent section
        if self._accent:
            line_grad = QLinearGradient(0, 0, self.width(), 0)
            line_grad.setColorAt(0.0, QColor(0, 220, 255, 0))
            line_grad.setColorAt(0.3, QColor(0, 220, 255, 25))
            line_grad.setColorAt(0.7, QColor(0, 220, 255, 25))
            line_grad.setColorAt(1.0, QColor(0, 220, 255, 0))
            p.setPen(QPen(QBrush(line_grad), 1.0))
            p.drawLine(16, 0, int(rect.right() - 16), 0)

        p.end()
        super().paintEvent(event)


class _HeaderPanel(QWidget):
    """Top header with greeting and subtle gradient background."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)

        self._greeting = QLabel("Главная")
        self._greeting.setStyleSheet(
            "color: #fff; font-size: 26px; font-weight: 800; background: transparent;"
        )
        lay.addWidget(self._greeting)
        lay.addStretch()

        sub = QLabel("CleanPlayer")
        sub.setStyleSheet(
            "color: rgba(255,255,255,40); font-size: 13px; font-weight: 500;"
            " background: transparent;"
        )
        lay.addWidget(sub)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(rect, _PANEL_RADIUS, _PANEL_RADIUS)
        p.setClipPath(clip)

        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(10, 14, 22, 220))
        grad.setColorAt(0.5, QColor(6, 16, 30, 220))
        grad.setColorAt(1.0, QColor(10, 14, 22, 220))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(rect)

        line_grad = QLinearGradient(0, 0, self.width(), 0)
        line_grad.setColorAt(0.0, QColor(0, 220, 255, 0))
        line_grad.setColorAt(0.3, QColor(0, 220, 255, 40))
        line_grad.setColorAt(0.7, QColor(0, 220, 255, 40))
        line_grad.setColorAt(1.0, QColor(0, 220, 255, 0))
        pen = QPen(QBrush(line_grad), 1.0)
        p.setPen(pen)
        p.drawLine(int(rect.left() + 16), int(rect.bottom() - 1),
                   int(rect.right() - 16), int(rect.bottom() - 1))

        p.end()
        super().paintEvent(event)
