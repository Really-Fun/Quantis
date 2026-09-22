"""Шина событий приложения.

Построена на базе Qt Signals.
Обеспечивает потокобезопасность и автоматическое удаление подписок
при удалении объектов (никаких утечек памяти).
"""

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    """Центральная шина событий приложения."""

    track_changed = Signal(object)  # Передает объект Track
    history_updated = Signal()  # История прослушивания записана в БД
    playlists_updated = Signal()  # Пользовательские плейлисты изменились
    playback_paused = Signal()
    playback_resumed = Signal()
    playback_stopped = Signal()
    playback_seeked = Signal(int)  # Позиция в мс после перемотки
    track_finished = Signal()
    queue_extended = Signal(object)  # Очередь радио/рекомендаций выросла

    next_requested = Signal()
    previous_requested = Signal()

    theme_changed = Signal(str)  # Передает 'dark' или 'light'
    plugin_loaded = Signal(str)  # Передает plugin_id
    plugin_unloaded = Signal(str)  # Передает plugin_id
    error_occurred = Signal(str)  # Передает текст ошибки для показа в UI

    def __init__(self) -> None:
        super().__init__()
        self._subscriptions: dict[callable, set[str]] = {}

    def subscribe(self, event_name: str, callback: callable) -> None:
        if hasattr(self, event_name):
            signal = getattr(self, event_name)
            signal.connect(callback)
            if callback not in self._subscriptions:
                self._subscriptions[callback] = set()
            self._subscriptions[callback].add(event_name)
        else:
            raise ValueError(f"Unknown event: {event_name}")

    def unsubscribe(self, event_name: str, callback: callable) -> None:
        if hasattr(self, event_name):
            signal = getattr(self, event_name)
            try:
                signal.disconnect(callback)
                if (
                    callback in self._subscriptions
                    and event_name in self._subscriptions[callback]
                ):
                    self._subscriptions[callback].remove(event_name)
                    if not self._subscriptions[callback]:
                        del self._subscriptions[callback]
            except RuntimeError:
                pass
        else:
            raise ValueError(f"Unknown event: {event_name}")

    def unsubscribe_all(self, callback: callable) -> None:
        if callback in self._subscriptions:
            events = list(self._subscriptions[callback])
            for event_name in events:
                self.unsubscribe(event_name, callback)
