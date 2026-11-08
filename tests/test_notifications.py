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


def test_download_notification_texts(qapp):
    track = YandexTrack(track_id="1", title="Песня", author="Группа")
    ok = DownloadNotification(track, True, cover_path=None)
    assert ok.kind == "success"
    assert ok._title.text() == "Трек скачан"
    assert ok._message.text() == "Группа — Песня"
    failed = DownloadNotification(track, False)
    assert failed.kind == "error"
    assert failed._title.text() == "Не удалось скачать"
