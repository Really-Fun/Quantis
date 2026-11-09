"""Меню слева: разделы, секция «Плагины» с менеджером, без плейлистов."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QToolButton

from quantis.ui.ui_extensions import NavExtension, UiExtensionHost
from quantis.ui.views.widgets.side_nav import SideNavRail


@pytest.fixture
def extensions(qapp):
    host = UiExtensionHost.instance()
    host.clear()
    yield host
    host.clear()


def _order(nav: SideNavRail) -> list[str]:
    """Подписи пунктов меню и раздела «Плагины» сверху вниз."""
    out: list[str] = []
    layout = nav._items_layout
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QToolButton):
            out.append(widget.accessibleName())
        elif isinstance(widget, QLabel) and widget.objectName() == "navSectionLabel":
            out.append(f"[{widget.text()}]")
    return out


def test_no_playlists_section(extensions) -> None:
    nav = SideNavRail()
    nav.set_expanded(True, animate=False)
    texts = [label.text() for label in nav.findChildren(QLabel)]
    assert "Плейлисты" not in texts
    assert not hasattr(nav, "set_playlists")


def test_plugins_section_order(extensions) -> None:
    extensions.register_nav_item(NavExtension("together", "Вместе", None, 100, True))
    extensions.register_nav_item(
        NavExtension("import", "Импорт плейлистов", None, 101, True)
    )
    nav = SideNavRail()
    assert _order(nav) == [
        "Главная",
        "Моя волна",
        "Библиотека",
        "Статистика",
        "[Плагины]",
        "Вместе",
        "Импорт плейлистов",
        "Менеджер плагинов",
        "Аккаунты",
        "Настройки",
    ]


def test_manager_opens_plugins_page(extensions) -> None:
    nav = SideNavRail()
    pages: list[int] = []
    nav.page_changed.connect(pages.append)
    nav._buttons[4].click()
    assert pages == [4]
    assert nav._buttons[4].accessibleName() == "Менеджер плагинов"


def test_updates_badge(extensions) -> None:
    nav = SideNavRail()
    nav.show()
    badge = nav._updates_badge
    assert badge.isHidden()
    nav.set_updates_count(2)
    assert not badge.isHidden()
    assert badge.text() == "2"
    nav.set_expanded(True, animate=False)
    assert not badge.isHidden()
    nav.set_updates_count(0)
    assert badge.isHidden()
    nav.close()


def test_plugin_page_removed_from_nav_on_disable(extensions) -> None:
    extensions.register_nav_item(NavExtension("together", "Вместе", None, 100, True))
    nav = SideNavRail()
    assert "Вместе" in _order(nav)
    extensions.unregister_nav_item("together")
    assert "Вместе" not in _order(nav)
    assert _order(nav)[-3:] == ["Менеджер плагинов", "Аккаунты", "Настройки"]


def test_section_label_only_when_expanded(extensions) -> None:
    nav = SideNavRail()
    nav.show()
    nav.set_expanded(False, animate=False)
    assert nav._section_label.isHidden()
    assert not nav._section_divider.isHidden()
    nav.set_expanded(True, animate=False)
    assert not nav._section_label.isHidden()
    assert nav._section_divider.isHidden()
    nav.close()


def test_off_menu_page_clears_selection(extensions) -> None:
    nav = SideNavRail()
    nav.set_active_page(2)
    assert nav._group.checkedButton() is not None
    nav.set_active_page(1)  # поиск — не в меню
    assert nav._group.checkedButton() is None
