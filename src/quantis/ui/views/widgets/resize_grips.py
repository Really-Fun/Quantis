"""Зоны ресайза по краям фреймлесс-окна."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QWidget


class _ResizeGrip(QWidget):
    """Прозрачная полоса у края окна: курсор + запуск ресайза через оконный менеджер."""

    def __init__(self, window: QWidget, edges: Qt.Edge, cursor: Qt.CursorShape) -> None:
        super().__init__(window)
        self._edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    @property
    def edges(self) -> Qt.Edge:
        return self._edges

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            handle = window.windowHandle() if window is not None else None
            if handle is not None and handle.startSystemResize(self._edges):
                event.accept()
                return
        super().mousePressEvent(event)


class WindowResizeGrips:
    """Восемь зон (4 края + 4 угла) поверх содержимого окна."""

    _SPECS = (
        (Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
        (Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
        (Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
        (Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
        (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeFDiagCursor),
        (Qt.Edge.BottomEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeFDiagCursor),
        (Qt.Edge.TopEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeBDiagCursor),
        (Qt.Edge.BottomEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeBDiagCursor),
    )

    def __init__(self, window: QWidget, margin: int = 7) -> None:
        self._window = window
        self._margin = margin
        self._enabled = True
        self._grips = [
            _ResizeGrip(window, edges, cursor) for edges, cursor in self._SPECS
        ]

    def set_enabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self.update_geometry()
            return
        for grip in self._grips:
            grip.hide()

    def update_geometry(self) -> None:
        if (
            not self._enabled
            or self._window.isMaximized()
            or self._window.isFullScreen()
        ):
            for grip in self._grips:
                grip.hide()
            return
        rect = self._window.rect()
        corner = self._margin * 2
        for grip in self._grips:
            grip.setGeometry(self._rect_for(rect, grip.edges, self._margin, corner))
            grip.show()
            grip.raise_()

    @staticmethod
    def _rect_for(rect: QRect, edges: Qt.Edge, margin: int, corner: int) -> QRect:
        left = bool(edges & Qt.Edge.LeftEdge)
        right = bool(edges & Qt.Edge.RightEdge)
        top = bool(edges & Qt.Edge.TopEdge)

        if (left or right) and (top or bool(edges & Qt.Edge.BottomEdge)):
            return QRect(
                rect.left() if left else rect.right() - corner + 1,
                rect.top() if top else rect.bottom() - corner + 1,
                corner,
                corner,
            )
        if left or right:
            return QRect(
                rect.left() if left else rect.right() - margin + 1,
                rect.top() + corner,
                margin,
                max(0, rect.height() - 2 * corner),
            )
        return QRect(
            rect.left() + corner,
            rect.top() if top else rect.bottom() - margin + 1,
            max(0, rect.width() - 2 * corner),
            margin,
        )
