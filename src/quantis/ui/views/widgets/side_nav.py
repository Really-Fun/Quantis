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
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui import resources
from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.ui.ui_extensions import UiExtensionHost

_COLLAPSED_W = 72
_EXPANDED_W = 208


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
        if icon_obj is not None:
            self.setIcon(icon_obj)
        elif icon_name:
            self.setIcon(resources.load_icon(icon_name))
        else:
            self.setIcon(resources.load_icon("puzzle.svg"))
        self.setIconSize(QSize(20, 20))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("navIndex", page_id)
        self.setProperty("plugin", from_plugin)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_expanded(False)

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
    """Выдвижная стеклянная рейка: свёрнута — иконки, развёрнута — подписи."""

    page_changed = Signal(int)
    expanded_changed = Signal(bool)

    CORE_TOP = (
        ("recent.svg", "Главная", 0),
        ("search.svg", "Поиск", 1),
        ("download.svg", "Библиотека", 2),
        ("stats.svg", "Статистика", 3),
        ("puzzle.svg", "Плагины", 4),
    )
    CORE_BOTTOM = (
        ("member.svg", "Member", 5),
        ("settings.svg", "Настройки", 6),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideNavRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._expanded = False
        self._pinned = False
        self._rail_width = float(_COLLAPSED_W)
        self.setFixedWidth(_COLLAPSED_W)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(10, 14, 10, 14)
        self._root.setSpacing(6)

        # Brand / expand hint
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 4)
        header.setSpacing(8)
        self._brand_icon = QLabel()
        logo = resources.load_icon("logo.png").pixmap(22, 22)
        if logo.isNull():
            logo = resources.load_icon("puzzle.svg").pixmap(22, 22)
        self._brand_icon.setPixmap(logo)
        self._brand_icon.setFixedSize(22, 22)
        self._brand_label = QLabel("Quantis")
        self._brand_label.setObjectName("navBrandLabel")
        self._brand_label.hide()
        header.addWidget(self._brand_icon)
        header.addWidget(self._brand_label, stretch=1)
        self._root.addLayout(header)

        self._items_layout = QVBoxLayout()
        self._items_layout.setSpacing(4)
        self._items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._root.addLayout(self._items_layout, stretch=1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[int, _NavItem] = {}
        self._plugin_buttons: list[_NavItem] = []
        self._accent = QColor(ACCENT_FALLBACK)
        self._extensions = UiExtensionHost.instance()

        self._pin_btn = QToolButton()
        self._pin_btn.setObjectName("navPinButton")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setToolTip("Закрепить меню")
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setIcon(resources.load_icon("restore.svg"))
        self._pin_btn.setIconSize(QSize(14, 14))
        self._pin_btn.setFixedHeight(32)
        self._pin_btn.toggled.connect(self._on_pin_toggled)
        self._root.addWidget(self._pin_btn)

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

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(280)
        self._collapse_timer.timeout.connect(self._collapse_if_unpinned)

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
            self._accent = QColor(color)
            self.update()

    @property
    def is_expanded(self) -> bool:
        return self._expanded

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
        self._brand_label.setVisible(expanded)
        self.setProperty("expanded", expanded)
        self._pin_btn.setText(" Закрепить" if expanded else "")
        self._pin_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            if expanded
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
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

    def _on_pin_toggled(self, pinned: bool) -> None:
        self._pinned = pinned
        if pinned:
            self._collapse_timer.stop()
            self.set_expanded(True)
        elif not self.underMouse():
            self.set_expanded(False)

    def _collapse_if_unpinned(self) -> None:
        if not self._pinned and not self.underMouse():
            self.set_expanded(False)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._collapse_timer.stop()
        self.set_expanded(True)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if not self._pinned:
            self._collapse_timer.start()

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
        return button

    def set_active_page(self, page_id: int) -> None:
        button = self._group.button(page_id)
        if button is None:
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

        bar = QRect(4, rect.y() + 10, 3, max(8, rect.height() - 20))
        bar_path = QPainterPath()
        bar_path.addRoundedRect(bar, 2, 2)
        painter.fillPath(
            bar_path,
            QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 220),
        )
        painter.end()
