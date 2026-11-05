from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui import resources
from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.ui.ui_extensions import UiExtensionHost

_COLLAPSED_W = 72
_EXPANDED_W = 224


class _NavItem(QToolButton):
    """Кнопка навбара: иконка + опциональная подпись."""

    def __init__(
        self,
        icon_name: str,
        label: str,
        page_id: int,
        *,
        from_plugin: bool = False,
        icon_obj=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("navIconButton")
        self.setCheckable(True)
        self.setAutoRaise(True)
        self._label = label
        self._page_id = page_id
        self.setToolTip(label + (" · плагин" if from_plugin else ""))
        self.setAccessibleName(label)
        self._icon_name = icon_name or ("" if icon_obj is not None else "plugins.svg")
        if icon_obj is not None:
            self.setIcon(icon_obj)
        self.tint(QColor("#B4BCC8"), QColor(ACCENT_FALLBACK))
        self.setIconSize(QSize(20, 20))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("navIndex", page_id)
        self.setProperty("plugin", from_plugin)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_expanded(False)

    def tint(self, normal: QColor, active: QColor) -> None:
        """Одноцветный значок: обычный — цветом текста темы, выбранный — акцентом."""
        if not self._icon_name:
            return  # значок плагина — как есть
        icon = QIcon()
        for color, state in ((normal, QIcon.State.Off), (active, QIcon.State.On)):
            pix = resources.load_icon(self._icon_name, color).pixmap(40, 40)
            icon.addPixmap(pix, QIcon.Mode.Normal, state)
            icon.addPixmap(pix, QIcon.Mode.Active, state)
            icon.addPixmap(pix, QIcon.Mode.Selected, state)
        self.setIcon(icon)

    def set_expanded(self, expanded: bool) -> None:
        if expanded:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setText(self._label)
            # Сбрасываем fixed width от свёрнутого режима (иначе подпись клипается).
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setFixedHeight(44)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setText("")
            self.setFixedSize(48, 48)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()
        self.updateGeometry()


class SideNavRail(QFrame):
    """Меню слева: свёрнуто — значки (72 px), развёрнуто — подписи (224 px).
    Переключается кнопкой в шапке, состояние хранится в UiPreferences."""

    page_changed = Signal(int)
    expanded_changed = Signal(bool)

    CORE_TOP = (
        ("home.svg", "Главная", 0),
        ("wave.svg", "Моя волна", 8),
        ("library.svg", "Библиотека", 2),
        ("chart.svg", "Статистика", 3),
        ("plugins.svg", "Плагины", 4),
    )
    CORE_BOTTOM = (
        ("user.svg", "Аккаунты", 5),
        ("sliders.svg", "Настройки", 6),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideNavRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._expanded = False
        self._rail_width = float(_COLLAPSED_W)
        self.setFixedWidth(_COLLAPSED_W)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 8, 12, 14)
        self._root.setSpacing(6)

        self._items_layout = QVBoxLayout()
        self._items_layout.setSpacing(4)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._root.addLayout(self._items_layout, stretch=1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, _NavItem] = {}
        self._plugin_buttons: list[_NavItem] = []
        self._accent = QColor(ACCENT_FALLBACK)
        self._text = QColor("#B4BCC8")
        self._extensions = UiExtensionHost.instance()

        self._rebuild_core()
        self._extensions.nav_changed.connect(self._rebuild_plugin_nav)

        self._indicator_y = 0.0
        self._indicator_h = 44.0
        self._ind_anim = QPropertyAnimation(self, b"indicatorY", self)
        self._ind_anim.setDuration(260)
        self._ind_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._width_anim = QPropertyAnimation(self, b"railWidth", self)
        self._width_anim.setDuration(220)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.set_active_page(0)
        self._apply_expanded_ui(False)

    # --- width property for animation ---
    def _get_rail_width(self) -> float:
        return self._rail_width

    def _set_rail_width(self, value: float) -> None:
        self._rail_width = value
        self.setFixedWidth(int(value))

    railWidth = Property(float, _get_rail_width, _set_rail_width)

    def _get_indicator_y(self) -> float:
        return self._indicator_y

    def _set_indicator_y(self, value: float) -> None:
        self._indicator_y = value
        self.update()

    indicatorY = Property(float, _get_indicator_y, _set_indicator_y)

    def set_accent(self, color: QColor) -> None:
        if color.isValid():
            changed = QColor(color).rgb() != self._accent.rgb()
            self._accent = QColor(color)
            if changed:
                self._retint()
            self.update()

    def set_text_color(self, color: QColor) -> None:
        if color.isValid():
            self._text = QColor(color)
            self._retint()

    def _retint(self) -> None:
        for button in self._buttons.values():
            button.tint(self._text, self._accent)

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._apply_expanded_ui(expanded)
        target = float(_EXPANDED_W if expanded else _COLLAPSED_W)
        if animate:
            self._width_anim.stop()
            self._width_anim.setStartValue(self._rail_width)
            self._width_anim.setEndValue(target)
            self._width_anim.start()
        else:
            self._set_rail_width(target)
        self.expanded_changed.emit(expanded)
        QTimer.singleShot(30, self._sync_indicator)

    def _apply_expanded_ui(self, expanded: bool) -> None:
        self.setProperty("expanded", expanded)
        align = (
            Qt.AlignmentFlag.AlignLeft if expanded else Qt.AlignmentFlag.AlignHCenter
        )
        for button in self._buttons.values():
            button.set_expanded(expanded)
            self._items_layout.setAlignment(button, align)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self._items_layout.invalidate()
        self.updateGeometry()
        self.update()

    def _clear_items(self) -> None:
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if isinstance(widget, _NavItem):
                    self._group.removeButton(widget)
                widget.deleteLater()
        self._buttons.clear()
        self._plugin_buttons.clear()

    def _rebuild_core(self) -> None:
        self._clear_items()
        for icon, label, page_id in self.CORE_TOP:
            self._items_layout.addWidget(
                self._make_button(icon, label, page_id, from_plugin=False)
            )
        self._items_layout.addStretch(1)
        self._rebuild_plugin_nav()
        for icon, label, page_id in self.CORE_BOTTOM:
            self._items_layout.addWidget(
                self._make_button(icon, label, page_id, from_plugin=False)
            )
        self._apply_expanded_ui(self._expanded)

    def _rebuild_plugin_nav(self, *_args) -> None:
        for button in list(self._plugin_buttons):
            self._group.removeButton(button)
            self._items_layout.removeWidget(button)
            self._buttons.pop(button._page_id, None)
            button.deleteLater()
        self._plugin_buttons.clear()

        insert_at = max(0, self._items_layout.count() - len(self.CORE_BOTTOM))
        for ext in self._extensions.nav_items():
            button = self._make_button(
                "",
                ext.tooltip,
                ext.page_id,
                from_plugin=True,
                icon_obj=ext.icon,
            )
            button.set_expanded(self._expanded)
            self._items_layout.insertWidget(insert_at, button)
            self._plugin_buttons.append(button)
            insert_at += 1
            if ext.on_click is not None:
                button.clicked.connect(ext.on_click)

    def _make_button(
        self,
        icon: str,
        label: str,
        page_id: int,
        *,
        from_plugin: bool = False,
        icon_obj=None,
    ) -> _NavItem:
        button = _NavItem(
            icon,
            label,
            page_id,
            from_plugin=from_plugin,
            icon_obj=icon_obj,
            parent=self,
        )
        button.clicked.connect(
            lambda checked=False, pid=page_id: self.page_changed.emit(pid)
        )
        self._group.addButton(button, page_id)
        self._buttons[page_id] = button
        button.tint(self._text, self._accent)
        return button

    def set_active_page(self, page_id: int) -> None:
        button = self._group.button(page_id)
        if button is None:
            # страницы нет в меню (поиск — в шапке): ничего не выделяем
            checked = self._group.checkedButton()
            if checked is not None:
                self._group.setExclusive(False)
                checked.setChecked(False)
                self._group.setExclusive(True)
            self._indicator_h = 0.0
            self.update()
            return
        if not button.isChecked():
            self._group.blockSignals(True)
            button.setChecked(True)
            self._group.blockSignals(False)
        self._move_indicator_to(button)

    def _sync_indicator(self) -> None:
        checked = self._group.checkedButton()
        if checked is not None:
            self._indicator_y = float(checked.geometry().y())
            self._indicator_h = float(checked.geometry().height())
            self.update()

    def _move_indicator_to(self, button: QToolButton) -> None:
        geo = button.geometry()
        target = float(geo.y())
        self._indicator_h = float(geo.height())
        if abs(self._indicator_y - target) < 0.5:
            self._indicator_y = target
            self.update()
            return
        self._ind_anim.stop()
        self._ind_anim.setStartValue(self._indicator_y)
        self._ind_anim.setEndValue(target)
        self._ind_anim.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_indicator()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_indicator()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._group.checkedButton() is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin_x = 8
        rect = QRect(
            margin_x,
            int(self._indicator_y),
            self.width() - margin_x * 2,
            int(self._indicator_h),
        )
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.fillPath(
            path,
            QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 40),
        )

        painter.end()
