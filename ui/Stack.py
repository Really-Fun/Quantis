"""Стек страниц приложения.

Переключение между главной, поиском, плейлистом, настройками, профилем.
"""

import asyncio

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ui.HomePage import HomePage
from ui.PlaylistPage import PlaylistPage
from ui.SearchPage import SearchPage
from ui.SettingsPage import SettingsPage
from ui.UserPage import UserPage


class Stack(QWidget):
    """Виджет со стеком страниц и навигацией."""

    HOME = 0
    SEARCH = 1
    PLAYLIST = 2
    SETTINGS = 3
    USER = 4

    def __init__(self, parent=None):
        super().__init__(parent)

        self._stack = QStackedWidget()
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.addWidget(self._stack)

        # Lazy loading cache
        self._pages_cache = {}

        # Add dummy widgets to reserve indices
        for i in range(5):
            self._stack.addWidget(QWidget())

        # Load initially
        self.switch_to(self.HOME)

    def _get_page(self, index: int) -> QWidget:
        if index in self._pages_cache:
            return self._pages_cache[index]

        if index == self.HOME:
            page = HomePage()
        elif index == self.SEARCH:
            page = SearchPage()
        elif index == self.PLAYLIST:
            page = PlaylistPage()
            page.go_back.connect(lambda: self.switch_to(self.HOME))
        elif index == self.SETTINGS:
            page = SettingsPage()
            page.go_back.connect(lambda: self.switch_to(self.HOME))
        elif index == self.USER:
            page = UserPage()
            page.go_back.connect(lambda: self.switch_to(self.HOME))
        else:
            page = QWidget()
        
        # Replace dummy widget with the real page
        old_widget = self._stack.widget(index)
        self._stack.insertWidget(index, page)
        self._stack.removeWidget(old_widget)
        old_widget.deleteLater()

        self._pages_cache[index] = page
        return page

    # Properties for backward compatibility with external code accessing pages directly
    @property
    def home_page(self):
        return self._get_page(self.HOME)

    @property
    def search_page(self):
        return self._get_page(self.SEARCH)

    @property
    def playlist_page(self):
        return self._get_page(self.PLAYLIST)

    @property
    def settings_page(self):
        return self._get_page(self.SETTINGS)

    @property
    def user_page(self):
        return self._get_page(self.USER)

    def switch_to(self, index: int) -> None:
        """Переключает активную страницу по индексу."""
        if 0 <= index < self._stack.count():
            self._get_page(index) # Ensure it's loaded
            self._stack.setCurrentIndex(index)
            if index == self.HOME:
                self.home_page.reload_system_playlists()
                self.home_page.reload_user_playlists()

    async def open_playlist(self, playlist) -> None:
        """Открывает страницу плейлиста и загружает его содержимое."""
        self.switch_to(self.PLAYLIST)
        # Даем Qt шанс отрисовать страницу до тяжелой загрузки карточек.
        await asyncio.sleep(0)
        await self.playlist_page.load_playlist(playlist)
