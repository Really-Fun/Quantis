from PySide6.QtWidgets import QWidget, QStackedWidget, QVBoxLayout

from ui.HomePage import HomePage
from ui.SearchPage import SearchPage
from ui.PlaylistPage import PlaylistPage


class Stack(QWidget):

    # Page indices
    HOME = 0
    SEARCH = 1
    PLAYLIST = 2

    def __init__(self, parent=None):
        super().__init__(parent)

        self._stack = QStackedWidget()
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)

        self.home_page = HomePage()
        self.search_page = SearchPage()
        self.playlist_page = PlaylistPage()

        self._stack.addWidget(self.home_page)      # index 0
        self._stack.addWidget(self.search_page)     # index 1
        self._stack.addWidget(self.playlist_page)   # index 2

        self._stack.setCurrentIndex(self.HOME)
        self._main_layout.addWidget(self._stack)

        # back from playlist -> home
        self.playlist_page.go_back.connect(lambda: self.switch_to(self.HOME))

    def switch_to(self, index: int) -> None:
        """Switch page by index (use Stack.HOME, Stack.SEARCH, etc.)."""
        if 0 <= index < self._stack.count():
            self._stack.setCurrentIndex(index)

    async def open_playlist(self, playlist) -> None:
        """Navigate to the playlist page and load data."""
        self.switch_to(self.PLAYLIST)
        await self.playlist_page.load_playlist(playlist)
