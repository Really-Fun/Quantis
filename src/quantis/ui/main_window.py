from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPropertyAnimation, QRect, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from quantis.core.bootstrap import ApplicationBundle
from quantis.core.eco_mode import EcoMode
from quantis.ui import resources
from quantis.ui.accent import AccentStyles
from quantis.ui.controllers.dynamic_wallpaper import DynamicWallpaperController
from quantis.ui.cover_accent import (
    CoverPalette,
    fallback_accent,
    fallback_palette,
    load_cover_image,
    palette_from_accent,
    palette_from_image,
)
from quantis.ui.fonts import register_bundled_fonts, theme_font
from quantis.ui.live_palette import LivePalette
from quantis.ui.preferences import UiPreferences
from quantis.ui.shortcuts import (
    ALT_PAGE_IDS,
    VOLUME_STEP,
    is_arrow_navigation_target,
    is_space_target,
    is_typing_target,
)
from quantis.ui.themes import registry
from quantis.ui.ui_extensions import NavExtension, UiExtensionHost
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.viewmodels.player_vm import PlayerViewModel
from quantis.ui.viewmodels.playlist_vm import PlaylistViewModel
from quantis.ui.viewmodels.search_vm import SearchViewModel
from quantis.ui.viewmodels.stats_vm import StatsViewModel
from quantis.ui.views.home_page import HomePage
from quantis.ui.views.member_page import MemberPage
from quantis.ui.views.player_bar import PlayerBar
from quantis.ui.views.playlist_page import PlaylistPage
from quantis.ui.views.plugins_page import PluginsPage
from quantis.ui.views.search_page import SearchPage
from quantis.ui.views.settings_page import SettingsPage
from quantis.ui.views.stats_page import StatsPage
from quantis.ui.views.widgets.app_header import AppHeader
from quantis.ui.views.widgets.background_frame import BackgroundFrame
from quantis.ui.views.widgets.now_playing_fullscreen import NowPlayingFullscreen
from quantis.ui.views.widgets.now_playing_panel import NowPlayingPanel
from quantis.ui.views.widgets.resize_grips import WindowResizeGrips
from quantis.ui.views.widgets.side_nav import SideNavRail
from quantis.ui.views.widgets.update_banner import UpdateBanner
from quantis.ui.views.widgets.wallpaper_backdrop import BodyWithWallpaper


