from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from quantis.config.media_backend import backend_display_name, resolve_media_backend
from quantis.core.async_bridge import AsyncBridge
from quantis.services.app_update import (
    ReleaseInfo,
    app_version,
    display_version,
    fetch_latest_release,
    is_newer,
    is_safe_release_url,
)
from quantis.services.wallpaper_policy import (
    WALLPAPER_AV_DELAY_MAX_MS,
    WALLPAPER_AV_DELAY_MIN_MS,
    WALLPAPER_FPS_CHOICES,
    WALLPAPER_QUALITY_CHOICES,
)
from quantis.ui.preferences import UiPreferences
from quantis.ui.resources import UI_THEME_LABELS
from quantis.ui.shortcuts import KEYBIND_HINTS
from quantis.ui.views.widgets.glass_panel import GlassPanel
from quantis.ui.wallpapers import (
    remap_renamed_wallpaper,
    scan_wallpapers,
    user_backgrounds_dir,
    wallpaper_display_name,
)
from quantis.utils import app_paths


class SettingsPage(QWidget):
    update_checked = Signal()

    def __init__(
        self,
        preferences: UiPreferences | None = None,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._prefs = preferences or UiPreferences()
        self._bridge = bridge
        self._update_loading = False
        self._release_url = ""
        self.setObjectName("settingsPage")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 8, 16, 20)
        layout.setSpacing(12)

        panel = GlassPanel()
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(14)

        panel_layout.addWidget(QLabel("Интерфейс", objectName="settingsSectionLabel"))

        theme_row, theme_body = self._row("Тема", "Внешний вид приложения")
        self._theme_combo = QComboBox()
        self._theme_combo.setObjectName("themeCombo")
        self._theme_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for theme_id, label in UI_THEME_LABELS.items():
            self._theme_combo.addItem(label, theme_id)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_body.addWidget(self._theme_combo)
        panel_layout.addWidget(theme_row)

        featured_row, featured_body = self._row(
            "Главная",
            "Дополнительная панель текущего трека",
        )
        self._home_featured_cb = QCheckBox("Панель «Сейчас» на главной")
        self._home_featured_cb.setObjectName("settingsCheck")
        self._home_featured_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_featured_cb.toggled.connect(self._on_home_featured_toggled)
        featured_body.addWidget(self._home_featured_cb)
        panel_layout.addWidget(featured_row)

        now_row, now_body = self._row(
            "Now Playing",
            "Правая колонка с обложкой и метаданными (на широком окне)",
        )
        self._now_playing_cb = QCheckBox("Показывать панель Now Playing")
        self._now_playing_cb.setObjectName("settingsCheck")
        self._now_playing_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._now_playing_cb.toggled.connect(self._on_now_playing_toggled)
        now_body.addWidget(self._now_playing_cb)
        panel_layout.addWidget(now_row)

        static_wall_row, static_wall_body = self._row(
            "Обои",
            "По умолчанию фон без картинки — экономия ОЗУ",
        )
        self._wallpaper_enabled_cb = QCheckBox("Показывать статичные обои")
        self._wallpaper_enabled_cb.setObjectName("settingsCheck")
        self._wallpaper_enabled_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wallpaper_enabled_cb.toggled.connect(self._on_wallpaper_enabled_toggled)
        static_wall_body.addWidget(self._wallpaper_enabled_cb)

        self._wallpaper_picker = QWidget()
        picker_layout = QVBoxLayout(self._wallpaper_picker)
        picker_layout.setContentsMargins(0, 4, 0, 0)
        picker_layout.setSpacing(8)

        self._wallpaper_combo = QComboBox()
        self._wallpaper_combo.setObjectName("themeCombo")
        self._wallpaper_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._wallpaper_combo.currentIndexChanged.connect(self._on_wallpaper_changed)
        picker_layout.addWidget(self._wallpaper_combo)

        self._wallpaper_status = QLabel()
        self._wallpaper_status.setObjectName("settingsRowDesc")
        self._wallpaper_status.setWordWrap(True)
        picker_layout.addWidget(self._wallpaper_status)
        static_wall_body.addWidget(self._wallpaper_picker)
        panel_layout.addWidget(static_wall_row)

        wallpaper_row, wallpaper_body = self._row(
            "Динамические обои",
            "Видео YouTube вместо статичного фона. Качество и FPS "
            "можно снизить, если греется видеокарта.",
        )
        self._dynamic_wallpaper_cb = QCheckBox("Видео-фон при воспроизведении")
        self._dynamic_wallpaper_cb.setObjectName("settingsCheck")
        self._dynamic_wallpaper_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dynamic_wallpaper_cb.toggled.connect(self._on_dynamic_wallpaper_toggled)
        wallpaper_body.addWidget(self._dynamic_wallpaper_cb)

        self._wallpaper_video_opts = QWidget()
        video_opts = QVBoxLayout(self._wallpaper_video_opts)
        video_opts.setContentsMargins(0, 4, 0, 0)
        video_opts.setSpacing(8)

        video_opts.addWidget(QLabel("Качество", objectName="settingsRowDesc"))
        self._wallpaper_quality_combo = QComboBox()
        self._wallpaper_quality_combo.setObjectName("themeCombo")
        self._wallpaper_quality_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        quality_labels = {
            360: "360p — меньше нагрузка",
            480: "480p",
            720: "720p — чётче",
            1080: "1080p — максимум",
        }
        for height in WALLPAPER_QUALITY_CHOICES:
            self._wallpaper_quality_combo.addItem(quality_labels[height], height)
        self._wallpaper_quality_combo.currentIndexChanged.connect(
            self._on_wallpaper_quality_changed
        )
        video_opts.addWidget(self._wallpaper_quality_combo)

        video_opts.addWidget(QLabel("Кадров в секунду", objectName="settingsRowDesc"))
        self._wallpaper_fps_combo = QComboBox()
        self._wallpaper_fps_combo.setObjectName("themeCombo")
        self._wallpaper_fps_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for fps in WALLPAPER_FPS_CHOICES:
            self._wallpaper_fps_combo.addItem(f"{fps} FPS", fps)
        self._wallpaper_fps_combo.currentIndexChanged.connect(
            self._on_wallpaper_fps_changed
        )
        video_opts.addWidget(self._wallpaper_fps_combo)

        av_delay_hint = QLabel(
            "Задержка звука — видео спешит: больше, опаздывает: меньше",
            objectName="settingsRowDesc",
        )
        av_delay_hint.setWordWrap(True)
        video_opts.addWidget(av_delay_hint)
        self._wallpaper_av_delay_spin = QSpinBox()
        self._wallpaper_av_delay_spin.setObjectName("settingSpin")
        self._wallpaper_av_delay_spin.setRange(
            WALLPAPER_AV_DELAY_MIN_MS, WALLPAPER_AV_DELAY_MAX_MS
        )
        self._wallpaper_av_delay_spin.setSingleStep(10)
        self._wallpaper_av_delay_spin.setSuffix(" мс")
        self._wallpaper_av_delay_spin.valueChanged.connect(
            self._on_wallpaper_av_delay_changed
        )
        video_opts.addWidget(self._wallpaper_av_delay_spin)
        wallpaper_body.addWidget(self._wallpaper_video_opts)
        panel_layout.addWidget(wallpaper_row)

        eco_row, eco_body = self._row(
            "Фоновый режим",
            "Когда окно свёрнуто или не в фокусе — меньше CPU/GPU "
            "(удобно при играх). Музыка продолжает играть.",
        )
        self._eco_cb = QCheckBox("Экономить ресурсы в фоне")
        self._eco_cb.setObjectName("settingsCheck")
        self._eco_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eco_cb.toggled.connect(self._on_eco_toggled)
        eco_body.addWidget(self._eco_cb)
        panel_layout.addWidget(eco_row)

        panel_layout.addWidget(
            QLabel("Горячие клавиши", objectName="settingsSectionLabel")
        )
        binds_row, binds_body = self._row(
            "Binds",
            "Работают в любом месте окна. S в поле поиска печатает букву.",
        )
        for key, action in KEYBIND_HINTS:
            line = QLabel(f"{key}  —  {action}")
            line.setObjectName("settingsRowDesc")
            binds_body.addWidget(line)
        panel_layout.addWidget(binds_row)

        panel_layout.addWidget(QLabel("Хранилище", objectName="settingsSectionLabel"))

        music_row, music_body = self._row(
            "Папка для скачанной музыки",
            "Треки и обложки сохраняются сюда. Программа не пишет в свой "
            "каталог установки, поэтому права администратора не нужны.",
        )
        self._music_dir_label = QLabel()
        self._music_dir_label.setObjectName("settingsRowDesc")
        self._music_dir_label.setWordWrap(True)
        self._music_dir_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        music_body.addWidget(self._music_dir_label)

        music_buttons = QHBoxLayout()
        music_buttons.setContentsMargins(0, 4, 0, 0)
        music_buttons.setSpacing(8)
        for text, slot in (
            ("Изменить…", self._on_pick_music_dir),
            ("Открыть", self._on_open_music_dir),
            ("По умолчанию", self._on_reset_music_dir),
        ):
            button = QPushButton(text)
            button.setObjectName("settingsButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            music_buttons.addWidget(button)
        music_buttons.addStretch()
        music_body.addLayout(music_buttons)
        panel_layout.addWidget(music_row)

        data_row, data_body = self._row(
            "Каталог данных",
            "База истории, плейлисты, токены, плагины и пользовательские обои",
        )
        self._data_dir_label = QLabel()
        self._data_dir_label.setObjectName("settingsRowDesc")
        self._data_dir_label.setWordWrap(True)
        self._data_dir_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        data_body.addWidget(self._data_dir_label)

        open_data = QPushButton("Открыть")
        open_data.setObjectName("settingsButton")
        open_data.setCursor(Qt.CursorShape.PointingHandCursor)
        open_data.clicked.connect(self._on_open_data_dir)
        data_buttons = QHBoxLayout()
        data_buttons.setContentsMargins(0, 4, 0, 0)
        data_buttons.addWidget(open_data)
        data_buttons.addStretch()
        data_body.addLayout(data_buttons)
        panel_layout.addWidget(data_row)

        engine_row, engine_body = self._row(
            "Медиадвижок",
            "Задаётся при сборке exe (Quantis / Quantis-VLC) "
            "или переменной QUANTIS_MEDIA_BACKEND=qt|vlc",
        )
        self._engine_label = QLabel(backend_display_name(resolve_media_backend()))
        self._engine_label.setObjectName("settingsRowDesc")
        engine_body.addWidget(self._engine_label)
        panel_layout.addWidget(engine_row)

        panel_layout.addWidget(
            QLabel("О приложении", objectName="settingsSectionLabel")
        )

        about_row, about_body = self._row(
            "Версия",
            "Проверка новых релизов на GitHub. Установка — вручную со страницы релиза.",
        )
        self._version_label = QLabel()
        self._version_label.setObjectName("settingsRowDesc")
        self._version_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        about_body.addWidget(self._version_label)

        self._update_status = QLabel()
        self._update_status.setObjectName("settingsRowDesc")
        self._update_status.setWordWrap(True)
        about_body.addWidget(self._update_status)

        self._update_startup_cb = QCheckBox("Проверять при запуске")
        self._update_startup_cb.setObjectName("settingsCheck")
        self._update_startup_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_startup_cb.toggled.connect(self._on_update_startup_toggled)
        about_body.addWidget(self._update_startup_cb)

        update_buttons = QHBoxLayout()
        update_buttons.setContentsMargins(0, 4, 0, 0)
        update_buttons.setSpacing(8)
        self._update_check_btn = QPushButton("Проверить")
        self._update_check_btn.setObjectName("settingsButton")
        self._update_check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_check_btn.clicked.connect(self.check_for_update)
        self._update_open_btn = QPushButton("Открыть релиз")
        self._update_open_btn.setObjectName("settingsButton")
        self._update_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_open_btn.clicked.connect(self._on_open_release)
        self._update_open_btn.setEnabled(False)
        update_buttons.addWidget(self._update_check_btn)
        update_buttons.addWidget(self._update_open_btn)
        update_buttons.addStretch()
        about_body.addLayout(update_buttons)
        panel_layout.addWidget(about_row)

        panel_layout.addStretch()
        layout.addWidget(panel)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Разовый перенос выбора после переименования встроенных обоев
        remapped = remap_renamed_wallpaper(self._prefs.wallpaper_path)
        if remapped:
            self._prefs.set_wallpaper_path(remapped)

        self._prefs.changed.connect(self._sync_from_preferences)
        self._sync_from_preferences()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_wallpapers()

    def _row(self, title: str, desc: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("settingsRow")
        col = QVBoxLayout(frame)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)
        col.addWidget(QLabel(title, objectName="settingsRowTitle"))
        description = QLabel(desc, objectName="settingsRowDesc")
        # Без переноса длинное описание задаёт минимальную ширину всей панели.
        description.setWordWrap(True)
        col.addWidget(description)
        return frame, col

    def _sync_from_preferences(self) -> None:
        self._home_featured_cb.blockSignals(True)
        self._home_featured_cb.setChecked(self._prefs.show_home_featured_panel)
        self._home_featured_cb.blockSignals(False)

        self._now_playing_cb.blockSignals(True)
        self._now_playing_cb.setChecked(self._prefs.show_now_playing_panel)
        self._now_playing_cb.blockSignals(False)

        self._wallpaper_enabled_cb.blockSignals(True)
        self._wallpaper_enabled_cb.setChecked(self._prefs.wallpaper_enabled)
        self._wallpaper_enabled_cb.blockSignals(False)
        self._wallpaper_picker.setVisible(self._prefs.wallpaper_enabled)

        self._dynamic_wallpaper_cb.blockSignals(True)
        self._dynamic_wallpaper_cb.setChecked(self._prefs.dynamic_wallpaper_enabled)
        self._dynamic_wallpaper_cb.blockSignals(False)
        self._wallpaper_video_opts.setVisible(self._prefs.dynamic_wallpaper_enabled)

        self._wallpaper_quality_combo.blockSignals(True)
        quality_index = self._wallpaper_quality_combo.findData(
            self._prefs.dynamic_wallpaper_quality
        )
        if quality_index >= 0:
            self._wallpaper_quality_combo.setCurrentIndex(quality_index)
        self._wallpaper_quality_combo.blockSignals(False)

        self._wallpaper_fps_combo.blockSignals(True)
        fps_index = self._wallpaper_fps_combo.findData(
            self._prefs.dynamic_wallpaper_fps
        )
        if fps_index >= 0:
            self._wallpaper_fps_combo.setCurrentIndex(fps_index)
        self._wallpaper_fps_combo.blockSignals(False)

        self._wallpaper_av_delay_spin.blockSignals(True)
        self._wallpaper_av_delay_spin.setValue(
            self._prefs.dynamic_wallpaper_av_delay_ms
        )
        self._wallpaper_av_delay_spin.blockSignals(False)

        self._eco_cb.blockSignals(True)
        self._eco_cb.setChecked(self._prefs.background_eco_enabled)
        self._eco_cb.blockSignals(False)

        self._theme_combo.blockSignals(True)
        index = self._theme_combo.findData(self._prefs.ui_theme)
        if index >= 0:
            self._theme_combo.setCurrentIndex(index)
        self._theme_combo.blockSignals(False)

        self._sync_storage_labels()
        self._refresh_wallpapers(block_signals=True)
        self._sync_update_row()

    def _sync_storage_labels(self) -> None:
        music = app_paths.music_dir()
        suffix = "" if self._prefs.music_dir else "  ·  по умолчанию"
        self._music_dir_label.setText(f"{music}{suffix}")
        self._data_dir_label.setText(str(app_paths.data_dir()))

    def _on_pick_music_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Папка для скачанной музыки",
            str(app_paths.music_dir()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self._prefs.set_music_dir(chosen)

    def _on_reset_music_dir(self) -> None:
        self._prefs.set_music_dir("")

    def _on_open_music_dir(self) -> None:
        self._open_folder(app_paths.music_dir())

    def _on_open_data_dir(self) -> None:
        self._open_folder(app_paths.data_dir())

    @staticmethod
    def _open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _on_home_featured_toggled(self, checked: bool) -> None:
        self._prefs.set_show_home_featured_panel(checked)

    def _on_now_playing_toggled(self, checked: bool) -> None:
        self._prefs.set_show_now_playing_panel(checked)

    def _on_wallpaper_enabled_toggled(self, checked: bool) -> None:
        self._wallpaper_picker.setVisible(checked)
        self._prefs.set_wallpaper_enabled(checked)
        if checked:
            self._refresh_wallpapers()

    def _on_dynamic_wallpaper_toggled(self, checked: bool) -> None:
        self._wallpaper_video_opts.setVisible(checked)
        self._prefs.set_dynamic_wallpaper_enabled(checked)

    def _on_wallpaper_quality_changed(self, index: int) -> None:
        height = self._wallpaper_quality_combo.itemData(index)
        if height is not None:
            self._prefs.set_dynamic_wallpaper_quality(int(height))

    def _on_wallpaper_fps_changed(self, index: int) -> None:
        fps = self._wallpaper_fps_combo.itemData(index)
        if fps is not None:
            self._prefs.set_dynamic_wallpaper_fps(int(fps))

    def _on_wallpaper_av_delay_changed(self, value: int) -> None:
        self._prefs.set_dynamic_wallpaper_av_delay_ms(int(value))

    def _on_eco_toggled(self, checked: bool) -> None:
        self._prefs.set_background_eco_enabled(checked)

    def _refresh_wallpapers(self, *, block_signals: bool = False) -> None:
        if not self._prefs.wallpaper_enabled:
            self._wallpaper_picker.hide()
            return

        self._wallpaper_picker.show()
        if block_signals:
            self._wallpaper_combo.blockSignals(True)

        current = self._prefs.wallpaper_path
        self._wallpaper_combo.clear()
        self._wallpaper_combo.addItem("По умолчанию", "")

        files = scan_wallpapers()
        for path in files:
            self._wallpaper_combo.addItem(
                wallpaper_display_name(path),
                str(path.resolve()),
            )

        folder = user_backgrounds_dir()
        if not files:
            self._wallpaper_status.setText(f"Пока пусто. Положите jpg/png в:\n{folder}")
        else:
            user_count = sum(
                1 for p in files if str(p.parent.resolve()) == str(folder.resolve())
            )
            self._wallpaper_status.setText(
                f"Найдено: {len(files)} · ваших: {user_count}\nПапка: {folder}"
            )

        index = self._wallpaper_combo.findData(current)
        if index < 0 and current:
            self._wallpaper_combo.addItem(f"⚠ {Path(current).name}", current)
            index = self._wallpaper_combo.findData(current)
        self._wallpaper_combo.setCurrentIndex(index if index >= 0 else 0)

        if block_signals:
            self._wallpaper_combo.blockSignals(False)

    def _on_wallpaper_changed(self, index: int) -> None:
        path = self._wallpaper_combo.itemData(index)
        self._prefs.set_wallpaper_path(str(path) if path else "")

    def _on_theme_changed(self, index: int) -> None:
        theme_id = self._theme_combo.itemData(index)
        if theme_id:
            theme_id = str(theme_id)
            self._prefs.set_ui_theme(theme_id)
            if theme_id == "glass" and not self._prefs.wallpaper_enabled:
                self._prefs.set_wallpaper_enabled(True)

    def _sync_update_row(self) -> None:
        current = app_version()
        engine = backend_display_name(resolve_media_backend())
        self._version_label.setText(f"{current}  ·  {engine}")
        self._update_startup_cb.blockSignals(True)
        self._update_startup_cb.setChecked(self._prefs.update_check_on_startup)
        self._update_startup_cb.blockSignals(False)
        self.apply_update_from_prefs()

    def apply_update_from_prefs(self) -> None:
        if self._update_loading:
            return
        current = app_version()
        tag = self._prefs.update_last_tag
        url = self._prefs.update_last_html_url
        self._release_url = url if is_safe_release_url(url) else ""
        if tag and is_newer(current, tag):
            shown = display_version(tag)
            self._update_status.setText(f"Доступна {shown}")
            self._update_open_btn.setEnabled(bool(url))
        elif self._prefs.update_last_check_at > 0:
            self._update_status.setText("Актуальная")
            self._update_open_btn.setEnabled(bool(url))
        else:
            self._update_status.setText("Ещё не проверяли")
            self._update_open_btn.setEnabled(False)

    def set_update_checking(self) -> None:
        self._update_loading = True
        self._update_check_btn.setEnabled(False)
        self._update_status.setText("Проверка…")

    def check_for_update(self) -> None:
        if self._bridge is None or self._update_loading:
            return
        self.set_update_checking()
        self._bridge.schedule(self._load_update())

    async def _load_update(self) -> None:
        try:
            info = await fetch_latest_release()
        except Exception as exc:
            if self._bridge is not None:
                self._bridge.invoke_main(lambda m=str(exc): self._on_update_failed(m))
            return
        if self._bridge is not None:
            self._bridge.invoke_main(lambda i=info: self._on_update_ok(i))

    def _on_update_failed(self, message: str) -> None:
        self._update_loading = False
        self._update_check_btn.setEnabled(True)
        self._update_status.setText(f"Не удалось проверить: {message}")

    def _on_update_ok(self, info: ReleaseInfo | None) -> None:
        self._update_loading = False
        self._update_check_btn.setEnabled(True)
        if info is not None:
            self._prefs.set_update_last_tag(info.tag)
            self._prefs.set_update_last_html_url(info.html_url)
        self._prefs.set_update_last_check_at(time.time())
        self.apply_update_from_prefs()
        self.update_checked.emit()

    def _on_update_startup_toggled(self, checked: bool) -> None:
        self._prefs.set_update_check_on_startup(checked)

    def _on_open_release(self) -> None:
        if self._release_url and is_safe_release_url(self._release_url):
            QDesktopServices.openUrl(QUrl(self._release_url))
