"""Главное окно приложения Quantis."""

import sys
import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from ui.AudioVisualizer import AudioVisualizer
from ui.MenuPlayWidget import PlayMenu
from ui.MenuTabsWidget import MenuTabs
from ui.Stack import Stack
from ui.ThemeManager import ThemeManager
from utils import asset_path
from providers import PathProvider


class Quantis(QMainWindow):
    """Главное окно: меню, контент, плеер, визуализатор."""

    def __init__(self) -> None:
        super().__init__()
        
        ThemeManager.apply_theme_to_app(self)


        self._settings = QSettings("ReallyFun", "Quantis")
        viz_delay = int(self._settings.value("visualizer/delay_ms", 25))
        viz_mode = str(self._settings.value("visualizer/mode", "smooth"))
        self.viz_toggle = bool(self._settings.value("vizualizer/toggle", False, type=bool))
        viz_r = int(self._settings.value("visualizer/color_r", 0))
        viz_g = int(self._settings.value("visualizer/color_g", 220))
        viz_b = int(self._settings.value("visualizer/color_b", 255))
        viz_color = (viz_r, viz_g, viz_b)
        self.cover_wallpaper_toggle = bool(self._settings.value("background/cover_toggle", False, type=bool))
        self.path_provider = PathProvider()

        self.setWindowTitle("Quantis")
        # Широкая ширина, обычная высота — чтобы всё было видно
        self.resize(1100, 750)
        self.setMaximumSize(1920, 1080)
        self._center_on_screen()

        # ================== ЦЕНТРАЛЬНЫЙ ВИДЖЕТ ==================
        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)

        # ================== ФОН ==================
        self.background = QLabel(central)
        try:
            self._settings.value("visualizer/bg")
            self.background.setPixmap(
                QPixmap(asset_path(self._settings.value("visualizer/bg")))
            )
        except Exception:
            self.background.setPixmap(
                QPixmap(asset_path("assets/background/default.jpg"))
            )
        self.background.setScaledContents(True)

        # ================== ТЕМНОЕ ПЕРЕКРЫТИЕ ==================
        self.dark_overlay = QFrame(central)
        self.dark_overlay.setObjectName("darkOverlay")

        # ================== ВИЗУАЛИЗАТОР (под контентом) ==================
        self.visualizer = AudioVisualizer(
            central,
            bar_count=56,
            height=120,
            delay_ms=viz_delay,
            color_rgb=viz_color,
            mode=viz_mode,
        )

        # Порядок слоев: фон < затемнение < визуализатор < контент
        self.background.lower()
        self.dark_overlay.stackUnder(self.visualizer)

        # ================== ОСНОВНОЙ LAYOUT ==================
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ================== КОНТЕНТ (ЛЕВО + ПРАВО) ==================
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # -------- ЛЕВОЕ МЕНЮ --------
        self.menu_tabs = MenuTabs()
        self.menu_tabs.setMaximumWidth(10)
        self.menu_tabs.setAttribute(Qt.WA_TranslucentBackground)

        content_layout.addWidget(self.menu_tabs,)

        # -------- ПРАВАЯ ЧАСТЬ --------
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.stack = Stack()
        right_layout.addWidget(self.stack, stretch=1)

        # -------- ПАНЕЛЬ ПЛЕЕРА (СНИЗУ) --------
        self.play_menu = PlayMenu()
        self.play_menu.setFixedHeight(90)
        self.play_menu.setAttribute(Qt.WA_TranslucentBackground)

        right_layout.addWidget(self.play_menu)

        content_layout.addLayout(right_layout)
        main_layout.addLayout(content_layout)

        # ================== СВЯЗЬ МЕНЮ -> STACK ==================
        self.menu_tabs.page_changed.connect(self.stack.switch_to)

        # ================== СВЯЗЬ HOME -> PLAYLIST PAGE ==================
        self.stack.home_page.playlist_opened.connect(self._open_playlist)

        #
        self._toggle_viz(self.viz_toggle)
        self.stack.settings_page.set_toggle_flags(self.viz_toggle, self.cover_wallpaper_toggle)

        # ================== СВЯЗЬ НАСТРОЕК ==================
        self.stack.settings_page.background_changed.connect(self._change_bg)
        self.stack.settings_page.visualizer_toggled.connect(self._toggle_viz)
        self.stack.settings_page.visualizer_delay_changed.connect(
            self._set_visualizer_delay
        )
        self.stack.settings_page.visualizer_color_changed.connect(
            self._set_visualizer_color
        )
        self.stack.settings_page.visualizer_mode_changed.connect(
            self._set_visualizer_mode
        )
        self.stack.settings_page.set_visualizer_settings(viz_delay, viz_color, viz_mode)
        self.stack.settings_page.cover_wallpaper_toggled.connect(self._change_dynamic_wallpaper)
        self.play_menu.player.track_changed.connect(self._change_bg_from_track)

        self.play_menu.playlist_generated.connect(self.display_radio_on_home)

    # ================== ОТКРЫТИЕ ПЛЕЙЛИСТА ==================
    @asyncSlot(object)
    async def _open_playlist(self, playlist) -> None:
        await self.stack.open_playlist(playlist)

    # ================== СМЕНА ФОНА ==================
    def _change_bg(self, path: str) -> None:
        pm = QPixmap(path)
        self._settings.setValue("visualizer/bg", path)
        if not pm.isNull():
            self.background.setPixmap(pm)

    def _change_bg_from_track(self, track):
        if not self.cover_wallpaper_toggle: return
        path = self.path_provider.get_cover_path(track)
        if os.path.exists(path):
            self._change_bg(path)

    # ================== ВКЛ/ВЫКЛ ВИЗУАЛИЗАТОРА ==================
    def _toggle_viz(self, on: bool) -> None:
        if on:
            self._settings.setValue("vizualizer/toggle", True)
            self.visualizer.show()
        else:
            self.visualizer.hide()
            self._settings.setValue("vizualizer/toggle", False)

    def _set_visualizer_delay(self, delay_ms: int) -> None:
        self.visualizer.set_delay_ms(delay_ms)
        self._settings.setValue("visualizer/delay_ms", int(delay_ms))

    def _set_visualizer_color(self, rgb: tuple[int, int, int]) -> None:
        self.visualizer.set_color_rgb(rgb)
        self._settings.setValue("visualizer/color_r", int(rgb[0]))
        self._settings.setValue("visualizer/color_g", int(rgb[1]))
        self._settings.setValue("visualizer/color_b", int(rgb[2]))

    def _set_visualizer_mode(self, mode: str) -> None:
        self.visualizer.set_mode(mode)
        self._settings.setValue("visualizer/mode", str(mode))

    def _center_on_screen(self) -> None:
        """Размещает окно по центру экрана."""
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            frame = self.frameGeometry()
            frame.moveCenter(available.center())
            self.move(frame.topLeft())

    # ================== ИЗМЕНЕНИЕ РАЗМЕРА ==================
    def resizeEvent(self, event) -> None:
        self.background.resize(self.size())
        self.dark_overlay.resize(self.size())

        # Визуализатор: во всю ширину и по центру по вертикали.
        viz_h = self.visualizer.height()
        self.visualizer.setGeometry(
            0,
            (self.height() - viz_h) // 2,
            self.width(),
            viz_h,
        )

        super().resizeEvent(event)

    def _change_dynamic_wallpaper(self, flag: bool):
        self._settings.setValue("background/cover_toggle", flag)
        self.cover_wallpaper_toggle = flag

    def display_radio_on_home(self, playlist):
        self.stack.home_page.add_recommendation_section(playlist)
        self.stack.setCurrentWidget(self.stack.home_page)
        self.menu_tabs.set_active_tab(0)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = Quantis()
    window.show()

    sys.exit(app.exec())