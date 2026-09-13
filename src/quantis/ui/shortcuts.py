"""Глобальные горячие клавиши окна."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSlider,
    QTextEdit,
    QWidget,
)

VOLUME_STEP = 5

# (клавиша, действие) — для настроек и подсказок.
KEYBIND_HINTS: tuple[tuple[str, str], ...] = (
    ("S", "Показать / скрыть интерфейс"),
    ("Пробел", "Play / Pause"),
    ("L", "В любимые / убрать"),
    ("←", "Предыдущий трек"),
    ("→", "Следующий трек"),
    ("R", "Режим повтора"),
    ("↑", "Громче"),
    ("↓", "Тише"),
    ("Alt+1", "Главная"),
    ("Alt+2", "Поиск"),
    ("Alt+3", "Библиотека"),
    ("Alt+4", "Статистика"),
    ("Alt+5", "Плагины"),
    ("Alt+M", "Member"),
    ("Alt+S", "Настройки"),
)

ALT_PAGE_IDS: tuple[int, ...] = (0, 1, 2, 3, 4)


def is_typing_target(widget: QWidget | None) -> bool:
    """Не перехватывать буквы и пробел, пока курсор в поле ввода."""
    current = widget
    while current is not None:
        if isinstance(
            current, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox)
        ):
            return True
        if isinstance(current, QComboBox):
            return True
        current = current.parentWidget()
    return False


def is_arrow_navigation_target(widget: QWidget | None) -> bool:
    """Списки и слайдеры сами едят стрелки."""
    current = widget
    while current is not None:
        if isinstance(
            current, (QAbstractItemView, QComboBox, QSlider, QAbstractSpinBox)
        ):
            return True
        current = current.parentWidget()
    return False


def is_space_target(widget: QWidget | None) -> bool:
    """Кнопки и списки сами едят пробел."""
    current = widget
    while current is not None:
        if isinstance(current, (QAbstractButton, QAbstractItemView)):
            return True
        current = current.parentWidget()
    return False
