"""Матовое стекло панелей.

Настоящего backdrop-blur в Qt Widgets нет, но фон окна рисуем мы сами
(``BackdropCompositor``), поэтому под панелью можно подложить кусок его
размытой копии. Поверх — тонировка темы и лёгкий блик сверху; рамку и
скругление по-прежнему рисует QSS (у таких панелей фон ``${panel_bg}``).

Подключение — ``install_glass(widget, "QFrame#objectName")``: фильтр событий
рисует стекло до собственного ``paintEvent`` виджета. Радиус и толщина рамки
берутся из итогового QSS темы для этого селектора — стекло ложится ровно
внутрь рамки в любой теме. Плагины могут подключать свои панели так же.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QTransform,
)
from PySide6.QtWidgets import QWidget

from quantis.ui.themes import qss
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor


def compositor_for(widget: QWidget) -> tuple[BackdropCompositor, QWidget] | None:
    """Компоновщик фона окна и виджет, в координатах которого его кадр."""
    node: QWidget | None = widget.parentWidget()
    while node is not None:
        found = getattr(node, "compositor", None)
        if isinstance(found, BackdropCompositor):
            return found, node
        node = node.parentWidget()
    return None


def glass_path(widget: QWidget, selector: str) -> QPainterPath:
    """Контур внутри рамки из QSS: скругление минус толщина рамки."""
    found = compositor_for(widget)
    theme = found[0].theme if found else None
    rule = qss.rule(theme, selector) if theme is not None else {}
    border = qss.px(rule.get("border"), 0.0)
    radius = qss.px(rule.get("border-radius"), 0.0)
    rect = QRectF(widget.rect()).adjusted(border, border, -border, -border)
    path = QPainterPath()
    inner = max(0.0, radius - border)
    path.addRoundedRect(rect, inner, inner)
    return path


def paint_glass(
    widget: QWidget,
    painter: QPainter,
    path: QPainterPath,
    tint: QColor | None = None,
    *,
    sheen: bool = True,
) -> bool:
    """Размытый фон окна под ``path`` + тонировка + блик. False — стекла нет
    (виджет не в окне с компоновщиком или тема без стекла)."""
    found = compositor_for(widget)
    if found is None:
        return False
    compositor, host = found
    theme = compositor.theme
    if not theme.has_glass or compositor.cinematic:
        return False  # театральный режим — как раньше: без стекла поверх клипа
    source = compositor.glass()
    scale = source.devicePixelRatio()  # пикселей стекла на логический пиксель
    glass = _tinted(source, tint if tint is not None else theme.glass_tint_color())
    offset = widget.mapTo(host, QPoint(0, 0))
    # Одна заливка контура текстурой вместо клипа по контуру + drawImage +
    # заливки тонировкой: сглаженный клип в raster-движке дорогой. Текстура — с
    # DPR 1, масштаб и сдвиг заданы явно: DPR текстуры кисти Qt учитывает
    # по-разному при рисовании в виджет и в QImage.
    brush = QBrush(glass)
    brush.setTransform(QTransform(1 / scale, 0, 0, 1 / scale, -offset.x(), -offset.y()))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.fillPath(path, brush)
    bounds = path.boundingRect()
    if sheen:
        top = bounds.top()
        gradient = QLinearGradient(0, top, 0, top + min(90.0, bounds.height()))
        gradient.setColorAt(0, QColor(255, 255, 255, 12 if theme.is_light else 16))
        gradient.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, gradient)
    return True


_TINTED: tuple[tuple[int, int], QImage] | None = None


def _tinted(glass: QImage, tint: QColor) -> QImage:
    """Стекло с тонировкой, запечённой один раз на пересчёт стекла."""
    global _TINTED
    key = (glass.cacheKey(), tint.rgba())
    if _TINTED is not None and _TINTED[0] == key:
        return _TINTED[1]
    image = glass.copy()
    image.setDevicePixelRatio(1.0)  # масштаб — в матрице кисти
    painter = QPainter(image)
    painter.fillRect(image.rect(), tint)
    painter.end()
    _TINTED = (key, image)
    return image


class _GlassFilter(QObject):
    def __init__(self, widget: QWidget, selector: str) -> None:
        super().__init__(widget)
        self._selector = selector
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint and isinstance(watched, QWidget):
            painter = QPainter(watched)
            paint_glass(watched, painter, glass_path(watched, self._selector))
            painter.end()
        return False


def install_glass(widget: QWidget, selector: str) -> None:
    """Стекло под виджетом; ``selector`` — его правило в QSS темы
    (например ``"QFrame#nowPlayingPanel"``)."""
    _GlassFilter(widget, selector)
