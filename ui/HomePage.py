from pathlib import Path

from PySide6.QtGui import QColor, QPainter, QLinearGradient, QBrush, QPainterPath, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QScrollArea, QHBoxLayout,
    QLabel, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QRectF, Signal

from models import UserPlaylist
from providers import PlaylistManager
from ui.PlaylistPreview import PlaylistPreview

_COLUMNS = 4
_CARD_SPACING = 14
_PANEL_RADIUS = 16


class HomePage(QWidget):

    playlist_opened = Signal(object)  # emitted with playlist when card is clicked

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pm = PlaylistManager()

        self.setObjectName("HomePage")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(14)

        # ═══════════ HEADER ═══════════
        header = _HeaderPanel()
        root.addWidget(header)

        # ═══════════ PLAYLISTS ═══════════
        self._panel = _DarkPanel()
        self._panel.setObjectName("PlPanel")

        panel_lay = QVBoxLayout(self._panel)
        panel_lay.setContentsMargins(16, 14, 16, 14)
        panel_lay.setSpacing(10)

        # section title row
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        sec = QLabel("Ваши плейлисты")
        sec.setStyleSheet(
            "color: #fff; font-size: 17px; font-weight: 700; background: transparent;"
        )
        title_row.addWidget(sec)
        title_row.addStretch()
        panel_lay.addLayout(title_row)

        # scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QWidget#_gc { background: transparent; }
            QScrollBar:vertical {
                width: 5px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,30); border-radius: 2px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        gc = QWidget()
        gc.setObjectName("_gc")
        self._grid = QGridLayout(gc)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(_CARD_SPACING)

        self._cards: list[PlaylistPreview] = []
        self._load_playlists()

        scroll.setWidget(gc)
        panel_lay.addWidget(scroll)

        root.addWidget(self._panel, stretch=1)

        # ── empty state ──
        self._empty_label = QLabel("Пока нет плейлистов\nДобавьте .json файл в папку playlists/")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: rgba(255,255,255,50); font-size: 14px; background: transparent;"
        )
        self._empty_label.setVisible(not self._cards)
        if not self._cards:
            panel_lay.addWidget(self._empty_label, alignment=Qt.AlignCenter)

    # ── paint dark panel ──

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

    # ── playlists loading ──

    def _load_playlists(self) -> None:
        playlists_dir = Path("playlists")
        if not playlists_dir.is_dir():
            playlists_dir.mkdir(parents=True, exist_ok=True)
            return

        row, col = 0, 0
        for name in sorted(playlists_dir.iterdir()):
            if not name.suffix == ".json":
                continue
            try:
                playlist = UserPlaylist.get_playlist_from_path(str(name))
            except Exception:
                continue
            if playlist is None:
                continue

            card = PlaylistPreview(playlist)
            card.clicked.connect(self._on_playlist_click)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)

            col += 1
            if col >= _COLUMNS:
                col = 0
                row += 1

    def _on_playlist_click(self, playlist) -> None:
        self._pm.set_playlist(playlist)
        self.playlist_opened.emit(playlist)


class _DarkPanel(QFrame):
    """Dark rounded panel for the playlist section."""

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(12, 14, 20, 160))
        p.drawRoundedRect(rect, _PANEL_RADIUS, _PANEL_RADIUS)
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

        # gradient background
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(15, 20, 30, 180))
        grad.setColorAt(0.5, QColor(10, 25, 40, 180))
        grad.setColorAt(1.0, QColor(15, 20, 30, 180))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(rect)

        # subtle accent line at bottom
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
