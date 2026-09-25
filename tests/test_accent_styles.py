"""Акцент из обложки ставится точечно — только подписанным виджетам."""

from __future__ import annotations

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel

from quantis.ui.accent import AccentStyles


def test_bind_and_set_accent(qapp) -> None:
    styles = AccentStyles()
    label = QLabel()
    other = QLabel()
    styles.bind(label, "#x { color: ${rgb}; border-color: ${rgba40}; }")
    styles.set_accent(QColor(255, 51, 102))
    assert label.styleSheet() == (
        "#x { color: rgb(255, 51, 102); border-color: rgba(255, 51, 102, 102); }"
    )
    assert other.styleSheet() == ""


def test_destroyed_widget_is_forgotten(qapp) -> None:
    styles = AccentStyles()
    label = QLabel()
    styles.bind(label, "#x { color: ${rgb}; }")
    label.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    styles.set_accent(QColor(1, 2, 3))
    assert styles._bound == {}
