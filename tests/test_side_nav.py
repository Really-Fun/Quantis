"""Меню слева: сворачивание, раздел «Плейлисты»."""

from __future__ import annotations

from dataclasses import dataclass

from quantis.ui.views.widgets.side_nav import SideNavRail


@dataclass
class _Playlist:
    name: str
    cover_path: str | None = None


def test_playlists_section_and_click(qapp) -> None:
    nav = SideNavRail()
    nav.set_expanded(True, animate=False)
    nav.set_playlists([_Playlist(f"Плейлист {i}") for i in range(9)])
    items = nav._playlist_items()
    assert [i.toolTip() for i in items] == [f"Плейлист {i}" for i in range(6)]
    assert nav._playlist_label is not None and not nav._playlist_label.isHidden()
    opened: list[str] = []
    nav.playlist_activated.connect(lambda pl: opened.append(pl.name))
    items[2].click()
    assert opened == ["Плейлист 2"]
    # тот же список новыми объектами — кнопки не пересоздаются
    nav.set_playlists([_Playlist(f"Плейлист {i}") for i in range(6)])
    assert nav._playlist_items()[0] is items[0]
    # свёрнутое меню: только обложки, вместо подписи — линия
    nav.set_expanded(False, animate=False)
    assert nav._playlist_label.isHidden()
    assert items[0].text() == ""
    # невысокое окно — лишние плейлисты прячутся
    nav.resize(nav.width(), 520)
    nav._fit_playlists()
    visible = [i for i in items if not i.isHidden()]
    assert 0 < len(visible) < 6
    nav.set_playlists([])
    assert nav._playlist_items() == []


def test_off_menu_page_clears_selection(qapp) -> None:
    nav = SideNavRail()
    nav.set_active_page(2)
    assert nav._group.checkedButton() is not None
    nav.set_active_page(1)  # поиск — не в меню
    assert nav._group.checkedButton() is None
