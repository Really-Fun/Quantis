"""Главное окно приложения."""
import sys

from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtCore import QSettings, Qt
from qasync import asyncSlot

from ui.MenuPlayWidget import PlayMenu
from ui.MenuTabsWidget import MenuTabs
from ui.Stack import Stack
from ui.AudioVisualizer import AudioVisualizer


class NeonMusic(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings("CleanPlayer", "NeonMusic")
        viz_delay = int(self._settings.value("visualizer/delay_ms", 25))
        viz_mode = str(self._settings.value("visualizer/mode", "smooth"))
        viz_r = int(self._settings.value("visualizer/color_r", 0))
        viz_g = int(self._settings.value("visualizer/color_g", 220))
        viz_b = int(self._settings.value("visualizer/color_b", 255))
        viz_color = (viz_r, viz_g, viz_b)

        self.setWindowTitle("NeonMusic")
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
        self.background.setPixmap(QPixmap("assets/background/real.jpg"))
        self.background.setScaledContents(True)

        # ================== ТЕМНОЕ ПЕРЕКРЫТИЕ ==================
        self.dark_overlay = QFrame(central)
        self.dark_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 150);
            }
        """)

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
        self.menu_tabs.setFixedWidth(self.width() // 3)
        self.menu_tabs.setAttribute(Qt.WA_TranslucentBackground)

        content_layout.addWidget(self.menu_tabs)

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

        # ================== СВЯЗЬ НАСТРОЕК ==================
        self.stack.settings_page.background_changed.connect(self._change_bg)
        self.stack.settings_page.visualizer_toggled.connect(self._toggle_viz)
        self.stack.settings_page.visualizer_delay_changed.connect(self._set_visualizer_delay)
        self.stack.settings_page.visualizer_color_changed.connect(self._set_visualizer_color)
        self.stack.settings_page.visualizer_mode_changed.connect(self._set_visualizer_mode)
        self.stack.settings_page.set_visualizer_settings(viz_delay, viz_color, viz_mode)

        # ================== ОБЩИЙ СТИЛЬ ==================
        self.setStyleSheet("""
            QWidget#central {
                background: transparent;
            }
            QWidget {
                background: transparent;
            }
        """)

    # ================== ОТКРЫТИЕ ПЛЕЙЛИСТА ==================
    @asyncSlot(object)
    async def _open_playlist(self, playlist) -> None:
        await self.stack.open_playlist(playlist)

    # ================== СМЕНА ФОНА ==================
    def _change_bg(self, path: str) -> None:
        pm = QPixmap(path)
        if not pm.isNull():
            self.background.setPixmap(pm)

    # ================== ВКЛ/ВЫКЛ ВИЗУАЛИЗАТОРА ==================
    def _toggle_viz(self, on: bool) -> None:
        if on:
            self.visualizer.show()
        else:
            self.visualizer.hide()

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
        """Размещает окно по центру доступной области экрана."""
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


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NeonMusic()
    window.show()

    sys.exit(app.exec())
