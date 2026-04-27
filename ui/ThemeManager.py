from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtGui import QColor
import os

class _ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._settings = QSettings("ReallyFun", "Quantis")
        self.current_theme = self._settings.value("theme/current", "dark")
        
        self._colors = {
            "dark": {
                "search_line": QColor(0, 220, 255),
                "toggle_on": QColor(0, 200, 240, 180),
                "toggle_off_track": QColor(60, 60, 70, 200),
                "toggle_on_thumb": QColor(255, 255, 255),
                "toggle_off_thumb": QColor(160, 160, 170),
                "card_bg": QColor(255, 255, 255),
            },
            "light": {
                "search_line": QColor(0, 150, 210),
                "toggle_on": QColor(0, 150, 210, 180),
                "toggle_off_track": QColor(200, 200, 200, 200),
                "toggle_on_thumb": QColor(255, 255, 255),
                "toggle_off_thumb": QColor(100, 100, 100),
                "card_bg": QColor(0, 0, 0),
            }
        }

    def get_color(self, name: str) -> QColor:
        """Получаем цвет подходящий текущей теме"""
        theme_colors = self._colors.get(self.current_theme, self._colors["dark"])
        return theme_colors.get(name, QColor(0, 220, 255))

    def set_theme(self, theme_name: str, app=None):
        """Установить переданную тему."""
        if theme_name not in ["dark", "light"]:
            theme_name = "dark"
        self.current_theme = theme_name
        self._settings.setValue("theme/current", theme_name)
        
        if app:
            self.apply_theme_to_app(app)
        elif hasattr(self, "global_app"):
            self.apply_theme_to_app(self.global_app)

        self.theme_changed.emit(theme_name)

    def apply_theme_to_app(self, app):
        """Применяем тему к приложению"""
        qss_path = f"styles/{self.current_theme}.qss"
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        self.global_app = app

ThemeManager = _ThemeManager()
