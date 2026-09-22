"""Диалог / меню «Добавить в плейлист»."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QCursor
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox, QWidget

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.services.user_playlists import UserPlaylistsService


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


def show_add_to_playlist_menu(
    track: Track,
    *,
    bridge: AsyncBridge,
    parent: QWidget | None = None,
    on_done: Callable[[], None] | None = None,
    event_bus=None,
) -> None:
    """Меню плейлистов → добавить трек (или создать новый)."""
    service = UserPlaylistsService()

    def _notify() -> None:
        if on_done is not None:
            on_done()
        if event_bus is not None:
            event_bus.playlists_updated.emit()

    async def load_and_show() -> None:
        names = await service.list_names()

        def show_menu() -> None:
            menu = QMenu(parent)
            menu.setObjectName("playlistPickMenu")
            for name in names:
                action = QAction(name, menu)

                def _pick(checked: bool = False, n: str = name) -> None:
                    bridge.schedule(
                        add_track_to_named(n, track, bridge, parent, _notify)
                    )

                action.triggered.connect(_pick)
                menu.addAction(action)
            if names:
                menu.addSeparator()
            create_action = QAction("Новый плейлист…", menu)
            create_action.triggered.connect(
                lambda: create_playlist_and_add(track, bridge, parent, _notify)
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
    if on_done is not None:
        bridge.invoke_main(on_done)


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
        if not added:
            QMessageBox.information(
                parent,
                "Плейлист",
                f"«{track.title}» уже есть в «{playlist_name}»",
            )
        if on_done is not None:
            on_done()

    bridge.invoke_main(notify)
