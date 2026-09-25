"""Динамический акцент из обложки — точечно, без перестилизации окна.

Оконный QSS ставится один раз на смену темы (~4000 строк на ~1000 объектов,
~120 мс). Акцент меняется на каждом треке, поэтому его получают только
виджеты, которые его используют: у каждого маленький собственный stylesheet
из шаблона ``string.Template`` с ``${rgb}``, ``${rgba14}``, ``${rgba40}``.

Плагины могут подписать свои виджеты так же: ``AccentStyles.instance().bind(...)``.
"""

from __future__ import annotations

from string import Template

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from quantis.ui.design_tokens import ACCENT_FALLBACK


def accent_values(color: QColor) -> dict[str, str]:
    r, g, b = color.red(), color.green(), color.blue()
    return {
        "rgb": f"rgb({r}, {g}, {b})",
        "rgba14": f"rgba({r}, {g}, {b}, 36)",
        "rgba40": f"rgba({r}, {g}, {b}, 102)",
    }


class AccentStyles(QObject):
    """Реестр виджетов с акцентом; обновляет только их stylesheet."""

    _instance: AccentStyles | None = None

    def __init__(self) -> None:
        super().__init__()
        self._color = QColor(ACCENT_FALLBACK)
        self._bound: dict[int, tuple[QWidget, Template]] = {}

    @classmethod
    def instance(cls) -> AccentStyles:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def bind(self, widget: QWidget, template: str) -> None:
        key = id(widget)
        self._bound[key] = (widget, Template(template))
        widget.destroyed.connect(lambda *_: self._bound.pop(key, None))
        self._apply(widget, self._bound[key][1], accent_values(self._color))

    def set_accent(self, color: QColor) -> None:
        if not color.isValid() or color == self._color:
            return
        self._color = QColor(color)
        values = accent_values(color)
        for widget, template in list(self._bound.values()):
            self._apply(widget, template, values)

    @staticmethod
    def _apply(widget: QWidget, template: Template, values: dict[str, str]) -> None:
        widget.setStyleSheet(template.substitute(values))
