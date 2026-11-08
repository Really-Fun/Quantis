"""Всплывающие уведомления: стопка в правом верхнем углу."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QWidget

from quantis.models import YandexTrack
from quantis.ui.views.widgets.notifications import (
    DownloadNotification,
    Notification,
    NotificationCenter,
)


def _host(qapp):
    host = QWidget()
    host.resize(1200, 800)
    host.show()
    return host


def test_stack_newest_on_top_right_aligned(qapp):
    host = _host(qapp)
    center = NotificationCenter(host, lambda: 50)
    first = center.push(Notification("Первое"))
    second = center.push(Notification("Второе", "текст"))
    assert center.notifications == [second, first]
    assert second.y() == 50
    assert first.y() > second.y() + second.height() - 2 * Notification.M
    assert second.geometry().right() <= host.width()
    assert second.x() + second.width() >= host.width() - NotificationCenter.RIGHT - 1


def test_max_visible_and_dismiss_removes(qapp):
    host = _host(qapp)
    center = NotificationCenter(host)
    items = [center.push(Notification(str(i))) for i in range(6)]
    assert len(center.notifications) == NotificationCenter.MAX_VISIBLE
    top = items[-1]
    top._finish()  # конец анимации исчезновения
    QApplication.processEvents()
    assert top not in center.notifications


def test_download_notification_goes_from_progress_to_done(qapp):
    track = YandexTrack(track_id="1", title="Песня", author="Группа")
    toast = DownloadNotification(track)
    assert toast._title.text() == "Скачивание…"
    assert toast._message.text() == "Группа — Песня"
    assert toast._has_progress and toast.progress is None  # бегущая полоска
    toast.set_fraction(0.42)
    assert toast.progress == 0.42
    assert toast._percent.text() == "42%"
    toast.finish(True)
    assert toast.kind == "success"
    assert toast._title.text() == "Трек скачан"
    assert not toast._has_progress
    toast.set_fraction(0.9)  # поздний прогресс после итога не возвращает полоску
    assert not toast._has_progress


def test_download_notification_finished_failure(qapp):
    track = YandexTrack(track_id="1", title="Песня", author="Группа")
    failed = DownloadNotification.finished(track, False)
    assert failed.kind == "error"
    assert failed._title.text() == "Не удалось скачать"


def test_progress_grows_card_and_restacks(qapp):
    host = _host(qapp)
    center = NotificationCenter(host)
    lower = center.push(Notification("Нижнее"))
    upper = center.push(Notification("Верхнее"))
    before = lower.y()
    upper.set_progress(0.5)
    QApplication.processEvents()
    assert lower.y() > before


def test_plugin_host_notify_from_thread_arrives_in_main_thread(qapp):
    import threading

    from PySide6.QtCore import QObject, QThread

    from quantis.core.plugin_host import PluginHost
    from quantis.plugins.event_bus import EventBus

    bus = EventBus()
    host = PluginHost(event_bus=bus, playback=None, music=None)
    got: list[tuple] = []

    class Receiver(QObject):
        def on(self, title, message, kind):
            got.append((title, message, kind, QThread.currentThread()))

    receiver = Receiver()
    bus.notification_requested.connect(receiver.on)
    worker = threading.Thread(target=lambda: host.notify("T", "m", "weird"))
    worker.start()
    worker.join()
    for _ in range(50):
        qapp.processEvents()
        if got:
            break
    assert got and got[0][:3] == ("T", "m", "info")  # неизвестный kind → info
    assert got[0][3] is qapp.thread()


def test_notification_exposes_title(qapp):
    item = Notification("Discord", "текст")
    assert item.title == "Discord"
    assert item.message == "текст"
