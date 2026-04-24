"""Главная страница приложения.

Секции: библиотека (скачанные, недавно прослушанные) и пользовательские плейлисты.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from models import DownloadPlaylist, RecentlyPlayedPlaylist, UserPlaylist
from providers import PlaylistManager
from services import TrackHistoryService, AsyncRecomendation
from ui.PlaylistPreview import PlaylistPreview
from utils import (
    create_user_playlist_file,
    delete_user_playlist_file,
    get_user_playlist_path_by_name,
    rename_user_playlist_file,
    touch_user_playlist_file,
)

COLUMNS = 4
CARD_SPACING = 14
PANEL_RADIUS = 16
logger = logging.getLogger(__name__)


class HomePage(QWidget):
    """Главная страница с карточками плейлистов."""

    playlist_opened = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.pm = PlaylistManager()
        self.history_service = TrackHistoryService()
        self.setObjectName("HomePage")

        with open("styles/home.qss") as file:
            self.setStyleSheet(file.read())


        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # ═══════ HEADER ═══════
        header = HeaderPanel()
        root.addWidget(header)
        root.addSpacing(12)

        # ═══════ SCROLLABLE CONTENT ═══════
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName("scrollContent")
        self.content_lay = QVBoxLayout(content)
        self.content_lay.setContentsMargins(0, 0, 0, 0)
        self.content_lay.setSpacing(14)

        # ── section: system playlists ──
        self.sys_section = PlaylistSection("Библиотека", accent=True)
        self.content_lay.addWidget(self.sys_section)
        self.load_system_playlists()

        # ── section: user playlists ──
        self.user_section = PlaylistSection("Ваши плейлисты", allow_create=True)
        self.user_section.create_requested.connect(self.create_playlist)
        self.content_lay.addWidget(self.user_section)
        self.load_user_playlists()

        self.recommend_section = PlaylistSection("Рекомендации")
        self.content_lay.insertWidget(0, self.recommend_section)

        self.content_lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    # ── loading ──

    async def load_recomendation(self) -> None:
        rl = await AsyncRecomendation().get_personal_playlist()
        if rl and rl.tracks.values:
            self.add_card(self.sys_section, rl)

    def load_system_playlists(self) -> None:
        try:
            dl = DownloadPlaylist.get_playlist_from_path("")
            if dl and dl.tracks.values:
                self.add_card(self.sys_section, dl)
        except Exception:
            logger.exception("Не удалось загрузить системный плейлист скачанных треков")

        QTimer.singleShot(0, self.load_recent_played_async)

    @asyncSlot()
    async def load_recent_played_async(self) -> None:
        try:
            recent = await self.history_service.get_recent_playlist(limit=50)
            if recent is None:
                recent = RecentlyPlayedPlaylist(tracks=())
            self.add_card(self.sys_section, recent)
        except Exception:
            logger.exception("Не удалось загрузить плейлист недавно прослушанных")

        if not self.sys_section.has_cards():
            self.sys_section.set_empty("Скачайте треки — они появятся здесь")

    def load_user_playlists(self) -> None:
        playlists_dir = Path("playlists")
        if not playlists_dir.is_dir():
            playlists_dir.mkdir(parents=True, exist_ok=True)

        json_files = (
            sorted(
                (p for p in playlists_dir.iterdir() if p.suffix == ".json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if playlists_dir.is_dir()
            else []
        )

        for path in json_files:
            try:
                playlist = UserPlaylist.get_playlist_from_path(str(path))
            except Exception:
                continue
            if playlist is None:
                continue
            self.add_card(self.user_section, playlist)

        if not self.user_section.has_cards():
            self.user_section.set_empty("Добавьте .json файл в папку playlists/")

    def reload_user_playlists(self) -> None:
        self.user_section.clear_cards()
        self.load_user_playlists()

    def reload_system_playlists(self) -> None:
        self.sys_section.clear_cards()
        self.load_system_playlists()

    def create_playlist(self) -> None:
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

        self.reload_user_playlists()

    def add_card(self, section: "PlaylistSection", playlist) -> None:
        card = PlaylistPreview(playlist)
        card.clicked.connect(self.on_click)
        if isinstance(playlist, UserPlaylist):
            card.rename_requested.connect(self.rename_playlist)
            card.delete_requested.connect(self.delete_playlist)
        section.add_card(card)

    @asyncSlot(object)
    async def on_click(self, playlist) -> None:
        if isinstance(playlist, RecentlyPlayedPlaylist):
            fresh = await self.history_service.get_recent_playlist(limit=50)
            playlist = fresh if fresh is not None else RecentlyPlayedPlaylist(tracks=())
        elif isinstance(playlist, UserPlaylist):
            try:
                touch_user_playlist_file(playlist.name)
                path = get_user_playlist_path_by_name(playlist.name)
                fresh = UserPlaylist.get_playlist_from_path(str(path))
                if fresh is not None:
                    playlist = fresh
            except Exception:
                logger.exception("Не удалось перезагрузить пользовательский плейлист")
        self.pm.set_playlist(playlist)
        self.playlist_opened.emit(playlist)

    def rename_playlist(self, playlist: UserPlaylist) -> None:
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

        self.reload_user_playlists()

    def delete_playlist(self, playlist: UserPlaylist) -> None:
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

        self.reload_user_playlists()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

    def add_recommendation_section(self, playlist):
        self.recommend_section.clear_cards()
        self.add_card(self.recommend_section, playlist)


# ═══════════════════════════════════════════════════════
#  Internal widgets
# ═══════════════════════════════════════════════════════


class PlaylistSection(QWidget):
    """Секция с заголовком и сеткой карточек плейлистов."""

    create_requested = Signal()

    def __init__(
        self,
        title: str,
        accent: bool = False,
        allow_create: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.cards: list[PlaylistPreview] = []
        self.accent = accent

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # dark panel
        self.panel = QFrame()
        self.panel.setObjectName("SectionPanel")

        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(16, 14, 16, 14)
        panel_lay.setSpacing(10)

        # title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel(title)
        self.title.setObjectName("sectionTitle")
        title_row.addWidget(self.title)

        if allow_create:
            create_btn = QPushButton("+")
            create_btn.setObjectName("createPlaylistBtn")
            create_btn.setFixedSize(22, 22)
            create_btn.setCursor(Qt.PointingHandCursor)
            create_btn.clicked.connect(self.create_requested.emit)
            title_row.addSpacing(8)
            title_row.addWidget(create_btn)

        if accent:
            badge = QLabel("СИСТЕМА")
            badge.setObjectName("systemBadge")
            title_row.addSpacing(8)
            title_row.addWidget(badge)

        title_row.addStretch()
        panel_lay.addLayout(title_row)

        # grid
        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(CARD_SPACING)
        panel_lay.addWidget(self.grid_container)

        # empty label (hidden by default)
        self.empty = QLabel("")
        self.empty.setObjectName("emptyLabel")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        panel_lay.addWidget(self.empty)

        lay.addWidget(self.panel)

    def add_card(self, card: PlaylistPreview) -> None:
        idx = len(self.cards)
        row, col = divmod(idx, COLUMNS)
        self.grid.addWidget(card, row, col)
        self.cards.append(card)
        self.empty.hide()

    def has_cards(self) -> bool:
        return bool(self.cards)

    def clear_cards(self) -> None:
        for card in self.cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self.cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def set_empty(self, text: str) -> None:
        self.empty.setText(text)
        self.empty.show()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)

        if self.accent:
            p.setBrush(QColor(0, 0, 0, 130))
        else:
            p.setBrush(QColor(0, 0, 0, 130))

        p.drawRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)

        if self.accent:
            line_grad = QLinearGradient(0, 0, self.width(), 0)
            line_grad.setColorAt(0.0, QColor(0, 220, 255, 0))
            line_grad.setColorAt(0.3, QColor(0, 220, 255, 25))
            line_grad.setColorAt(0.7, QColor(0, 220, 255, 25))
            line_grad.setColorAt(1.0, QColor(0, 220, 255, 0))
            p.setPen(QPen(QBrush(line_grad), 1.0))
            p.drawLine(16, 0, int(rect.right() - 16), 0)

        p.end()
        super().paintEvent(event)


class HeaderPanel(QWidget):
    """Верхняя шапка с приветствием и градиентным фоном."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)

        self.greeting = QLabel("Главная")
        self.greeting.setObjectName("headerGreeting")
        lay.addWidget(self.greeting)
        lay.addStretch()

        sub = QLabel("Quantis")
        sub.setObjectName("headerSub")
        lay.addWidget(sub)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
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
        p.drawLine(
            int(rect.left() + 16),
            int(rect.bottom() - 1),
            int(rect.right() - 16),
            int(rect.bottom() - 1),
        )

        p.end()
        super().paintEvent(event)