class QuantisMainWindow(QMainWindow):
    """Главное окно приложения.

    Страницы в QStackedWidget (индексы):
      0 Home, 1 Search, 2 Library, 3 Stats, 4 Plugins, 5 Member, 6 Settings,
      7 Playlist (overlay, не в боковом nav), 8+ — страницы плагинов.

    Страницы 1–6 и 7 создаются лениво через ``_ensure_*_page`` при первом
    переходе (в stack изначально стоят пустые QWidget-заглушки).
    """

    PAGE_HOME = 0
    PAGE_SEARCH = 1
    PAGE_LIBRARY = 2
    PAGE_STATS = 3
    PAGE_PLUGINS = 4
    PAGE_MEMBER = 5
    PAGE_SETTINGS = 6
    PAGE_PLAYLIST = 7
    _CORE_STACK_COUNT = 8

    _PAGE_META = {
        PAGE_HOME: ("Главная", ""),
        PAGE_SEARCH: ("Поиск", ""),
        PAGE_LIBRARY: ("Библиотека", ""),
        PAGE_STATS: ("Статистика", ""),
        PAGE_PLUGINS: ("Плагины", ""),
        PAGE_MEMBER: ("Member", ""),
        PAGE_SETTINGS: ("Настройки", ""),
    }

    def __init__(self, bundle: ApplicationBundle, parent=None) -> None:
        super().__init__(parent)

        register_bundled_fonts()

        self._bundle = bundle
        self._bridge = bundle.async_bridge
        self.setWindowTitle("Quantis")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(1024, 640)
        self._ui_prefs = UiPreferences()
        self._restore_window_geometry()
        self._resize_grips = WindowResizeGrips(self)
        self._current_page = -1
        self._accent = fallback_accent(self._ui_prefs.theme)
        self._cover_palette: CoverPalette | None = None
        """Палитра обложки текущего трека; None — обложки нет, палитра от темы."""

        self._player_vm = PlayerViewModel(
            bundle.playback,
            bundle.player,
            bundle.event_bus,
        )
        self._search_vm = SearchViewModel(
            bundle.music.finder,
            bundle.playback,
            self._bridge,
            parent=self,
        )
        self._home_vm = HomeViewModel(
            bundle.history,
            bundle.playback,
            bundle.music,
            parent=self,
        )
        self._playlist_vm = PlaylistViewModel(
            bundle.playback,
            bridge=self._bridge,
            parent=self,
        )
        self._stats_vm = StatsViewModel(
            bundle.history,
            bundle.playback,
            parent=self,
        )
        self._return_page_id = self.PAGE_HOME
        self._applied_theme = ""
        self._page_meta = dict(self._PAGE_META)
        self._plugin_page_ids: dict[str, int] = {}
        self._eco = EcoMode(self)
        self._eco.set_pref_enabled(self._ui_prefs.background_eco_enabled)

        shell = BackgroundFrame(
            resources.wallpaper_path(),
            theme=self._ui_prefs.theme,
        )
        self.setCentralWidget(shell)
        self._shell = shell

        root = QVBoxLayout(shell.content_host())
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._chrome_hidden = False
        self._header = AppHeader()
        self._header.minimize_requested.connect(self.showMinimized)
        self._header.maximize_requested.connect(self._toggle_maximize)
        self._header.close_requested.connect(self.close)
        self._header.hide_ui_requested.connect(self._toggle_chrome_hidden)
        root.addWidget(self._header)

        self._update_banner = UpdateBanner()
        self._update_banner.open_requested.connect(self._open_cached_release)
        self._update_banner.dismiss_requested.connect(self._dismiss_update_banner)
        root.addWidget(self._update_banner)

        self._body_shell = BodyWithWallpaper(
            resources.wallpaper_path(),
            theme=self._ui_prefs.theme,
            compositor=shell.compositor,
        )
        body = self._body_shell.layout_host
        body.setContentsMargins(10, 10, 10, 0)
        body.setSpacing(10)

        self._nav = SideNavRail()
        self._nav.page_changed.connect(self._on_page_changed)

        # Content column
        content_host = QWidget()
        self._content_host = content_host
        content = QVBoxLayout(content_host)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setObjectName("pageStack")

        self._home_page = HomePage(self._home_vm, self._bridge, self._ui_prefs)
        self._library_page = None
        self._search_page: SearchPage | None = None
        self._stats_page: StatsPage | None = None
        self._plugins_page: PluginsPage | None = None
        self._member_page: MemberPage | None = None
        self._settings_page: SettingsPage | None = None
        self._playlist_page: PlaylistPage | None = None

        self._stack.addWidget(self._home_page)  # 0
        self._stack.addWidget(QWidget())  # 1 SEARCH
        self._stack.addWidget(QWidget())  # 2 LIBRARY (lazy)
        self._stack.addWidget(QWidget())  # 3 STATS
        self._stack.addWidget(QWidget())  # 4 PLUGINS
        self._stack.addWidget(QWidget())  # 5 MEMBER
        self._stack.addWidget(QWidget())  # 6 SETTINGS
        self._stack.addWidget(QWidget())  # 7 PLAYLIST

        self._home_page.playlist_open_requested.connect(self._open_playlist_page)

        content.addWidget(self._stack, stretch=1)

        self._now_playing = NowPlayingPanel(
            bundle.music.provider,
            bridge=self._bridge,
            music=bundle.music,
        )
        self._now_playing.lyrics_requested.connect(self._open_now_playing_fullscreen)

        self._np_fullscreen = NowPlayingFullscreen(bundle.music.provider, parent=shell)
        self._np_fullscreen.closed.connect(self._np_fullscreen.hide)
        self._np_fullscreen.hide()

        mid = QWidget()
        mid_layout = QHBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(10)
        mid_layout.addWidget(self._nav)
        mid_layout.addWidget(content_host, stretch=1)
        mid_layout.addWidget(self._now_playing)

        columns = QVBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        columns_host = QWidget()
        columns_host.setLayout(columns)
        columns.addWidget(mid, stretch=1)

        self._player_bar = PlayerBar(
            self._player_vm,
            bundle.music.provider,
            bridge=self._bridge,
            music=bundle.music,
            on_liked_changed=lambda: self._bridge.schedule(
                self._home_vm.refresh_liked(self._bridge)
            ),
            on_playlists_changed=lambda: self._bridge.schedule(
                self._home_vm.refresh_user_playlists(self._bridge)
            ),
        )
        self._player_bar.now_playing_toggle_requested.connect(self._toggle_now_playing)
        self._player_bar.hide_ui_requested.connect(self._toggle_chrome_hidden)
        columns.addWidget(self._player_bar)

        body.addWidget(columns_host, stretch=1)
        root.addWidget(self._body_shell, stretch=1)

        for view_model in (
            self._player_vm,
            self._search_vm,
            self._home_vm,
            self._playlist_vm,
        ):
            view_model.error_occurred.connect(self._show_error)

        bundle.event_bus.track_changed.connect(self._sync_playing_track)
        LivePalette.instance().palette_changed.connect(self._on_live_palette)
        bundle.event_bus.history_updated.connect(self._on_history_updated)
        bundle.event_bus.playlists_updated.connect(self._on_playlists_updated)
        bundle.event_bus.queue_extended.connect(self._on_queue_extended)
        bundle.event_bus.error_occurred.connect(self._show_error)
        self._search_vm.download_finished.connect(
            lambda: self._home_vm.refresh_downloaded(self._bridge)
        )
        self._playlist_vm.tracks_mutated.connect(self._on_playlist_tracks_mutated)
        self._ui_prefs.theme_changed.connect(self._on_theme_changed)
        self._ui_prefs.wallpaper_changed.connect(self._on_wallpaper_changed)
        self._wallpaper_source = (
            resources.wallpaper_path(),
            self._ui_prefs.dynamic_wallpaper_enabled,
        )
        self._apply_backdrop_look()
        self._ui_prefs.layout_changed.connect(self._sync_now_playing_visibility)
        self._ui_prefs.eco_changed.connect(self._on_eco_pref_changed)
        self._dynamic_wallpaper = DynamicWallpaperController(
            self._body_shell.backdrop,
            bundle.music,
            bundle.async_bridge,
            self._ui_prefs,
            bundle.event_bus,
            playback=bundle.playback,
            parent=self,
        )
        self._eco.subscribe(self._apply_eco)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)
            app.installEventFilter(self)
            app.focusChanged.connect(self._sync_shortcut_enabled)
        self._install_shortcuts()
        self._refresh_eco_state()
        self._apply_ui_theme(self._ui_prefs.ui_theme)
        self._sync_now_playing_visibility()
        self._mounted_layers: dict[str, QWidget] = {}
        self._extensions = UiExtensionHost.instance()
        self._extensions.pages_changed.connect(self._sync_plugin_pages)
        self._extensions.background_layers_changed.connect(self._sync_background_layers)
        self._sync_plugin_pages()
        self._sync_background_layers()
        self._on_page_changed(self.PAGE_HOME)
        # Данные главной — после первого кадра, чтобы не тормозить show().
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: self._home_vm.request_load(self._bridge))
        QTimer.singleShot(0, self._maybe_check_for_update)

    def _on_app_state_changed(self, state) -> None:
        self._refresh_eco_state()

    def _refresh_eco_state(self) -> None:
        app = QApplication.instance()
        inactive = (
            app is not None
            and app.applicationState() != Qt.ApplicationState.ApplicationActive
        )
        self._eco.set_window_background(inactive or self.isMinimized())

    def _apply_eco(self, active: bool) -> None:
        self._shell.set_eco(active)
        self._player_vm.set_eco(active)
        self._bundle.history_watcher.set_eco(active)
        self._bundle.music.streamer.set_eco(active)
        self._dynamic_wallpaper.set_eco(active)
        for widget in getattr(self, "_mounted_layers", {}).values():
            setter = getattr(widget, "set_eco", None)
            if callable(setter):
                setter(active)

    def _toggle_now_playing(self) -> None:
        self._ui_prefs.set_show_now_playing_panel(
            not self._ui_prefs.show_now_playing_panel
        )

    def _toggle_chrome_hidden(self) -> None:
        self._set_chrome_hidden(not self._chrome_hidden)

    def _set_chrome_hidden(self, hidden: bool) -> None:
        if self._chrome_hidden == hidden:
            return
        self._chrome_hidden = hidden
        self._nav.setVisible(not hidden)
        self._content_host.setVisible(not hidden)
        if hidden:
            self._update_banner.hide()
            self._now_playing.hide()
            if self._np_fullscreen.isVisible():
                self._np_fullscreen.hide()
            self._body_shell.layout_host.setContentsMargins(0, 0, 0, 0)
        else:
            self._body_shell.layout_host.setContentsMargins(10, 10, 10, 0)
            self._sync_update_banner()
            self._sync_now_playing_visibility()
        self._body_shell.set_theater_mode(hidden)
        self._shell.set_cinematic(hidden)
        self._player_bar.set_cinematic(hidden)
        if hidden:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._sync_shortcut_enabled()

    def _event_from_this_window(self, obj) -> bool:
        if obj is self:
            return True
        if isinstance(obj, QWidget):
            return obj.window() is self
        return False

    def _install_shortcuts(self) -> None:
        self._sc_hide = self._make_shortcut("S", self._toggle_chrome_hidden)
        self._sc_pause = self._make_shortcut(
            Qt.Key.Key_Space, self._player_vm.toggle_pause
        )
        self._sc_like = self._make_shortcut("L", self._player_bar.toggle_like)
        self._sc_prev = self._make_shortcut(
            Qt.Key.Key_Left, self._player_vm.play_previous
        )
        self._sc_next = self._make_shortcut(Qt.Key.Key_Right, self._player_vm.play_next)
        self._sc_repeat = self._make_shortcut("R", self._player_vm.cycle_repeat_mode)
        self._sc_vol_up = self._make_shortcut(
            Qt.Key.Key_Up, lambda: self._player_vm.nudge_volume(VOLUME_STEP)
        )
        self._sc_vol_up.setAutoRepeat(True)
        self._sc_vol_down = self._make_shortcut(
            Qt.Key.Key_Down, lambda: self._player_vm.nudge_volume(-VOLUME_STEP)
        )
        self._sc_vol_down.setAutoRepeat(True)
        self._sc_pages: list[QShortcut] = []
        for index, page_id in enumerate(ALT_PAGE_IDS, start=1):
            self._sc_pages.append(
                self._make_shortcut(
                    f"Alt+{index}",
                    lambda pid=page_id: self._goto_page(pid),
                )
            )
        self._make_shortcut("Alt+M", lambda: self._goto_page(self.PAGE_MEMBER))
        self._make_shortcut("Alt+S", lambda: self._goto_page(self.PAGE_SETTINGS))
        self._sync_shortcut_enabled()

    def _make_shortcut(self, key, slot) -> QShortcut:
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        shortcut.setAutoRepeat(False)
        shortcut.activated.connect(slot)
        return shortcut

    def _goto_page(self, page_id: int) -> None:
        if self._chrome_hidden:
            self._set_chrome_hidden(False)
        if self._stack.currentIndex() == self.PAGE_PLAYLIST:
            self._current_page = -1
        self._apply_page(page_id)

    def _sync_shortcut_enabled(self, *_) -> None:
        focus = QApplication.focusWidget()
        typing = is_typing_target(focus)
        arrows = is_arrow_navigation_target(focus)
        space = is_space_target(focus)
        hidden = self._chrome_hidden
        if getattr(self, "_sc_hide", None) is not None:
            self._sc_hide.setEnabled(hidden or not typing)
        if getattr(self, "_sc_like", None) is not None:
            self._sc_like.setEnabled(hidden or not typing)
            self._sc_repeat.setEnabled(hidden or not typing)
        if getattr(self, "_sc_pause", None) is not None:
            self._sc_pause.setEnabled(hidden or not (typing or space))
        if getattr(self, "_sc_vol_up", None) is not None:
            enabled = hidden or not arrows
            self._sc_vol_up.setEnabled(enabled)
            self._sc_vol_down.setEnabled(enabled)
            self._sc_prev.setEnabled(enabled)
            self._sc_next.setEnabled(enabled)

    def eventFilter(self, obj, event) -> bool:
        if (
            self._chrome_hidden
            and self._event_from_this_window(obj)
            and not self._is_pinned_chrome(obj)
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._set_chrome_hidden(False)
            return True
        return super().eventFilter(obj, event)

    def _is_pinned_chrome(self, obj) -> bool:
        widget = obj if isinstance(obj, QWidget) else None
        while widget is not None:
            if widget is self._header or widget is self._player_bar:
                return True
            widget = widget.parentWidget()
        return self._resize_grips.owns(obj if isinstance(obj, QWidget) else None)

    def _sync_now_playing_visibility(self) -> None:
        if self._chrome_hidden:
            self._now_playing.hide()
            return
        wide = self.width() >= 1100
        show = self._ui_prefs.show_now_playing_panel and wide
        self._now_playing.setVisible(show)

    def _on_page_changed(self, page_id: int) -> None:
        if page_id < 0 or page_id >= self._stack.count():
            return
        if page_id == self.PAGE_PLAYLIST:
            return
        if page_id == self._current_page:
            return
        self._apply_page(page_id)

    def _replace_stack_page(self, index: int, widget: QWidget) -> None:
        old = self._stack.widget(index)
        self._stack.removeWidget(old)
        self._stack.insertWidget(index, widget)
        if old is not None:
            old.deleteLater()

    def _ensure_search_page(self) -> SearchPage:
        """Ленивая инициализация страницы поиска (index 1)."""
        if self._search_page is None:
            self._search_page = SearchPage(
                self._search_vm,
                self._bridge,
                on_playlists_changed=lambda: self._bridge.schedule(
                    self._home_vm.refresh_user_playlists(self._bridge)
                ),
            )
            self._replace_stack_page(self.PAGE_SEARCH, self._search_page)
        return self._search_page

    def _ensure_library_page(self):
        """Ленивая инициализация библиотеки (index 2)."""
        if self._library_page is None:
            from quantis.ui.views.library_page import LibraryPage

            self._library_page = LibraryPage(self._home_vm, self._bridge)
            self._replace_stack_page(self.PAGE_LIBRARY, self._library_page)
        return self._library_page

    def _ensure_stats_page(self) -> StatsPage:
        if self._stats_page is None:
            self._stats_page = StatsPage(self._stats_vm, self._bridge)
            self._stats_page.set_accent(self._accent)
            self._replace_stack_page(self.PAGE_STATS, self._stats_page)
        return self._stats_page

    def _ensure_plugins_page(self) -> PluginsPage:
        if self._plugins_page is None:
            self._plugins_page = PluginsPage(self._bridge)
            self._replace_stack_page(self.PAGE_PLUGINS, self._plugins_page)
        return self._plugins_page

    def _ensure_member_page(self) -> MemberPage:
        if self._member_page is None:
            self._member_page = MemberPage(self._bridge)
            self._replace_stack_page(self.PAGE_MEMBER, self._member_page)
        return self._member_page

    def _ensure_settings_page(self) -> SettingsPage:
        if self._settings_page is None:
            self._settings_page = SettingsPage(self._ui_prefs, self._bridge)
            self._settings_page.update_checked.connect(self._sync_update_banner)
            self._replace_stack_page(self.PAGE_SETTINGS, self._settings_page)
        return self._settings_page

    def _ensure_playlist_page(self) -> PlaylistPage:
        """Ленивая инициализация детальной страницы плейлиста (index 7, вне nav)."""
        if self._playlist_page is None:
            self._playlist_page = PlaylistPage(self._playlist_vm, self._bridge)
            self._playlist_page.back_requested.connect(self._close_playlist_page)
            self._replace_stack_page(self.PAGE_PLAYLIST, self._playlist_page)
        return self._playlist_page

    def _sync_plugin_pages(self) -> None:
        """Монтирует страницы плагинов в стек и пункты навбара."""
        host = self._extensions
        pages = host.pages()

        active_plugin_id = next(
            (
                pid
                for pid, idx in self._plugin_page_ids.items()
                if idx == self._current_page
            ),
            None,
        )

        while self._stack.count() > self._CORE_STACK_COUNT:
            last = self._stack.count() - 1
            widget = self._stack.widget(last)
            self._stack.removeWidget(widget)
            if widget is not None:
                widget.setParent(None)

        for page_id in list(self._plugin_page_ids):
            host.unregister_nav_item(page_id)
            self._page_meta.pop(self._plugin_page_ids[page_id], None)
        self._plugin_page_ids.clear()

        for offset, page in enumerate(pages):
            index = self._CORE_STACK_COUNT + offset
            widget = page.widget
            widget.setWindowFlags(Qt.WindowType.Widget)
            widget.setParent(None)
            widget.hide()
            self._stack.addWidget(widget)
            page.stack_index = index
            self._plugin_page_ids[page.page_id] = index
            self._page_meta[index] = (page.title, page.subtitle or "")
            host.register_nav_item(
                NavExtension(
                    item_id=page.page_id,
                    tooltip=page.title,
                    icon=page.icon,
                    page_id=index,
                    from_plugin=True,
                )
            )

        if active_plugin_id and active_plugin_id in self._plugin_page_ids:
            restored = self._plugin_page_ids[active_plugin_id]
            self._current_page = -1
            self._apply_page(restored)
        elif (
            self._current_page >= self._CORE_STACK_COUNT
            and self._current_page >= self._stack.count()
        ):
            self._current_page = -1
            self._apply_page(self.PAGE_HOME)

    def _sync_background_layers(self) -> None:
        """Монтирует фоновые слои плагинов между обоями и интерфейсом."""
        layers = {
            layer.layer_id: layer.widget
            for layer in self._extensions.background_layers()
        }

        for layer_id, mounted in list(self._mounted_layers.items()):
            if layers.get(layer_id) is mounted:
                continue
            self._mounted_layers.pop(layer_id)
            self._body_shell.remove_background_layer(mounted)

        for layer_id, widget in layers.items():
            if layer_id in self._mounted_layers:
                continue
            self._body_shell.add_background_layer(widget)
            self._mounted_layers[layer_id] = widget
            setter = getattr(widget, "set_eco", None)
            if callable(setter):
                setter(self._eco.active)

    def _apply_page(self, page_id: int) -> None:
        if page_id < 0 or page_id >= self._stack.count():
            return
        if page_id == self.PAGE_PLAYLIST:
            return
        if page_id == self._current_page:
            return
        if page_id == self.PAGE_SEARCH:
            self._ensure_search_page()
        elif page_id == self.PAGE_LIBRARY:
            self._ensure_library_page()
        elif page_id == self.PAGE_STATS:
            self._ensure_stats_page()
            self._stats_vm.request_load(self._bridge)
        elif page_id == self.PAGE_PLUGINS:
            self._ensure_plugins_page()
        elif page_id == self.PAGE_MEMBER:
            self._ensure_member_page()
        elif page_id == self.PAGE_SETTINGS:
            self._ensure_settings_page()
        previous = self._current_page
        self._current_page = page_id
        self._stack.setCurrentIndex(page_id)
        self._nav.set_active_page(page_id)
        self._fade_current_page()
        title, subtitle = self._page_meta.get(page_id, ("Quantis", ""))
        self._header.set_page(title, subtitle)
        if previous == self.PAGE_SEARCH and page_id != self.PAGE_SEARCH:
            self._search_vm.clear_results()
        # Home уже подгружается после первого кадра; Library — при открытии.
        if page_id == self.PAGE_LIBRARY:
            self._home_vm.request_load(self._bridge)

    def _fade_current_page(self) -> None:
        page = self._stack.currentWidget()
        if page is None:
            return
        effect = page.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        page._quantis_fade = anim  # type: ignore[attr-defined]

    def _open_playlist_page(self, playlist) -> None:
        page = self._ensure_playlist_page()
        self._return_page_id = self._current_page
        self._playlist_vm.set_playlist(playlist)
        self._stack.setCurrentIndex(self.PAGE_PLAYLIST)
        count = len(playlist)
        self._header.set_page(playlist.name, f"{count} треков")
        _ = page

    def _close_playlist_page(self) -> None:
        if self._return_page_id == self.PAGE_PLAYLIST:
            self._return_page_id = self.PAGE_HOME
        page_id = self._return_page_id
        self._current_page = -1
        self._playlist_vm.clear()
        self._apply_page(page_id)

    def _sync_playing_track(self, track) -> None:
        self._search_vm.model.set_playing_track(track)
        self._home_vm.recent_model.set_playing_track(track)
        self._home_vm.recommendation_model.set_playing_track(track)
        if self._library_page is not None:
            self._library_page.set_playing_track(track)
        if self._stats_page is not None:
            self._stats_page.set_playing_track(track)
        if self._playlist_page is not None:
            self._playlist_page.set_playing_track(track)
        self._home_page.refresh_featured()
        self._now_playing.set_track(track)
        self._np_fullscreen.set_track(track)
        self._update_palette_from_track(track)

    def _open_now_playing_fullscreen(self) -> None:
        track = self._bundle.playback.current_track
        self._np_fullscreen.setGeometry(self._shell.rect())
        self._np_fullscreen.show()
        self._np_fullscreen.raise_()
        self._np_fullscreen.set_track(track)
        self._np_fullscreen.update()
        self._np_fullscreen.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _update_palette_from_track(self, track) -> None:
        if self._eco.active:
            return
        path = Path(self._bundle.music.provider.get_cover_path(track))
        cover = load_cover_image(path if path.is_file() else None)
        self._cover_palette = palette_from_image(cover)
        self._shell.compositor.set_cover(cover)
        self.apply_palette(
            self._cover_palette or fallback_palette(registry.get(self._applied_theme))
        )

    def apply_palette(self, palette: CoverPalette, *, animate: bool = True) -> None:
        """Палитра трека. Виджеты со stylesheet получают итоговый акцент сразу и
        один раз; рисующие себя сами (фон, меню) — кадры перехода от LivePalette."""
        color = palette.accent
        self._accent = QColor(color)
        if self._stats_page is not None:
            self._stats_page.set_accent(color)
        AccentStyles.instance().set_accent(color)
        LivePalette.instance().set_target(
            palette, animate=animate and not self._eco.active
        )

    def _on_live_palette(self, palette: CoverPalette) -> None:
        self._shell.set_palette(palette)
        self._nav.set_accent(palette.accent)

    def apply_accent(self, color: QColor) -> None:
        """Акцент одним цветом, без перехода (палитра достраивается из него)."""
        if color.isValid():
            self.apply_palette(palette_from_accent(color), animate=False)

    def _on_history_updated(self) -> None:
        if self._eco.active:
            return
        from quantis.ui.async_ui import schedule

        schedule(self._home_vm.refresh_recent(self._bridge), self._bridge)
        if self._current_page == self.PAGE_STATS or self._stats_page is not None:
            self._stats_vm.request_load(self._bridge)

    def _on_playlists_updated(self) -> None:
        from quantis.ui.async_ui import schedule

        schedule(self._home_vm.refresh_user_playlists(self._bridge), self._bridge)
        if self._playlist_page is not None and self._playlist_vm.playlist is not None:
            pl = self._playlist_vm.playlist
            from quantis.models import UserPlaylist

            if isinstance(pl, UserPlaylist):
                schedule(self._reload_open_user_playlist(pl.name), self._bridge)

    def _on_queue_extended(self, playlist) -> None:
        self._home_vm.apply_queue_extended(playlist)
        if self._playlist_page is not None and self._playlist_vm.playlist is playlist:
            self._playlist_vm.sync_appended()
            self._header.set_page(playlist.name, f"{len(playlist)} треков")

    def _on_playlist_tracks_mutated(self) -> None:
        playlist = self._playlist_vm.playlist
        if playlist is not None:
            self._header.set_page(playlist.name, f"{len(playlist)} треков")
        from quantis.models import DownloadPlaylist, UserPlaylist
        from quantis.ui.async_ui import schedule

        if isinstance(playlist, DownloadPlaylist):
            self._home_vm.refresh_downloaded(self._bridge)
        elif isinstance(playlist, UserPlaylist):
            schedule(self._home_vm.refresh_user_playlists(self._bridge), self._bridge)

    async def _reload_open_user_playlist(self, name: str) -> None:
        from quantis.services.user_playlists import UserPlaylistsService

        playlists = await UserPlaylistsService().load_all(include_empty=True)
        match = next((p for p in playlists if p.name == name), None)
        if match is not None:
            self._playlist_vm.set_playlist(match)
            self._header.set_page(match.name, f"{len(match)} треков")

    def _on_eco_pref_changed(self) -> None:
        self._eco.set_pref_enabled(self._ui_prefs.background_eco_enabled)

    def _on_theme_changed(self) -> None:
        theme = self._ui_prefs.ui_theme
        if theme != self._applied_theme:
            self._apply_ui_theme(theme)

    def _on_wallpaper_changed(self) -> None:
        self._apply_backdrop_look()
        source = (resources.wallpaper_path(), self._ui_prefs.dynamic_wallpaper_enabled)
        if source == self._wallpaper_source:
            return  # двигают ползунки затемнения/размытия — видео не трогаем
        self._wallpaper_source = source
        self._apply_wallpaper()
        if self._ui_prefs.dynamic_wallpaper_enabled and not self._eco.active:
            self._dynamic_wallpaper.refresh_for_track(
                self._bundle.playback.current_track
            )

    def _apply_backdrop_look(self) -> None:
        compositor = self._shell.compositor
        compositor.set_mode(self._ui_prefs.backdrop_mode)
        compositor.set_motion(self._ui_prefs.backdrop_motion)
        compositor.set_look(self._ui_prefs.backdrop_dim, self._ui_prefs.backdrop_blur)

    def _apply_wallpaper(self) -> None:
        path = resources.wallpaper_path()
        self._body_shell.set_wallpaper(path or None)

    def _apply_ui_theme(self, theme_id: str) -> None:
        self._applied_theme = theme_id
        theme = registry.get(theme_id)
        QApplication.setFont(theme_font(theme, "ui", 10))
        if self._cover_palette is None:
            self.apply_palette(fallback_palette(theme), animate=False)
        self.setStyleSheet(resources.load_stylesheet(theme_id, accent=self._accent))
        self._shell.set_theme(theme)
        self._body_shell.set_theme(theme)
        self._player_bar.refresh_theme()

    def _restore_window_geometry(self) -> None:
        saved = self._ui_prefs.window_geometry
        if saved is not None and self.restoreGeometry(saved):
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1280, 800)
            return
        available = screen.availableGeometry()
        minimum = self.minimumSize()
        frame = QRect(
            0,
            0,
            max(minimum.width(), min(1280, available.width() - 80)),
            max(minimum.height(), min(800, available.height() - 80)),
        )
        frame.moveCenter(available.center())
        self.setGeometry(frame)

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if not (self.isMaximized() or self.isMinimized() or self.isFullScreen()):
            self._ui_prefs.set_window_geometry(self.saveGeometry())
        super().closeEvent(event)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._header.set_maximized(self.isMaximized())
            self._resize_grips.update_geometry()
            self._refresh_eco_state()
        elif event.type() == QEvent.Type.ActivationChange:
            self._refresh_eco_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_grips.update_geometry()
        self._sync_now_playing_visibility()
        if self._np_fullscreen.isVisible():
            self._np_fullscreen.setGeometry(self._shell.rect())

    def _show_error(self, message: str) -> None:
        import logging

        logging.getLogger(__name__).warning("Quantis: %s", message)

    def _maybe_check_for_update(self) -> None:
        import time

        from quantis.services.app_update import should_auto_check

        self._sync_update_banner()
        if not should_auto_check(
            last_check_at=self._ui_prefs.update_last_check_at,
            now=time.time(),
            enabled=self._ui_prefs.update_check_on_startup,
        ):
            return
        self._bridge.schedule(self._run_update_check())

    async def _run_update_check(self) -> None:
        import logging

        from quantis.services.app_update import fetch_latest_release

        try:
            info = await fetch_latest_release()
        except Exception as exc:
            logging.getLogger(__name__).warning("Проверка обновлений: %s", exc)
            return
        self._bridge.invoke_main(lambda i=info: self._on_update_check_ok(i))

    def _on_update_check_ok(self, info) -> None:
        import time

        if info is not None:
            self._ui_prefs.set_update_last_tag(info.tag)
            self._ui_prefs.set_update_last_html_url(info.html_url)
        self._ui_prefs.set_update_last_check_at(time.time())
        self._sync_update_banner()
        if self._settings_page is not None:
            self._settings_page.apply_update_from_prefs()

    def _sync_update_banner(self) -> None:
        from quantis.services.app_update import (
            app_version,
            display_version,
            should_announce,
        )

        tag = self._ui_prefs.update_last_tag
        if should_announce(app_version(), tag, self._ui_prefs.update_dismissed_tag):
            self._update_banner.show_version(display_version(tag))
        else:
            self._update_banner.hide()

    def _open_cached_release(self) -> None:
        from quantis.services.app_update import is_safe_release_url

        url = self._ui_prefs.update_last_html_url
        if url and is_safe_release_url(url):
            QDesktopServices.openUrl(QUrl(url))

    def _dismiss_update_banner(self) -> None:
        tag = self._ui_prefs.update_last_tag
        if tag:
            self._ui_prefs.set_update_dismissed_tag(tag)
        self._update_banner.hide()


Quantis = QuantisMainWindow
