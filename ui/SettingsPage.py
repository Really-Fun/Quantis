"""Страница настроек."""

import os
import re

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QSlider, QComboBox, QLineEdit, QToolButton, QSizePolicy,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QBrush, QPen
from PySide6.QtCore import Qt, QRectF, Signal
from ui.theme import COMBO_QSS, PANEL_DARK, PANEL_RADIUS, REFRESH_MS_MAX, REFRESH_MS_MIN, scroll_qss


class SettingsPage(QWidget):

    go_back = Signal()
    background_changed = Signal(str)
    visualizer_toggled = Signal(bool)  # True = вкл, False = выкл
    visualizer_delay_changed = Signal(int)
    visualizer_color_changed = Signal(tuple)  # (r, g, b)
    visualizer_mode_changed = Signal(str)  # smooth/sharp/choppy

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self._last_valid_rgb = (0, 220, 255)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # ═══════ HEADER ═══════
        header = _SettingsHeader()
        header.back_clicked.connect(self.go_back.emit)
        root.addWidget(header)
        root.addSpacing(12)

        # ═══════ SCROLL ═══════
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(scroll_qss("_sc"))

        content = QWidget()
        content.setObjectName("_sc")
        self._lay = QVBoxLayout(content)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(12)

        self._build_audio_section()
        self._build_appearance_section()
        self._build_visualizer_section()
        self._build_about_section()

        self._lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    # ── Audio ──

    def _build_audio_section(self) -> None:
        sec = _Section("Аудио")

        row_q = _SettingRow("Качество стрима")
        self._quality_combo = QComboBox()
        self._quality_combo.addItems(["Авто", "Высокое", "Среднее", "Низкое"])
        self._quality_combo.setStyleSheet(COMBO_QSS)
        row_q.add_right(self._quality_combo)
        sec.add_row(row_q)

        self._lay.addWidget(sec)

    # ── Appearance ──

    def _build_appearance_section(self) -> None:
        sec = _Section("Внешний вид")

        row_bg = _SettingRow("Фон")
        self._bg_combo = QComboBox()
        bg_dir = "assets/background"
        if os.path.isdir(bg_dir):
            bg_files = sorted(
                f for f in os.listdir(bg_dir)
                if f.lower().endswith((".jpg", ".png", ".jpeg"))
            )
        else:
            bg_files = []
        self._bg_combo.addItems(bg_files)
        self._bg_combo.setStyleSheet(COMBO_QSS)
        self._bg_combo.activated.connect(self._on_bg_selected)
        row_bg.add_right(self._bg_combo)
        sec.add_row(row_bg)

        self._lay.addWidget(sec)

    # ── Visualizer ──

    def _build_visualizer_section(self) -> None:
        sec = _Section("Визуализатор", icon="〰")

        # вкл / выкл
        row_toggle = _SettingRow("Отображение")
        self._viz_toggle = _ToggleButton(checked=True)
        self._viz_toggle.toggled_changed.connect(self.visualizer_toggled.emit)
        row_toggle.add_right(self._viz_toggle)
        sec.add_row(row_toggle)

        # задержка
        row_delay = _SettingRow("Задержка (мс)")
        delay_wrap = QWidget()
        delay_lay = QHBoxLayout(delay_wrap)
        delay_lay.setContentsMargins(0, 0, 0, 0)
        delay_lay.setSpacing(8)
        self._viz_delay = QSlider(Qt.Horizontal)
        self._viz_delay.setRange(REFRESH_MS_MIN, REFRESH_MS_MAX)
        self._viz_delay.setValue(25)
        self._viz_delay.setFixedWidth(140)
        self._viz_delay.valueChanged.connect(self._on_delay_changed)
        self._viz_delay_label = QLabel("25")
        self._viz_delay_label.setStyleSheet(
            "color: rgba(255,255,255,180); font-size: 12px; background: transparent;"
        )
        delay_lay.addWidget(self._viz_delay)
        delay_lay.addWidget(self._viz_delay_label)
        row_delay.add_right(delay_wrap)
        sec.add_row(row_delay)

        # цвет
        row_color = _SettingRow("Цвет (R G B)")
        self._viz_color = QLineEdit("0 220 255")
        self._viz_color.setFixedWidth(140)
        self._viz_color.setPlaceholderText("255 255 255")
        self._viz_color.setStyleSheet(
            "color: white; background: rgba(255,255,255,10);"
            "border: 1px solid rgba(255,255,255,20); border-radius: 8px; padding: 6px;"
        )
        self._viz_color.editingFinished.connect(self._on_color_edited)
        row_color.add_right(self._viz_color)
        sec.add_row(row_color)

        # режим
        row_mode = _SettingRow("Режим")
        self._viz_mode = QComboBox()
        self._viz_mode.addItem("Плавный", "smooth")
        self._viz_mode.addItem("Резкий", "sharp")
        self._viz_mode.addItem("Разрывистый", "choppy")
        self._viz_mode.setStyleSheet(COMBO_QSS)
        self._viz_mode.currentIndexChanged.connect(self._on_mode_changed)
        row_mode.add_right(self._viz_mode)
        sec.add_row(row_mode)

        self._lay.addWidget(sec)

    # ── About ──

    def _build_about_section(self) -> None:
        sec = _Section("О приложении")

        info = _SettingRow("NeonMusic CleanPlayer")
        ver = QLabel("Beta 0.1.0")
        ver.setStyleSheet("color: rgba(255,255,255,50); font-size: 12px; background: transparent;")
        info.add_right(ver)
        sec.add_row(info)

        dev = _SettingRow("Разработчик")
        dev_name = QLabel("reallyfun")
        dev_name.setStyleSheet("color: rgba(0,220,255,160); font-size: 13px; background: transparent;")
        dev.add_right(dev_name)
        sec.add_row(dev)

        self._lay.addWidget(sec)

    # ── callbacks ──

    def _on_bg_selected(self, index: int) -> None:
        name = self._bg_combo.itemText(index)
        self.background_changed.emit(f"assets/background/{name}")

    def _on_delay_changed(self, value: int) -> None:
        self._viz_delay_label.setText(str(value))
        self.visualizer_delay_changed.emit(int(value))

    def _on_color_edited(self) -> None:
        rgb = self._parse_rgb_text(self._viz_color.text())
        if rgb is None:
            # Возвращаем к последнему корректному значению.
            self._viz_color.setText(
                f"{self._last_valid_rgb[0]} {self._last_valid_rgb[1]} {self._last_valid_rgb[2]}"
            )
            return
        self._last_valid_rgb = rgb
        self._viz_color.setText(f"{rgb[0]} {rgb[1]} {rgb[2]}")
        self.visualizer_color_changed.emit(rgb)

    def _on_mode_changed(self, index: int) -> None:
        mode = self._viz_mode.itemData(index)
        if mode:
            self.visualizer_mode_changed.emit(str(mode))

    def set_visualizer_settings(self, delay_ms: int, color_rgb: tuple[int, int, int], mode: str) -> None:
        """Устанавливает начальные значения настроек визуализатора."""
        self._viz_delay.blockSignals(True)
        self._viz_delay.setValue(max(REFRESH_MS_MIN, min(REFRESH_MS_MAX, int(delay_ms))))
        self._viz_delay.blockSignals(False)
        self._viz_delay_label.setText(str(self._viz_delay.value()))

        r, g, b = color_rgb
        self._last_valid_rgb = (int(r), int(g), int(b))
        self._viz_color.setText(f"{int(r)} {int(g)} {int(b)}")

        idx = self._viz_mode.findData(mode)
        if idx < 0:
            idx = 0
        self._viz_mode.blockSignals(True)
        self._viz_mode.setCurrentIndex(idx)
        self._viz_mode.blockSignals(False)

    @staticmethod
    def _parse_rgb_text(text: str) -> tuple[int, int, int] | None:
        """Парсит строку вида '255 255 255' или '255,255,255'."""
        chunks = [c for c in re.split(r"[,\s]+", text.strip()) if c]
        if len(chunks) != 3:
            return None
        try:
            vals = [int(x) for x in chunks]
        except ValueError:
            return None
        if any(v < 0 or v > 255 for v in vals):
            return None
        return vals[0], vals[1], vals[2]

    def paintEvent(self, event) -> None:
        super().paintEvent(event)


