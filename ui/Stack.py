from PySide6.QtWidgets import QWidget, QStackedWidget, QVBoxLayout
import asyncio

from ui.HomePage import HomePage
from ui.SearchPage import SearchPage
from ui.PlaylistPage import PlaylistPage
from ui.SettingsPage import SettingsPage
from ui.UserPage import UserPage


class Stack(QWidget):

    # Индексы страниц
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

        self.home_page = HomePage()
        self.search_page = SearchPage()
        self.playlist_page = PlaylistPage()
        self.settings_page = SettingsPage()
        self.user_page = UserPage()

        self._stack.addWidget(self.home_page)      # index 0
        self._stack.addWidget(self.search_page)     # index 1
        self._stack.addWidget(self.playlist_page)   # index 2
        self._stack.addWidget(self.settings_page)   # index 3
        self._stack.addWidget(self.user_page)       # index 4

        self._stack.setCurrentIndex(self.HOME)
        self._main_layout.addWidget(self._stack)

        # Назад с плейлиста -> домой
        self.playlist_page.go_back.connect(lambda: self.switch_to(self.HOME))
        # Назад с настроек -> домой
        self.settings_page.go_back.connect(lambda: self.switch_to(self.HOME))
        # Назад со страницы пользователя -> домой
        self.user_page.go_back.connect(lambda: self.switch_to(self.HOME))

    def switch_to(self, index: int) -> None:
        """Переключает страницу по индексу (``Stack.HOME``, ``Stack.SEARCH`` и т.д.)."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)
            if index == self.HOME:
                self.home_page._reload_user_playlists()

    async def open_playlist(self, playlist) -> None:
        """Открывает страницу плейлиста и загружает данные."""
        self.switch_to(self.PLAYLIST)
        # Даем Qt шанс отрисовать страницу до тяжелой загрузки карточек.
        await asyncio.sleep(0)
        await self.playlist_page.load_playlist(playlist)
