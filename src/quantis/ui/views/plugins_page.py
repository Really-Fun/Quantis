"""Страница плагинов — установка, импорт, включение/выключение."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.plugins import PluginRegistry
from quantis.plugins.installer import (
    PluginInstallError,
    install_plugin_from_url,
    install_plugin_from_zip,
)
from quantis.plugins.loader import resolve_plugins_dir
from quantis.ui import resources
from quantis.ui.views.widgets.glass_panel import GlassPanel

logger = logging.getLogger(__name__)


class PluginsPage(QWidget):
    def __init__(
        self,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._registry = PluginRegistry.instance()
        self._toggles: dict[str, QCheckBox] = {}
        self.setObjectName("pluginsPage")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        self._outer = QVBoxLayout(content)
        self._outer.setContentsMargins(16, 8, 16, 20)
        self._outer.setSpacing(12)

        panel = GlassPanel()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("ПЛАГИНЫ")
        title.setObjectName("settingsSectionLabel")
        header.addWidget(title)
        header.addStretch()
        puzzle = QLabel()
        puzzle.setPixmap(resources.load_icon("puzzle.svg").pixmap(18, 18))
        puzzle.setToolTip("Элементы от плагинов помечаются иконкой пазла")
        header.addWidget(puzzle)
        panel_layout.addLayout(header)

        self._path_label = QLabel(f"Папка: {resolve_plugins_dir()}")
        self._path_label.setObjectName("settingsRowDesc")
        self._path_label.setWordWrap(True)
        panel_layout.addWidget(self._path_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._import_btn = QPushButton("Импорт из архива")
        self._import_btn.setObjectName("searchButton")
        self._import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._import_btn.clicked.connect(self._import_archive)

        self._download_btn = QPushButton("Скачать по URL")
        self._download_btn.setObjectName("nowPlayingStubBtn")
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.clicked.connect(self._download_url)

        self._folder_btn = QPushButton("Открыть папку")
        self._folder_btn.setObjectName("nowPlayingStubBtn")
        self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._folder_btn.clicked.connect(self._open_folder)

        self._refresh_btn = QPushButton("Обновить")
        self._refresh_btn.setObjectName("nowPlayingStubBtn")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._refresh)

        for btn in (
            self._import_btn,
            self._download_btn,
            self._folder_btn,
            self._refresh_btn,
        ):
            actions.addWidget(btn)
        actions.addStretch()
        panel_layout.addLayout(actions)

        self._status = QLabel("")
        self._status.setObjectName("settingsRowDesc")
        self._status.setWordWrap(True)
        panel_layout.addWidget(self._status)

        installed = QLabel("Установленные")
        installed.setObjectName("settingsSectionLabel")
        panel_layout.addWidget(installed)

        self._cards_host = QVBoxLayout()
        self._cards_host.setSpacing(10)
        panel_layout.addLayout(self._cards_host)

        panel_layout.addStretch()
        self._outer.addWidget(panel)
        self._outer.addStretch()

        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self._registry.plugin_changed.connect(self._refresh)
        self._refresh()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._path_label.setText(f"Папка: {resolve_plugins_dir()}")
        self._refresh()

    def _clear_cards(self) -> None:
        while self._cards_host.count():
            item = self._cards_host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._toggles.clear()

    def _refresh(self, *_args) -> None:
        self._registry.rescan()
        self._clear_cards()
        infos = sorted(self._registry.get_all(), key=lambda i: i.meta.name.lower())
        if not infos:
            empty = QLabel(
                "Плагины не найдены. Импортируйте .zip с plugin.py и manifest.json "
                "или положите папку вручную."
            )
            empty.setObjectName("settingsRowDesc")
            empty.setWordWrap(True)
            self._cards_host.addWidget(empty)
            return

        for info in infos:
            self._cards_host.addWidget(self._make_card(info))

    def _make_card(self, info) -> QFrame:
        meta = info.meta
        card = QFrame()
        card.setObjectName("pluginCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(resources.load_icon("puzzle.svg").pixmap(28, 28))
        row.addWidget(icon)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(meta.name)
        name.setObjectName("pluginCardTitle")
        author_bits = [f"v{meta.version}", meta.plugin_id]
        if meta.author and meta.author != "Unknown":
            author_bits.append(meta.author)
        author = QLabel(" · ".join(author_bits))
        author.setObjectName("pluginCardAuthor")
        desc = QLabel(meta.description or "Без описания")
        desc.setObjectName("pluginCardDesc")
        desc.setWordWrap(True)
        col.addWidget(name)
        col.addWidget(author)
        col.addWidget(desc)
        if not meta.is_valid:
            err = QLabel("; ".join(meta.errors) or "Некорректный плагин")
            err.setObjectName("pluginCardDesc")
            err.setStyleSheet("color: #FF4E45;")
            err.setWordWrap(True)
            col.addWidget(err)
        elif info.error:
            err = QLabel(info.error)
            err.setObjectName("pluginCardDesc")
            err.setStyleSheet("color: #FF4E45;")
            err.setWordWrap(True)
            col.addWidget(err)
        row.addLayout(col, stretch=1)

        toggle = QCheckBox("Включено")
        toggle.setObjectName("settingsCheck")
        toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle.blockSignals(True)
        toggle.setChecked(info.is_active)
        toggle.blockSignals(False)
        invalid = not meta.is_valid
        toggle.setEnabled(not invalid)
        pid = meta.plugin_id
        toggle.toggled.connect(lambda checked, p=pid: self._toggle(p, checked))
        self._toggles[pid] = toggle
        row.addWidget(toggle, 0, Qt.AlignmentFlag.AlignTop)
        return card

    def _toggle(self, plugin_id: str, enabled: bool) -> None:
        if self._bridge is None:
            return

        async def _run() -> None:
            if enabled:
                await self._registry.enable(plugin_id)
            else:
                await self._registry.disable(plugin_id)

        self._bridge.schedule(_run())

    def _confirm_untrusted_plugin(self, source: str) -> bool:
        reply = QMessageBox.warning(
            self,
            "Установка плагина",
            "Плагины выполняются с правами Quantis: доступ к токенам, "
            "файлам и сети. Ставьте только архивы из доверенных источников.\n\n"
            f"{source}\n\nПродолжить установку?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _import_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт плагина",
            "",
            "Архив плагина (*.zip)",
        )
        if not path:
            return
        if not self._confirm_untrusted_plugin(path):
            return
        try:
            plugin_id = install_plugin_from_zip(path, overwrite=True)
            self._status.setText(f"Установлен: {plugin_id}")
            self._refresh()
        except PluginInstallError as exc:
            QMessageBox.warning(self, "Импорт плагина", str(exc))
        except Exception as exc:
            logger.exception("import plugin")
            QMessageBox.critical(self, "Импорт плагина", str(exc))

    def _download_url(self) -> None:
        url, ok = QInputDialog.getText(
            self,
            "Скачать плагин",
            "HTTPS-URL zip-архива плагина:",
        )
        if not ok or not url.strip():
            return
        url = url.strip()
        if not self._confirm_untrusted_plugin(url):
            return
        self._status.setText("Скачивание…")
        self._download_btn.setEnabled(False)

        if self._bridge is None:
            try:
                plugin_id = install_plugin_from_url(url, overwrite=True)
                self._on_install_ok(plugin_id)
            except Exception as exc:
                self._on_install_fail(str(exc))
            return

        from quantis.ui.async_ui import schedule

        async def _async() -> None:
            import asyncio

            loop = asyncio.get_running_loop()
            try:
                plugin_id = await loop.run_in_executor(
                    None,
                    lambda: install_plugin_from_url(url, overwrite=True),
                )
                self._bridge.invoke_main(lambda: self._on_install_ok(plugin_id))
            except Exception as exc:
                msg = str(exc)
                self._bridge.invoke_main(lambda: self._on_install_fail(msg))

        schedule(_async(), self._bridge)

    def _on_install_ok(self, plugin_id: str) -> None:
        self._download_btn.setEnabled(True)
        self._status.setText(f"Скачан и установлен: {plugin_id}")
        self._refresh()

    def _on_install_fail(self, message: str) -> None:
        self._download_btn.setEnabled(True)
        self._status.setText("")
        QMessageBox.warning(self, "Скачать плагин", message)

    def _open_folder(self) -> None:
        folder = resolve_plugins_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(folder.as_uri())
