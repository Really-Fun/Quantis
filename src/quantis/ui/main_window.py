from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    QUrl,
)
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
from quantis.services.lyrics import LyricsService
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
from quantis.ui.cover_prefetch import schedule_cover_prefetch
from quantis.ui.fonts import register_bundled_fonts, theme_font
from quantis.ui.live_palette import LivePalette
from quantis.ui.playlist_actions import bind_event_bus as bind_playlist_event_bus
from quantis.ui.preferences import UiPreferences
from quantis.ui.shortcuts import (
    ALT_PAGE_IDS,
    VOLUME_STEP,
    is_arrow_navigation_target,
    is_space_target,
    is_typing_target,
)
from quantis.ui.themes import registry
from quantis.ui.themes.spec import qcolor
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
from quantis.ui.views.wave_page import WavePage
from quantis.ui.views.widgets.app_header import AppHeader
from quantis.ui.views.widgets.backdrop_panel import (
    BackdropPanel,
    apply_backdrop_file,
    backdrop_kind,
)
from quantis.ui.views.widgets.background_frame import BackgroundFrame
from quantis.ui.views.widgets.cover_art import CoverEvents, is_track_cover
from quantis.ui.views.widgets.notifications import (
    DownloadNotification,
    Notification,
    NotificationCenter,
)
from quantis.ui.views.widgets.now_playing_fullscreen import NowPlayingFullscreen
from quantis.ui.views.widgets.now_playing_stage import upcoming
from quantis.ui.views.widgets.resize_grips import WindowResizeGrips
from quantis.ui.views.widgets.side_nav import SideNavRail
from quantis.ui.views.widgets.side_panel import SidePanel
from quantis.ui.views.widgets.update_banner import UpdateBanner
from quantis.ui.views.widgets.wallpaper_backdrop import BodyWithWallpaper