# ═══════════════════════════════════════
#  Внутренние виджеты
# ═══════════════════════════════════════


class _ToggleButton(QWidget):
    """Кастомный переключатель вкл/выкл."""

    toggled_changed = Signal(bool)

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self._on = checked
        self.setFixedSize(48, 26)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._on = not self._on
            self.toggled_changed.emit(self._on)
            self.update()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        r = h / 2

        # track
        if self._on:
            track_color = QColor(0, 200, 240, 180)
        else:
            track_color = QColor(60, 60, 70, 200)
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # thumb
        margin = 3
        thumb_r = h - margin * 2
        if self._on:
            tx = w - thumb_r - margin
            thumb_color = QColor(255, 255, 255)
        else:
            tx = margin
            thumb_color = QColor(160, 160, 170)
        p.setBrush(thumb_color)
        p.drawEllipse(QRectF(tx, margin, thumb_r, thumb_r))

        p.end()


class _SettingsHeader(QWidget):

    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 20, 0)

        self._back = QToolButton()
        self._back.setText("←")
        self._back.setFixedSize(36, 36)
        self._back.setCursor(Qt.PointingHandCursor)
        self._back.setStyleSheet("""
            QToolButton {
                color: white; font-size: 18px; font-weight: 700;
                background: rgba(0,0,0,100); border-radius: 18px; border: none;
            }
            QToolButton:hover { background: rgba(0,220,255,60); }
        """)
        self._back.clicked.connect(self.back_clicked.emit)
        lay.addWidget(self._back)
        lay.addSpacing(12)

        title = QLabel("Настройки")
        title.setStyleSheet(
            "color: #fff; font-size: 24px; font-weight: 800; background: transparent;"
        )
        lay.addWidget(title)
        lay.addStretch()

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
        p.setPen(QPen(QBrush(line_grad), 1.0))
        p.drawLine(16, int(rect.bottom() - 1), int(rect.right() - 16), int(rect.bottom() - 1))

        p.end()
        super().paintEvent(event)


class _Section(QWidget):
    """Темная панель с заголовком и строками настроек."""

    def __init__(self, title: str, icon: str = "", parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(16, 14, 16, 14)
        self._lay.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        hdr.setSpacing(8)

        if icon:
            ic = QLabel(icon)
            ic.setStyleSheet("font-size: 18px; background: transparent;")
            hdr.addWidget(ic)

        lbl = QLabel(title)
        lbl.setStyleSheet(
            "color: #fff; font-size: 16px; font-weight: 700; background: transparent;"
        )
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._lay.addLayout(hdr)
        self._lay.addSpacing(6)

    def add_row(self, row: QWidget) -> None:
        self._lay.addWidget(row)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(PANEL_DARK)
        p.drawRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
        p.end()
        super().paintEvent(event)


class _SettingRow(QWidget):
    """Одна строка настройки: слева подпись, справа контрол."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)

        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(4, 0, 4, 0)
        self._lay.setSpacing(12)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            "color: rgba(255,255,255,180); font-size: 14px; background: transparent;"
        )
        self._lay.addWidget(lbl)
        self._lay.addStretch()

    def add_right(self, widget: QWidget) -> None:
        self._lay.addWidget(widget)
