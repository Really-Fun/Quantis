"""Менеджер плагинов: «Установленные» (включить, обновить, удалить) и «Магазин»."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.plugins import PluginRegistry
from quantis.plugins.installer import PluginInstallError, install_plugin_from_zip
from quantis.plugins.loader import resolve_plugins_dir
from quantis.plugins.store import StoreError, StorePlugin, download_plugin, store_action
from quantis.ui import resources
from quantis.ui.views.widgets.page_layout import (
    CONTENT_MAX_W,
    PageTitle,
    apply_page_margins,
)
from quantis.ui.views.widgets.switch import Switch
from quantis.utils import app_paths

logger = logging.getLogger(__name__)

Notify = Callable[..., None]
Download = Callable[[object, StorePlugin, Path], Awaitable[Path]]

_COVER_SIZE = 48
_MAX_COVER_BYTES = 2 * 1024 * 1024


def _label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _button(text: str, name: str, slot: Callable[[], None]) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(lambda _checked=False: slot())
    return button


def _error_label(text: str) -> QLabel:
    label = _label(text, "pluginCardDesc", wrap=True)
    label.setStyleSheet("color: #FF4E45;")
    return label


def _clear(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            # Сразу убираем со страницы: deleteLater сработает позже, а старая
            # карточка до тех пор висела бы рядом с новой.
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class PluginsPage(QWidget):
    INSTALLED, STORE = range(2)

    def __init__(
        self,
        bridge: AsyncBridge | None = None,
        account=None,
        updates=None,
        *,
        registry=None,
        notify: Notify | None = None,
        download: Download | None = None,
        open_accounts: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._account = account
        self._updates = updates
        self._registry = registry or PluginRegistry.instance()
        self._notify = notify or (lambda *args, **kwargs: None)
        self._download = download or download_plugin
        self._open_accounts = open_accounts or (lambda: None)
        self._busy: set[str] = set()
        self._toggles: dict[str, Switch] = {}
        self._covers: dict[str, bytes] = {}
        self.setObjectName("pluginsPage")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        outer = QVBoxLayout(content)
        apply_page_margins(outer, spacing=0)

        panel = QWidget()
        panel.setObjectName("settingsPanel")
        panel.setMaximumWidth(CONTENT_MAX_W)
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        col.addWidget(
            PageTitle(
                "Менеджер плагинов",
                "Включайте и обновляйте плагины, ставьте новые из магазина Quantis",
            )
        )

        tabs = QHBoxLayout()
        tabs.setSpacing(8)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._installed_tab = self._make_tab("Установленные", self.INSTALLED)
        self._store_tab = self._make_tab("Магазин", self.STORE)
        tabs.addWidget(self._installed_tab)
        tabs.addWidget(self._store_tab)
        tabs.addStretch()
        col.addLayout(tabs)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_installed())
        self._stack.addWidget(self._build_store())
        col.addWidget(self._stack)
        col.addStretch()
        outer.addWidget(panel)
        outer.addStretch()

        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self._registry.plugin_changed.connect(self._refresh_installed)
        if updates is not None:
            updates.updates_changed.connect(self._refresh_all)
        self.show_installed()
        self._refresh_all()

    # ------------------------------------------------------------ вкладки

    def _make_tab(self, text: str, index: int) -> QToolButton:
        tab = QToolButton()
        tab.setObjectName("sourceFilterChip")
        tab.setText(text)
        tab.setCheckable(True)
        tab.setCursor(Qt.CursorShape.PointingHandCursor)
        tab.clicked.connect(lambda _checked=False, i=index: self._show_tab(i))
        self._tab_group.addButton(tab, index)
        return tab

    def _show_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._tab_group.button(index).setChecked(True)

    def show_installed(self) -> None:
        self._show_tab(self.INSTALLED)

    def show_store(self) -> None:
        self._show_tab(self.STORE)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._folder_btn.setToolTip(str(resolve_plugins_dir()))
        self._registry.rescan()
        self._refresh_all()
        if self._updates is not None and self._bridge is not None:
            self._bridge.schedule(self._updates.refresh())

    def _refresh_all(self, *_args) -> None:
        self._refresh_installed()
        self._refresh_store()

    # ------------------------------------------------------------ установленные

    def _build_installed(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(
            _button("Импорт из архива", "nowPlayingStubBtn", self._import_archive)
        )
        self._folder_btn = _button(
            "Открыть папку", "nowPlayingStubBtn", self._open_folder
        )
        actions.addWidget(self._folder_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self._installed_cards = QVBoxLayout()
        self._installed_cards.setSpacing(10)
        layout.addLayout(self._installed_cards)
        layout.addStretch()  # карточки — сверху, а не растянуты на всю вкладку
        return page

    def _available_updates(self) -> dict[str, StorePlugin]:
        return dict(getattr(self._updates, "updates", {}) or {})

    def _refresh_installed(self, *_args) -> None:
        _clear(self._installed_cards)
        self._toggles.clear()
        infos = sorted(self._registry.get_all(), key=lambda i: i.meta.name.lower())
        if not infos:
            self._installed_cards.addWidget(
                _label(
                    "Плагинов пока нет. Загляните в «Магазин» или импортируйте .zip "
                    "с plugin.py и manifest.json.",
                    "settingsRowDesc",
                    wrap=True,
                )
            )
            return
        updates = self._available_updates()
        for info in infos:
            self._installed_cards.addWidget(
                self._installed_card(info, updates.get(info.meta.plugin_id))
            )

    def _installed_card(self, info, update: StorePlugin | None) -> QFrame:
        meta = info.meta
        card, row, col = self._card_frame(
            resources.load_icon("puzzle.svg").pixmap(28, 28)
        )
        col.addWidget(_label(meta.name, "pluginCardTitle"))
        bits = [f"v{meta.version}", meta.plugin_id]
        if meta.author and meta.author != "Unknown":
            bits.append(meta.author)
        if self._registry.is_bundled(meta.plugin_id):
            bits.append("встроенный")
        col.addWidget(_label(" · ".join(bits), "pluginCardAuthor"))
        col.addWidget(
            _label(meta.description or "Без описания", "pluginCardDesc", wrap=True)
        )
        if not meta.is_valid:
            col.addWidget(_error_label("; ".join(meta.errors) or "Некорректный плагин"))
        elif info.error:
            col.addWidget(_error_label(info.error))

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        pid = meta.plugin_id
        if update is not None:
            if pid in self._busy:
                busy = _button("Обновление…", "searchButton", lambda: None)
                busy.setEnabled(False)
                buttons.addWidget(busy)
            else:
                buttons.addWidget(
                    _button(
                        f"Обновить до v{update.version}",
                        "searchButton",
                        lambda item=update: self._install(item),
                    )
                )
        if not self._registry.is_bundled(pid):
            buttons.addWidget(
                _button(
                    "Удалить",
                    "memberDanger",
                    lambda p=pid, n=meta.name: self._uninstall(p, n),
                )
            )
        buttons.addStretch()
        col.addLayout(buttons)

        toggle = Switch()
        toggle.setObjectName("pluginSwitch")
        toggle.setToolTip("Выключить" if info.is_active else "Включить")
        toggle.setAccessibleName(f"Плагин {meta.name}")
        toggle.blockSignals(True)
        toggle.setChecked(info.is_active)
        toggle.blockSignals(False)
        toggle.setEnabled(meta.is_valid)
        toggle.toggled.connect(lambda checked, p=pid: self._toggle(p, checked))
        self._toggles[pid] = toggle
        row.addWidget(toggle, 0, Qt.AlignmentFlag.AlignTop)
        return card

    def _toggle(self, plugin_id: str, enabled: bool) -> None:
        if self._bridge is None:
            return

        async def run() -> None:
            if enabled:
                await self._registry.enable(plugin_id)
            else:
                await self._registry.disable(plugin_id)

        self._bridge.schedule(run())

    def _uninstall(self, plugin_id: str, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Удалить плагин",
            f"Удалить плагин «{name}»? Его файлы будут удалены с этого компьютера.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes or self._bridge is None:
            return

        async def run() -> None:
            try:
                await self._registry.uninstall(plugin_id)
            except (PluginInstallError, OSError) as exc:
                message = str(exc)
                self._bridge.invoke_main(
                    lambda: self._notify(
                        f"Не удалось удалить «{name}»", message, "error"
                    )
                )
                return
            self._bridge.invoke_main(
                lambda: self._notify(f"Плагин «{name}» удалён", "", "info")
            )

        self._bridge.schedule(run())

    def _import_archive(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт плагина", "", "Архив плагина (*.zip)"
        )
        if not path:
            return
        reply = QMessageBox.warning(
            self,
            "Установка плагина",
            "Плагины выполняются с правами Quantis: доступ к токенам, "
            "файлам и сети. Ставьте только архивы из доверенных источников.\n\n"
            f"{path}\n\nПродолжить установку?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            plugin_id = install_plugin_from_zip(path, overwrite=True)
        except PluginInstallError as exc:
            self._notify("Не удалось импортировать плагин", str(exc), "error")
            return
        except Exception as exc:
            logger.exception("Импорт плагина")
            self._notify("Не удалось импортировать плагин", str(exc), "error")
            return
        self._registry.rescan()
        self._notify(
            f"Плагин «{plugin_id}» установлен", "Включите его переключателем", "success"
        )
        self._refresh_installed()

    def _open_folder(self) -> None:
        folder = resolve_plugins_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------ магазин

    def _build_store(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._store_message = _label("", "settingsRowDesc", wrap=True)
        layout.addWidget(self._store_message)
        actions = QHBoxLayout()
        self._login_btn = _button(
            "Открыть аккаунты", "searchButton", self._open_accounts
        )
        self._retry_btn = _button("Повторить", "nowPlayingStubBtn", self._retry)
        actions.addWidget(self._login_btn)
        actions.addWidget(self._retry_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self._store_cards = QVBoxLayout()
        self._store_cards.setSpacing(10)
        layout.addLayout(self._store_cards)
        layout.addStretch()
        return page

    def _logged_in(self) -> bool:
        if self._account is not None and not self._account.is_logged_in:
            return False
        return not getattr(self._updates, "logged_out", False)

    def _refresh_store(self, *_args) -> None:
        _clear(self._store_cards)
        updates = self._updates
        logged_in = self._logged_in()
        error = getattr(updates, "error", "") if updates is not None else ""
        store = list(getattr(updates, "store", []) or [])
        self._login_btn.setVisible(not logged_in)
        self._retry_btn.setVisible(logged_in and bool(error))
        if not logged_in:
            self._show_store_message(
                "Войдите в аккаунт Quantis, чтобы смотреть и ставить плагины из магазина."
            )
            return
        if error:
            self._show_store_message(error)
        elif not store:
            self._show_store_message("В магазине пока пусто.")
        else:
            self._show_store_message("")
        for item in sorted(store, key=lambda i: i.title.lower()):
            self._store_cards.addWidget(self._store_card(item))

    def _show_store_message(self, text: str) -> None:
        self._store_message.setText(text)
        self._store_message.setVisible(bool(text))

    def _retry(self) -> None:
        if self._updates is not None and self._bridge is not None:
            self._bridge.schedule(self._updates.refresh())

    def _store_card(self, item: StorePlugin) -> QFrame:
        cover = resources.load_icon("puzzle.svg").pixmap(_COVER_SIZE, _COVER_SIZE)
        card, row, col = self._card_frame(cover)
        col.addWidget(_label(item.title, "pluginCardTitle"))
        bits = [f"v{item.version}"]
        if item.author:
            bits.append(item.author)
        col.addWidget(_label(" · ".join(bits), "pluginCardAuthor"))
        col.addWidget(
            _label(item.description or "Без описания", "pluginCardDesc", wrap=True)
        )
        if item.cover_url:
            self._load_cover(item.cover_url, card.property("coverLabel"))

        action = store_action(item, self._registry.installed_version(item.plugin_id))
        if item.plugin_id in self._busy:
            button = _button("Установка…", "searchButton", lambda: None)
            button.setEnabled(False)
        elif action == "install":
            button = _button("Установить", "searchButton", lambda: self._install(item))
        elif action == "update":
            button = _button("Обновить", "searchButton", lambda: self._install(item))
        else:
            button = _button("Установлено", "nowPlayingStubBtn", lambda: None)
            button.setEnabled(False)
        row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        return card

    def _card_frame(self, pixmap: QPixmap) -> tuple[QFrame, QHBoxLayout, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("pluginCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)
        icon = QLabel()
        icon.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(pixmap)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        card.setProperty("coverLabel", icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        row.addLayout(col, stretch=1)
        return card, row, col

    def _load_cover(self, url: str, label: QLabel) -> None:
        cached = self._covers.get(url)
        if cached is not None:
            self._set_cover(label, cached)
            return
        if self._bridge is None:
            return

        async def fetch() -> None:
            try:
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            return
                        data = await response.content.read(_MAX_COVER_BYTES + 1)
            except (aiohttp.ClientError, TimeoutError):
                return
            if len(data) > _MAX_COVER_BYTES:
                return
            self._covers[url] = data
            self._bridge.invoke_main(lambda: self._set_cover(label, data))

        self._bridge.schedule(fetch())

    @staticmethod
    def _set_cover(label: QLabel, data: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        try:
            label.setPixmap(
                pixmap.scaled(
                    _COVER_SIZE,
                    _COVER_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except RuntimeError:
            pass  # карточку уже пересобрали

    # ------------------------------------------------------------ установка

    def _install(self, item: StorePlugin) -> None:
        if self._bridge is None or item.plugin_id in self._busy:
            return
        updating = self._registry.installed_version(item.plugin_id) is not None
        self._busy.add(item.plugin_id)
        self._refresh_all()

        async def run() -> None:
            path: Path | None = None
            error = ""
            ok = False
            try:
                dest = app_paths.cache_dir() / "plugin_downloads"
                path = await self._download(self._account, item, dest)
                ok = await self._registry.install(path, item.plugin_id)
            except (StoreError, PluginInstallError) as exc:
                error = str(exc)
            except Exception as exc:
                logger.exception("Установка плагина %s", item.plugin_id)
                error = str(exc) or "Неизвестная ошибка"
            finally:
                if path is not None:
                    await asyncio.to_thread(path.unlink, missing_ok=True)
            self._bridge.invoke_main(
                lambda: self._install_done(item, updating, ok, error)
            )

        self._bridge.schedule(run())

    def _install_done(
        self, item: StorePlugin, updating: bool, ok: bool, error: str
    ) -> None:
        self._busy.discard(item.plugin_id)
        if error:
            verb = "обновить" if updating else "установить"
            self._notify(f"Не удалось {verb} «{item.title}»", error, "error")
        elif not ok:
            info = next(
                (
                    i
                    for i in self._registry.get_all()
                    if i.meta.plugin_id == item.plugin_id
                ),
                None,
            )
            detail = info.error if info is not None else ""
            if updating:
                self._notify(
                    f"«{item.title}» v{item.version} не запустился",
                    f"Оставлена прежняя версия. {detail}".strip(),
                    "error",
                )
            else:
                self._notify(
                    f"«{item.title}» установлен, но не запустился", detail, "error"
                )
        elif updating:
            self._notify(
                f"Плагин «{item.title}» обновлён до v{item.version}", "", "success"
            )
        else:
            self._notify(f"Плагин «{item.title}» установлен", "", "success")
        if self._updates is not None:
            self._updates.recount()
        self._refresh_all()