class QuantisMainWindow(QMainWindow):
    """Главное окно приложения.

    Страницы в QStackedWidget (индексы):
      0 Home, 1 Search, 2 Library, 3 Stats, 4 Plugins, 5 Member, 6 Settings,
      7 Playlist (overlay, не в боковом nav), 8 Моя волна, 9+ — страницы плагинов.

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
    PAGE_WAVE = 8
    _CORE_STACK_COUNT = 9

    _PAGE_META = {
        PAGE_HOME: ("Главная", ""),
        PAGE_SEARCH: ("Поиск", ""),
        PAGE_LIBRARY: ("Библиотека", ""),
        PAGE_STATS: ("Статистика", ""),
        PAGE_PLUGINS: ("Плагины", ""),
        PAGE_MEMBER: ("Аккаунты", ""),
        PAGE_SETTINGS: ("Настройки", ""),
        PAGE_WAVE: ("Моя волна", ""),
    }

    def __init__(self, bundle: ApplicationBundle, parent=None) -> None:
        super().__init__(parent)

        register_bundled_fonts()

        self._bundle = bundle
        self._bridge = bundle.async_bridge
        self.setWindowTitle("Quantis")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self._fit_minimum_to_screen()
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
        # Трек сменился в эко — фон и палитра догонят его при выходе из эко.
        self._palette_stale = False

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
        self._header.nav_toggle_requested.connect(self._toggle_nav)
        self._header.search_edited.connect(self._on_header_search_edited)
        self._header.search_submitted.connect(self._on_header_search_submitted)
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
        self._nav.set_expanded(self._ui_prefs.nav_expanded, animate=False)
        self._nav.playlist_activated.connect(
            lambda pl: self._open_playlist_page(self._home_vm.resolve_playlist(pl))
        )
        self._home_vm.home_changed.connect(
            lambda: self._nav.set_playlists(self._home_vm.snapshot.quick_playlists)
        )
        self._header.set_nav_expanded(self._ui_prefs.nav_expanded)
        self._header.set_maximized(
            self.isMaximized()
        )  # окно могло открыться развёрнутым

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
        self._wave_page: WavePage | None = None

        self._stack.addWidget(self._home_page)  # 0
        self._stack.addWidget(QWidget())  # 1 SEARCH
        self._stack.addWidget(QWidget())  # 2 LIBRARY (lazy)
        self._stack.addWidget(QWidget())  # 3 STATS
        self._stack.addWidget(QWidget())  # 4 PLUGINS
        self._stack.addWidget(QWidget())  # 5 MEMBER
        self._stack.addWidget(QWidget())  # 6 SETTINGS
        self._stack.addWidget(QWidget())  # 7 PLAYLIST
        self._stack.addWidget(QWidget())  # 8 WAVE

        self._home_page.playlist_open_requested.connect(self._open_playlist_page)
        self._home_page.search_requested.connect(
            lambda: self._goto_page(self.PAGE_SEARCH)
        )
        self._home_page.wave_page_requested.connect(
            lambda: self._goto_page(self.PAGE_WAVE)
        )
        self._home_page.queue_requested.connect(self._open_playing_queue)
        self._home_page.up_next_activated.connect(self._play_up_next)
        self._player_vm.is_playing_changed.connect(self._home_page.set_playing)

        content.addWidget(self._stack, stretch=1)

        self._side_panel = SidePanel(bundle.music.provider)
        self._side_panel.close_requested.connect(
            lambda: self._ui_prefs.set_side_panel("")
        )
        self._side_panel.track_activated.connect(self._play_up_next)
        self._side_panel.queue_page_requested.connect(self._open_playing_queue)
        self._side_panel.tab_requested.connect(self._ui_prefs.set_side_panel)
        self._side_panel.seek_requested.connect(self._player_vm.seek)
        self._player_vm.position_changed.connect(self._side_panel.lyrics.set_position)
        self._lyrics_service = LyricsService()
        self._lyrics_track = None
        """Трек, чей текст сейчас в панели (или грузится)."""

        self._np_fullscreen = NowPlayingFullscreen(bundle.music.provider, parent=shell)
        self._np_fullscreen.closed.connect(self._np_fullscreen.hide)
        self._np_fullscreen.hide()

        self._backdrop_panel = BackdropPanel(
            shell.compositor, self._ui_prefs, parent=shell
        )
        self._header.backdrop_requested.connect(
            lambda: self._backdrop_panel.toggle(self._header.backdrop_button)
        )
        self.setAcceptDrops(True)  # картинка или видео в окно — фоном

        mid = QWidget()
        mid_layout = QHBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(10)
        mid_layout.addWidget(self._nav)
        mid_layout.addWidget(content_host, stretch=1)
        mid_layout.addWidget(self._side_panel)

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
        )
        self._player_bar.queue_toggle_requested.connect(
            lambda: self._toggle_side_panel("queue")
        )
        self._player_bar.lyrics_toggle_requested.connect(
            lambda: self._toggle_side_panel("lyrics")
        )
        self._player_bar.hide_ui_requested.connect(self._toggle_chrome_hidden)
        columns.addWidget(self._player_bar)

        body.addWidget(columns_host, stretch=1)
        root.addWidget(self._body_shell, stretch=1)

        self._notifications = NotificationCenter(self._shell, self._notifications_top)
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
        bind_playlist_event_bus(bundle.event_bus)
        bundle.event_bus.queue_extended.connect(self._on_queue_extended)
        bundle.event_bus.error_occurred.connect(self._show_error)
        bundle.event_bus.notification_requested.connect(self._show_notification)
        bundle.event_bus.accounts_requested.connect(
            lambda: self._goto_page(self.PAGE_MEMBER)
        )
        self._download_toasts: dict[tuple[str, str], DownloadNotification] = {}
        bundle.event_bus.track_download_started.connect(self._on_download_started)
        bundle.event_bus.track_download_progress.connect(self._on_download_progress)
        bundle.event_bus.track_downloaded.connect(self._on_track_downloaded)
        self._search_vm.download_finished.connect(
            lambda: self._home_vm.refresh_downloaded(self._bridge)
        )
        from quantis.providers.library_index import LibraryIndex

        # Индекс меняется на каждом скачанном, удалённом или переименованном
        # файле («Записать теги» — сотни подряд): обновляем «Скачанные» один
        # раз после серии изменений.
        self._downloaded_refresh_timer = QTimer(self)
        self._downloaded_refresh_timer.setSingleShot(True)
        self._downloaded_refresh_timer.setInterval(300)
        self._downloaded_refresh_timer.timeout.connect(self._on_library_changed)
        # Слушатель зовётся из рабочего потока — в UI переходим через мост.
        LibraryIndex.instance().add_listener(
            lambda: self._bridge.invoke_main(self._downloaded_refresh_timer.start)
        )
        self._playlist_vm.tracks_mutated.connect(self._on_playlist_tracks_mutated)
        self._ui_prefs.theme_changed.connect(self._on_theme_changed)
        self._ui_prefs.wallpaper_changed.connect(self._on_wallpaper_changed)
        self._wallpaper_source = self._backdrop_source()
        self._apply_backdrop_look()
        self._apply_file_loop()
        self._ui_prefs.layout_changed.connect(self._sync_side_panel)
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
        CoverEvents.instance().cover_ready.connect(self._on_cover_ready)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_app_state_changed)
            app.focusChanged.connect(self._sync_shortcut_enabled)
        self._install_shortcuts()
        self._refresh_eco_state()
        self._apply_ui_theme(self._ui_prefs.ui_theme)
        self._sync_side_panel(animate=False)
        self._mounted_layers: dict[str, QWidget] = {}
        self._extensions = UiExtensionHost.instance()
        self._extensions.pages_changed.connect(self._sync_plugin_pages)
        self._extensions.background_layers_changed.connect(self._sync_background_layers)
        self._sync_plugin_pages()
        self._sync_background_layers()
        self._on_page_changed(self.PAGE_HOME)
        # Данные главной — после первого кадра, чтобы не тормозить show().

        QTimer.singleShot(0, lambda: self._home_vm.request_load(self._bridge))
        QTimer.singleShot(0, self._maybe_check_for_update)
        # Первый заход на страницу — создание и полировка стилей (20–40 мс,
        # заметный рывок). Создаём их заранее, по одной, пока окно простаивает.
        self._prewarm_queue = [
            self._ensure_search_page,
            self._ensure_library_page,
            self._ensure_stats_page,
            self._ensure_settings_page,
        ]
        QTimer.singleShot(3000, self._prewarm_next_page)

    def _prewarm_next_page(self) -> None:
        if not self._prewarm_queue:
            return
        self._prewarm_queue.pop(0)()
        if self._prewarm_queue:
            QTimer.singleShot(400, self._prewarm_next_page)

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
        self._home_page.set_eco(active)
        if self._wave_page is not None:
            self._wave_page.set_eco(active)
        self._player_vm.set_eco(active)
        self._bundle.history_watcher.set_eco(active)
        self._bundle.music.streamer.set_eco(active)
        self._dynamic_wallpaper.set_eco(active)
        self._body_shell.backdrop.set_file_loop_paused(active)
        if not active and self._palette_stale:
            self._update_palette_from_track(self._bundle.playback.current_track)
        for widget in getattr(self, "_mounted_layers", {}).values():
            setter = getattr(widget, "set_eco", None)
            if callable(setter):
                setter(active)

    def _toggle_side_panel(self, tab: str) -> None:
        """Кнопка в плеере: та же вкладка открыта — закрыть, иначе открыть её."""
        self._ui_prefs.set_side_panel("" if self._ui_prefs.side_panel == tab else tab)

    def _toggle_nav(self) -> None:
        expanded = not self._nav.is_expanded
        self._nav.set_expanded(expanded)
        self._header.set_nav_expanded(expanded)
        self._ui_prefs.set_nav_expanded(expanded)

    def _on_header_search_edited(self, text: str) -> None:
        page = self._ensure_search_page()
        if self._stack.currentIndex() != self.PAGE_SEARCH:
            self._goto_page(self.PAGE_SEARCH)
        page.set_query(text)

    def _on_header_search_submitted(self, text: str) -> None:
        page = self._ensure_search_page()
        if self._stack.currentIndex() != self.PAGE_SEARCH:
            self._goto_page(self.PAGE_SEARCH)
        page.set_query(text, submit=True)

    def _focus_search(self) -> None:
        if self._chrome_hidden:
            self._set_chrome_hidden(False)
        self._header.focus_search()

    def _toggle_chrome_hidden(self) -> None:
        self._set_chrome_hidden(not self._chrome_hidden)

    def _set_chrome_hidden(self, hidden: bool) -> None:
        if self._chrome_hidden == hidden:
            return
        self._chrome_hidden = hidden
        # Клик «вернуть интерфейс» ловится фильтром на всём приложении — ставим
        # его только на время режима: иначе через Python идёт каждое событие.
        app = QApplication.instance()
        if app is not None:
            if hidden:
                app.installEventFilter(self)
            else:
                app.removeEventFilter(self)
        self._nav.setVisible(not hidden)
        self._content_host.setVisible(not hidden)
        if hidden:
            self._update_banner.hide()
            self._side_panel.set_open(False, animate=False)
            if self._np_fullscreen.isVisible():
                self._np_fullscreen.hide()
            self._body_shell.layout_host.setContentsMargins(0, 0, 0, 0)
        else:
            self._body_shell.layout_host.setContentsMargins(10, 10, 10, 0)
            self._sync_update_banner()
            self._sync_side_panel(animate=False)
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
        self._make_shortcut("Ctrl+K", self._focus_search)
        self._make_shortcut("Ctrl+F", self._focus_search)
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

    def _sync_side_panel(self, *_: object, animate: bool = True) -> None:
        tab = self._ui_prefs.side_panel
        open_ = bool(tab) and not self._chrome_hidden
        if tab:
            self._side_panel.set_tab(tab)
        self._side_panel.set_open(open_, animate=animate)
        self._player_bar.set_side_panel(tab if open_ else "")
        self._home_page.set_queue_elsewhere(open_ and tab == "queue")
        if open_ and tab == "lyrics":
            self._load_lyrics(self._bundle.playback.current_track)

    def _load_lyrics(self, track) -> None:
        """Текст грузим, только когда вкладка «Текст» открыта (и один раз на трек)."""
        view = self._side_panel.lyrics
        if track is None:
            self._lyrics_track = None
            view.set_empty()
            return
        if track == self._lyrics_track:
            return
        self._lyrics_track = track
        view.set_loading()

        async def run() -> None:
            lyrics = await self._lyrics_service.fetch(track)

            def apply() -> None:
                if track == self._lyrics_track:  # пока искали, трек сменили
                    view.set_lyrics(lyrics)

            self._bridge.invoke_main(apply)

        self._bridge.schedule(run())

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
            )
            self._replace_stack_page(self.PAGE_SEARCH, self._search_page)
        return self._search_page

    def _ensure_library_page(self):
        """Ленивая инициализация библиотеки (index 2)."""
        if self._library_page is None:
            from quantis.ui.views.library_page import LibraryPage

            self._library_page = LibraryPage(self._home_vm, self._bridge)
            self._library_page.search_requested.connect(self._focus_search)
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
            self._settings_page = SettingsPage(
                self._ui_prefs, self._bridge, music=self._bundle.music
            )
            self._settings_page.update_checked.connect(self._sync_update_banner)
            self._replace_stack_page(self.PAGE_SETTINGS, self._settings_page)
        return self._settings_page

    def _ensure_wave_page(self) -> WavePage:
        if self._wave_page is None:
            self._wave_page = WavePage(self._home_vm, self._bridge)
            self._wave_page.toggle_pause_requested.connect(self._player_vm.toggle_pause)
            self._player_vm.is_playing_changed.connect(self._wave_page.set_playing)
            self._player_vm.track_changed.connect(
                lambda _track: self._wave_page.set_playing(
                    self._bundle.player.is_playing()
                )
            )
            self._wave_page.set_eco(self._eco.active)
            self._replace_stack_page(self.PAGE_WAVE, self._wave_page)
        return self._wave_page

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
        elif page_id == self.PAGE_WAVE:
            self._ensure_wave_page()
        previous = self._current_page
        self._current_page = page_id
        self._stack.setCurrentIndex(page_id)
        self._nav.set_active_page(page_id)
        self._fade_current_page()
        title, subtitle = self._page_meta.get(page_id, ("Quantis", ""))
        self._header.set_page(title, subtitle)
        if previous == self.PAGE_SEARCH and page_id != self.PAGE_SEARCH:
            self._search_vm.clear_results()
            self._header.clear_search()
        if page_id == self.PAGE_SEARCH and not self._header.search_field.hasFocus():
            self._header.focus_search()
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
        # Эффект рисует страницу через отдельный буфер — после появления он
        # не нужен, а висящий на странице лишь мешает частичной перерисовке.
        anim.finished.connect(
            lambda p=page, e=effect: (
                p.graphicsEffect() is e and p.setGraphicsEffect(None)
            )
        )
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
        self._home_page.set_now_playing(track)
        self._refresh_up_next()
        self._side_panel.set_track(track)
        if self._side_panel.is_open() and self._side_panel.tab() == "lyrics":
            self._load_lyrics(track)
        self._np_fullscreen.set_track(track)
        self._update_palette_from_track(track)

    def _refresh_up_next(self) -> None:
        playlist = self._bundle.playback.playlist_manager.current_playlist
        if playlist is None:
            self._home_page.set_up_next([])
            self._side_panel.set_queue([])
            return
        cycle = playlist.tracks
        current = self._bundle.playback.current_track
        index = getattr(cycle, "_index", 0)
        queue = upcoming(cycle.values, current, index, count=SidePanel.QUEUE_COUNT)
        self._home_page.set_up_next(queue[:4])
        self._side_panel.set_queue(queue)
        # Обложки очереди (волна, только что открытый плейлист) ещё не скачаны:
        # докачанные подхватят «Дальше» и очередь в панели.
        schedule_cover_prefetch(
            [item.track for item in queue],
            self._bundle.music.downloader,
            self._bridge,
            limit=len(queue),
        )

    def _play_up_next(self, index: int) -> None:
        playlist = self._bundle.playback.playlist_manager.current_playlist
        if playlist is None:
            return
        from quantis.ui.async_ui import schedule

        schedule(self._home_vm.play_playlist(playlist, index), self._bridge)

    def _open_playing_queue(self) -> None:
        playlist = self._bundle.playback.playlist_manager.current_playlist
        if playlist is not None and len(playlist):
            self._open_playlist_page(playlist)

    def _open_now_playing_fullscreen(self) -> None:
        track = self._bundle.playback.current_track
        self._np_fullscreen.setGeometry(self._shell.rect())
        self._np_fullscreen.show()
        self._np_fullscreen.raise_()
        self._np_fullscreen.set_track(track)
        self._np_fullscreen.update()
        self._np_fullscreen.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _on_cover_ready(self, path: str) -> None:
        """Обложка играющего трека докачалась: фон, палитра, панели."""
        track = self._bundle.playback.current_track
        if track is None or not is_track_cover(track, path):
            return
        self._side_panel.set_track(track)
        if self._np_fullscreen.isVisible():
            self._np_fullscreen.set_track(track)
        self._update_palette_from_track(track)

    def _update_palette_from_track(self, track) -> None:
        if self._eco.active:
            self._palette_stale = True
            return
        self._palette_stale = False
        if track is None:
            return
        path = Path(self._bundle.music.provider.get_cover_path(track))
        cover = load_cover_image(path if path.is_file() else None)
        self._cover_palette = palette_from_image(cover)
        self._shell.compositor.set_cover(cover)
        self.apply_palette(self._palette_for(registry.get(self._applied_theme)))

    def _palette_for(self, theme) -> CoverPalette:  # type: ignore[no-untyped-def]
        """Цвет обложки, если тема его берёт; иначе — свой акцент темы."""
        if theme.fixed_accent or self._cover_palette is None:
            return fallback_palette(theme)
        return self._cover_palette

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
        if not LivePalette.instance().is_animating():
            self._nav.set_accent(palette.accent)  # значки перекрашиваем один раз

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
        self._refresh_up_next()
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

    def _on_library_changed(self) -> None:
        from quantis.models import DownloadPlaylist
        from quantis.ui.async_ui import schedule

        self._home_vm.refresh_downloaded(self._bridge)
        if self._playlist_page is not None and isinstance(
            self._playlist_vm.playlist, DownloadPlaylist
        ):
            schedule(self._reload_open_downloaded_playlist(), self._bridge)

    async def _reload_open_downloaded_playlist(self) -> None:
        from quantis.models import DownloadPlaylist

        tracks = await asyncio.to_thread(DownloadPlaylist.get_tracks_from_music_dir)

        def apply() -> None:
            # Пока читали индекс, пользователь мог уйти со страницы.
            if self._playlist_page is None or not isinstance(
                self._playlist_vm.playlist, DownloadPlaylist
            ):
                return
            playlist = DownloadPlaylist(tracks=tracks)
            self._playlist_vm.set_playlist(playlist)
            self._header.set_page(playlist.name, f"{len(playlist)} треков")

        self._bridge.invoke_main(apply)

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
        source = self._backdrop_source()
        if source == self._wallpaper_source:
            return  # двигают ползунки затемнения/размытия — видео не трогаем
        self._wallpaper_source = source
        self._apply_wallpaper()
        self._apply_file_loop()
        if self._ui_prefs.dynamic_wallpaper_enabled and not self._eco.active:
            self._dynamic_wallpaper.refresh_for_track(
                self._bundle.playback.current_track
            )

    def _backdrop_source(self) -> tuple[object, ...]:
        """Откуда берётся фон; поменялось — перезапускаем картинку/видео."""
        prefs = self._ui_prefs
        own_video = prefs.backdrop_video_file if prefs.backdrop_video_is_file else ""
        return (resources.wallpaper_path(), prefs.dynamic_wallpaper_enabled, own_video)

    def _apply_file_loop(self) -> None:
        """Свой видеофайл фоном (режим «Клип» без клипов треков)."""
        backdrop = self._body_shell.backdrop
        prefs = self._ui_prefs
        if prefs.backdrop_video_is_file and Path(prefs.backdrop_video_file).is_file():
            backdrop.play_file_loop(prefs.backdrop_video_file)
            backdrop.set_file_loop_paused(self._eco.active)
        else:
            backdrop.stop_file_loop()

    def _dropped_path(self, event) -> str | None:
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            return None
        for url in mime.urls():
            path = url.toLocalFile()
            if path and backdrop_kind(path) is not None:
                return path
        return None

    def dragEnterEvent(self, event) -> None:
        if self._dropped_path(event) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        path = self._dropped_path(event)
        if path is not None and apply_backdrop_file(self._ui_prefs, path):
            event.acceptProposedAction()
            return
        super().dropEvent(event)

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
        # Тема могла сменить правило акцента (своя / из обложки) — пересчитать.
        self.apply_palette(self._palette_for(theme), animate=False)
        self.setStyleSheet(resources.load_stylesheet(theme_id, accent=self._accent))
        self._shell.set_theme(theme)
        self._body_shell.set_theme(theme)
        self._player_bar.refresh_theme()
        self._nav.set_text_color(qcolor(theme.colors.text_dim))

    MIN_SIZE = QSize(1024, 640)

    def _fit_minimum_to_screen(self) -> None:
        """Минимум окна не больше экрана: 1366×768 при 150 % на Windows —
        это ~910×480 логических точек, окно 1024×640 туда не влезает."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.setMinimumSize(self.MIN_SIZE)
            return
        available = screen.availableGeometry().size()
        self.setMinimumSize(self.MIN_SIZE.boundedTo(available))

    def _restore_window_geometry(self) -> None:
        saved = self._ui_prefs.window_geometry
        if saved is not None and self.restoreGeometry(saved):
            # сохранено на другом масштабе/экране — окно могло стать больше экрана
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                available = screen.availableGeometry()
                frame = self.geometry()
                if not available.contains(frame):
                    frame.setSize(frame.size().boundedTo(available.size()))
                    frame.moveTopLeft(
                        QPoint(
                            max(
                                available.left(),
                                min(
                                    frame.left(), available.right() - frame.width() + 1
                                ),
                            ),
                            max(
                                available.top(),
                                min(
                                    frame.top(), available.bottom() - frame.height() + 1
                                ),
                            ),
                        )
                    )
                    self.setGeometry(frame)
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
        # Развёрнутое окно тоже сохраняем: saveGeometry() хранит обычный размер
        # и флаг «развёрнуто», иначе окно каждый раз открывается не на весь экран.
        if not (self.isMinimized() or self.isFullScreen()):
            self._ui_prefs.set_window_geometry(self.saveGeometry())
        super().closeEvent(event)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        # restoreGeometry() в __init__ разворачивает окно до того, как созданы
        # шапка и эко-режим: состояние им отдаётся, когда они появятся.
        if not hasattr(self, "_header"):
            return
        if event.type() == QEvent.Type.WindowStateChange:
            self._header.set_maximized(self.isMaximized())
            self._resize_grips.update_geometry()
            self._refresh_eco_state()
        elif event.type() == QEvent.Type.ActivationChange:
            self._refresh_eco_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_grips.update_geometry()
        if self._np_fullscreen.isVisible():
            self._np_fullscreen.setGeometry(self._shell.rect())
        if self._backdrop_panel.isVisible():
            self._backdrop_panel.refresh()  # держится у кнопки «Фон»

    def _notifications_top(self) -> int:
        """Уведомления — сразу под шапкой (или от верха, если шапка скрыта)."""
        header = self._header
        if not header.isVisible():
            return 0
        return header.mapTo(self._shell, QPoint(0, header.height())).y() - 6

    @staticmethod
    def _download_key(track) -> tuple[str, str]:
        return str(track.source), str(track.track_id)

    def _on_download_started(self, track) -> None:
        key = self._download_key(track)
        if key in self._download_toasts:
            return
        cover = self._bundle.music.provider.get_cover_path(track)
        toast = DownloadNotification(track, cover)
        # Закрыли крестиком — итог придёт новой карточкой.
        toast.closed.connect(lambda: self._forget_download_toast(key, toast))
        self._download_toasts[key] = toast
        self._notifications.push(toast)

    def _forget_download_toast(self, key, toast) -> None:
        if self._download_toasts.get(key) is toast:
            del self._download_toasts[key]

    def _on_download_progress(self, track, fraction) -> None:
        toast = self._download_toasts.get(self._download_key(track))
        if toast is not None:
            toast.set_fraction(fraction)

    def _on_track_downloaded(self, track, ok: bool) -> None:
        cover = self._bundle.music.provider.get_cover_path(track)
        toast = self._download_toasts.pop(self._download_key(track), None)
        if toast is not None and not toast.done:
            toast.finish(ok, cover)
        else:
            self._notifications.push(DownloadNotification.finished(track, ok, cover))

    def _show_error(self, message: str) -> None:
        import logging

        logging.getLogger(__name__).warning("Quantis: %s", message)
        message = (message or "").strip()
        if not message:
            return
        # Та же ошибка уже на экране — второй карточки не нужно.
        for shown in self._notifications.notifications:
            if shown.kind == "error" and shown.message == message:
                return
        self._notifications.push(
            Notification("Ошибка", message, kind="error", timeout_ms=7000)
        )

    def _show_notification(self, title: str, message: str, kind: str) -> None:
        title = (title or "").strip()
        if not title:
            return
        # Такая же карточка уже на экране — второй не нужно.
        for shown in self._notifications.notifications:
            if shown.title == title and shown.message == message:
                return
        timeout = 7000 if kind == "error" else None
        self._notifications.push(
            Notification(title, message, kind=kind, timeout_ms=timeout)
        )

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
