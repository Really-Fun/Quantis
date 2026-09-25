"""Пользовательские настройки интерфейса (QSettings)."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QObject, QSettings, Signal, SignalInstance

from quantis.models.repeat_mode import RepeatMode
from quantis.ui.resources import normalize_ui_theme
from quantis.ui.themes import registry
from quantis.ui.themes.spec import ThemeSpec


class UiPreferences(QObject):
    """Синглтон настроек UI.

    Сигналы по смыслу: слушай только то, от чего зависишь. ``changed`` —
    для совместимости с плагинами (любая пользовательская настройка, кроме
    громкости, повтора, геометрии окна и служебных полей обновлений); внутри
    приложения на него не подписываемся.
    """

    changed = Signal()
    theme_changed = Signal()
    # Статичные и динамические (видео) обои: вкл/выкл, путь, качество, fps, задержка.
    wallpaper_changed = Signal()
    # Панели главной и «Сейчас играет».
    layout_changed = Signal()
    eco_changed = Signal()
    volume_changed = Signal(int)

    _instance: UiPreferences | None = None

    _KEY_HOME_FEATURED = "ui/show_home_featured_panel"
    _KEY_UI_THEME = "ui/theme"
    _KEY_DYNAMIC_WALLPAPER = "ui/dynamic_wallpaper"
    _KEY_WALLPAPER_QUALITY = "ui/dynamic_wallpaper_quality"
    _KEY_WALLPAPER_FPS = "ui/dynamic_wallpaper_fps"
    _KEY_WALLPAPER_AV_DELAY = "ui/dynamic_wallpaper_av_delay_ms"
    _KEY_WALLPAPER = "ui/wallpaper_path"
    _KEY_WALLPAPER_ENABLED = "ui/wallpaper_enabled"
    _KEY_NOW_PLAYING = "ui/show_now_playing_panel"
    _KEY_BACKGROUND_ECO = "ui/background_eco"
    _KEY_VOLUME = "playback/volume"
    _KEY_REPEAT_MODE = "playback/repeat_mode"
    _KEY_MUSIC_DIR = "storage/music_dir"
    _KEY_WINDOW_GEOMETRY = "ui/window_geometry"
    _KEY_UPDATE_LAST_CHECK = "updates/last_check_at"
    _KEY_UPDATE_LAST_TAG = "updates/last_tag"
    _KEY_UPDATE_LAST_URL = "updates/last_html_url"
    _KEY_UPDATE_DISMISSED_TAG = "updates/dismissed_tag"
    _KEY_UPDATE_CHECK_ON_STARTUP = "updates/check_on_startup"

    def __new__(cls) -> UiPreferences:
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._initialized = False
            cls._instance = obj
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        super().__init__()
        self._settings = QSettings("ReallyFun", "Quantis")
        self._initialized = True

    def _emit(self, signal: SignalInstance) -> None:
        signal.emit()
        self.changed.emit()

    @staticmethod
    def _read_bool(raw: object, default: bool) -> bool:
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes")
        if raw is None:
            return default
        return bool(raw)

    @staticmethod
    def _read_int(raw: object, default: int) -> int:
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_float(raw: object, default: float) -> float:
        try:
            return float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    @property
    def show_home_featured_panel(self) -> bool:
        return self._read_bool(
            self._settings.value(self._KEY_HOME_FEATURED, True),
            True,
        )

    def set_show_home_featured_panel(self, value: bool) -> None:
        if self.show_home_featured_panel == value:
            return
        self._settings.setValue(self._KEY_HOME_FEATURED, value)
        self._emit(self.layout_changed)

    @property
    def show_now_playing_panel(self) -> bool:
        return self._read_bool(
            self._settings.value(self._KEY_NOW_PLAYING, True),
            True,
        )

    def set_show_now_playing_panel(self, value: bool) -> None:
        if self.show_now_playing_panel == value:
            return
        self._settings.setValue(self._KEY_NOW_PLAYING, value)
        self._emit(self.layout_changed)

    @property
    def ui_theme(self) -> str:
        raw = self._settings.value(self._KEY_UI_THEME, registry.DEFAULT_ID)
        return normalize_ui_theme(str(raw) if raw is not None else None)

    @property
    def theme(self) -> ThemeSpec:
        """Описание текущей темы."""
        return registry.get(self.ui_theme)

    def set_ui_theme(self, theme_id: str) -> None:
        theme_id = normalize_ui_theme(theme_id)
        if self.ui_theme == theme_id:
            return
        self._settings.setValue(self._KEY_UI_THEME, theme_id)
        self._emit(self.theme_changed)

    @property
    def dynamic_wallpaper_enabled(self) -> bool:
        return self._read_bool(
            self._settings.value(self._KEY_DYNAMIC_WALLPAPER, False),
            False,
        )

    def set_dynamic_wallpaper_enabled(self, value: bool) -> None:
        if self.dynamic_wallpaper_enabled == value:
            return
        self._settings.setValue(self._KEY_DYNAMIC_WALLPAPER, value)
        self._emit(self.wallpaper_changed)

    @property
    def dynamic_wallpaper_quality(self) -> int:
        from quantis.services.wallpaper_policy import (
            WALLPAPER_DEFAULT_QUALITY,
            clamp_wallpaper_quality,
        )

        raw = self._settings.value(
            self._KEY_WALLPAPER_QUALITY, WALLPAPER_DEFAULT_QUALITY
        )
        return clamp_wallpaper_quality(self._read_int(raw, WALLPAPER_DEFAULT_QUALITY))

    def set_dynamic_wallpaper_quality(self, value: int) -> None:
        from quantis.services.wallpaper_policy import clamp_wallpaper_quality

        clamped = clamp_wallpaper_quality(int(value))
        if self.dynamic_wallpaper_quality == clamped:
            return
        self._settings.setValue(self._KEY_WALLPAPER_QUALITY, clamped)
        self._emit(self.wallpaper_changed)

    @property
    def dynamic_wallpaper_fps(self) -> int:
        from quantis.services.wallpaper_policy import (
            WALLPAPER_DEFAULT_FPS,
            clamp_wallpaper_fps,
        )

        raw = self._settings.value(self._KEY_WALLPAPER_FPS, WALLPAPER_DEFAULT_FPS)
        return clamp_wallpaper_fps(self._read_int(raw, WALLPAPER_DEFAULT_FPS))

    def set_dynamic_wallpaper_fps(self, value: int) -> None:
        from quantis.services.wallpaper_policy import clamp_wallpaper_fps

        clamped = clamp_wallpaper_fps(int(value))
        if self.dynamic_wallpaper_fps == clamped:
            return
        self._settings.setValue(self._KEY_WALLPAPER_FPS, clamped)
        self._emit(self.wallpaper_changed)

    @property
    def dynamic_wallpaper_av_delay_ms(self) -> int:
        """На сколько видео-фон отстаёт от позиции звука (задержка аудиовыхода)."""
        from quantis.services.wallpaper_policy import (
            WALLPAPER_DEFAULT_AV_DELAY_MS,
            clamp_wallpaper_av_delay,
        )

        raw = self._settings.value(
            self._KEY_WALLPAPER_AV_DELAY, WALLPAPER_DEFAULT_AV_DELAY_MS
        )
        return clamp_wallpaper_av_delay(
            self._read_int(raw, WALLPAPER_DEFAULT_AV_DELAY_MS)
        )

    def set_dynamic_wallpaper_av_delay_ms(self, value: int) -> None:
        from quantis.services.wallpaper_policy import clamp_wallpaper_av_delay

        clamped = clamp_wallpaper_av_delay(value)
        if self.dynamic_wallpaper_av_delay_ms == clamped:
            return
        self._settings.setValue(self._KEY_WALLPAPER_AV_DELAY, clamped)
        self._emit(self.wallpaper_changed)

    @property
    def wallpaper_path(self) -> str:
        raw = self._settings.value(self._KEY_WALLPAPER, "")
        return str(raw).strip() if raw else ""

    def set_wallpaper_path(self, path: str) -> None:
        normalized = path.strip()
        if self.wallpaper_path == normalized:
            return
        self._settings.setValue(self._KEY_WALLPAPER, normalized)
        self._emit(self.wallpaper_changed)

    @property
    def wallpaper_enabled(self) -> bool:
        return self._read_bool(
            self._settings.value(self._KEY_WALLPAPER_ENABLED, False),
            False,
        )

    def set_wallpaper_enabled(self, value: bool) -> None:
        if self.wallpaper_enabled == value:
            return
        self._settings.setValue(self._KEY_WALLPAPER_ENABLED, value)
        self._emit(self.wallpaper_changed)

    @property
    def background_eco_enabled(self) -> bool:
        """Экономия ресурсов, пока окно свёрнуто / не в фокусе (игры)."""
        return self._read_bool(
            self._settings.value(self._KEY_BACKGROUND_ECO, True),
            True,
        )

    def set_background_eco_enabled(self, value: bool) -> None:
        if self.background_eco_enabled == value:
            return
        self._settings.setValue(self._KEY_BACKGROUND_ECO, value)
        self._emit(self.eco_changed)

    @property
    def volume(self) -> int:
        raw = self._settings.value(self._KEY_VOLUME, 80)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 80
        return max(0, min(100, value))

    def set_volume(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        if self.volume == clamped:
            return
        self._settings.setValue(self._KEY_VOLUME, clamped)
        self.volume_changed.emit(clamped)

    @property
    def repeat_mode(self) -> RepeatMode:
        raw = self._settings.value(self._KEY_REPEAT_MODE, RepeatMode.PLAYLIST.value)
        return RepeatMode.from_value(str(raw) if raw is not None else None)

    def set_repeat_mode(self, mode: RepeatMode) -> None:
        if self.repeat_mode == mode:
            return
        self._settings.setValue(self._KEY_REPEAT_MODE, mode.value)

    @property
    def window_geometry(self) -> QByteArray | None:
        raw = self._settings.value(self._KEY_WINDOW_GEOMETRY)
        if isinstance(raw, QByteArray) and not raw.isEmpty():
            return raw
        if isinstance(raw, (bytes, bytearray)) and raw:
            return QByteArray(bytes(raw))
        return None

    def set_window_geometry(self, geometry: QByteArray) -> None:
        self._settings.setValue(self._KEY_WINDOW_GEOMETRY, geometry)
        self._settings.sync()

    @property
    def music_dir(self) -> str:
        """Папка для скачанных треков. Пусто — каталог по умолчанию."""
        raw = self._settings.value(self._KEY_MUSIC_DIR, "")
        return str(raw).strip() if raw else ""

    def set_music_dir(self, path: str) -> None:
        from quantis.utils import app_paths

        normalized = path.strip()
        if self.music_dir == normalized:
            return
        self._settings.setValue(self._KEY_MUSIC_DIR, normalized)
        self._settings.sync()
        app_paths.reset_music_dir_cache()
        self.changed.emit()

    @property
    def update_check_on_startup(self) -> bool:
        return self._read_bool(
            self._settings.value(self._KEY_UPDATE_CHECK_ON_STARTUP, True),
            True,
        )

    def set_update_check_on_startup(self, value: bool) -> None:
        if self.update_check_on_startup == value:
            return
        self._settings.setValue(self._KEY_UPDATE_CHECK_ON_STARTUP, value)

    @property
    def update_last_check_at(self) -> float:
        return self._read_float(
            self._settings.value(self._KEY_UPDATE_LAST_CHECK, 0),
            0.0,
        )

    def set_update_last_check_at(self, value: float) -> None:
        self._settings.setValue(self._KEY_UPDATE_LAST_CHECK, int(value))

    @property
    def update_last_tag(self) -> str:
        raw = self._settings.value(self._KEY_UPDATE_LAST_TAG, "")
        return str(raw).strip() if raw else ""

    def set_update_last_tag(self, tag: str) -> None:
        self._settings.setValue(self._KEY_UPDATE_LAST_TAG, tag.strip())

    @property
    def update_last_html_url(self) -> str:
        raw = self._settings.value(self._KEY_UPDATE_LAST_URL, "")
        return str(raw).strip() if raw else ""

    def set_update_last_html_url(self, url: str) -> None:
        self._settings.setValue(self._KEY_UPDATE_LAST_URL, url.strip())

    @property
    def update_dismissed_tag(self) -> str:
        raw = self._settings.value(self._KEY_UPDATE_DISMISSED_TAG, "")
        return str(raw).strip() if raw else ""

    def set_update_dismissed_tag(self, tag: str) -> None:
        self._settings.setValue(self._KEY_UPDATE_DISMISSED_TAG, tag.strip())
