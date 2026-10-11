"""Диалог / меню «Добавить в плейлист»."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox, QWidget

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.services.user_playlists import UserPlaylistsService

logger = logging.getLogger(__name__)

_event_bus = None


def bind_event_bus(event_bus) -> None:
    """Шина, через которую главное окно узнаёт об изменении плейлистов."""
    global _event_bus
    _event_bus = event_bus


def _announce_playlists_updated() -> None:
    # Главное окно обновляет главную и открытый плейлист — откуда бы ни добавили.
    if _event_bus is not None:
        _event_bus.playlists_updated.emit()


def prompt_new_playlist_name(parent: QWidget | None = None) -> str | None:
    name, ok = QInputDialog.getText(
        parent,
        "Новый плейлист",
        "Название плейлиста:",
    )
    if not ok:
        return None
    clean = name.strip()
    return clean or None


def add_track_actions(menu: QMenu, track: Track) -> bool:
    """Пункты плагинов для трека (например, «Предложить в комнату»). True — что-то добавили."""
    from quantis.ui.ui_extensions import UiExtensionHost

    added = False
    for extension in UiExtensionHost.instance().track_actions():
        try:
            label = extension.label(track)
        except Exception:
            logger.exception("Пункт меню трека %s сломался", extension.action_id)
            continue
        if not label:
            continue
        action = QAction(label, menu)
        action.triggered.connect(lambda checked=False, cb=extension.callback: cb(track))
        menu.addAction(action)
        added = True
    return added


def show_add_to_playlist_menu(
    track: Track,
    *,
    bridge: AsyncBridge,
    parent: QWidget | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Меню плейлистов → добавить трек (или создать новый)."""
    service = UserPlaylistsService()

    async def load_and_show() -> None:
        names = await service.list_names()

        def show_menu() -> None:
            menu = QMenu(parent)
            menu.setObjectName("playlistPickMenu")
            if add_track_actions(menu, track):
                menu.addSeparator()
            for name in names:
                action = QAction(name, menu)

                def _pick(checked: bool = False, n: str = name) -> None:
                    bridge.schedule(
                        add_track_to_named(n, track, bridge, parent, on_done)
                    )

                action.triggered.connect(_pick)
                menu.addAction(action)
            if names:
                menu.addSeparator()
            create_action = QAction("Новый плейлист…", menu)
            create_action.triggered.connect(
                lambda: create_playlist_and_add(track, bridge, parent, on_done)
            )
            menu.addAction(create_action)
            menu.exec(QCursor.pos())

        bridge.invoke_main(show_menu)

    bridge.schedule(load_and_show())


def create_playlist_and_add(
    track: Track | None,
    bridge: AsyncBridge,
    parent: QWidget | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Создать плейлист (и опционально сразу добавить трек)."""
    name = prompt_new_playlist_name(parent)
    if not name:
        return
    bridge.schedule(_create_async(name, track, bridge, parent, on_done))


async def _create_async(
    name: str,
    track: Track | None,
    bridge: AsyncBridge,
    parent: QWidget | None,
    on_done: Callable[[], None] | None,
) -> None:
    service = UserPlaylistsService()
    try:
        await service.create(name)
        if track is not None:
            await service.add_track(name, track)
    except FileExistsError as err:
        message = str(err)
        if track is not None:
            await service.add_track(name, track)
        else:
            bridge.invoke_main(lambda: QMessageBox.warning(parent, "Плейлист", message))
            return
    except Exception as err:
        message = str(err)
        bridge.invoke_main(
            lambda: QMessageBox.warning(
                parent, "Плейлист", f"Не удалось создать плейлист:\n{message}"
            )
        )
        return

    def notify() -> None:
        _announce_playlists_updated()
        if on_done is not None:
            on_done()

    bridge.invoke_main(notify)


async def add_track_to_named(
    playlist_name: str,
    track: Track,
    bridge: AsyncBridge,
    parent: QWidget | None,
    on_done: Callable[[], None] | None,
) -> None:
    service = UserPlaylistsService()
    try:
        added = await service.add_track(playlist_name, track)
    except Exception as err:
        message = str(err)
        bridge.invoke_main(
            lambda: QMessageBox.warning(
                parent, "Плейлист", f"Не удалось добавить трек:\n{message}"
            )
        )
        return

    def notify() -> None:
        if added:
            _announce_playlists_updated()
        else:
            QMessageBox.information(
                parent,
                "Плейлист",
                f"«{track.title}» уже есть в «{playlist_name}»",
            )
        if on_done is not None:
            on_done()

    bridge.invoke_main(notify)
