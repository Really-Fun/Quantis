from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QLabel, QSlider, QToolButton

from quantis.models.repeat_mode import RepeatMode
from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.ui.preferences import UiPreferences
from quantis.ui.ui_extensions import PlayerActionExtension, UiExtensionHost
from quantis.ui.views import player_bar
from quantis.ui.views.player_bar import PlayerBar
from quantis.ui.views.widgets.waveform_seek import WaveformSeekSlider


class _FakeVM(QObject):
    track_changed = Signal(object)
    is_playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    volume_changed = Signal(int)
    repeat_mode_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.repeat_mode = RepeatMode.PLAYLIST
        self.calls: list[tuple] = []

    def __getattr__(self, name: str):
        if name in {
            "toggle_pause",
            "play_next",
            "play_previous",
            "cycle_repeat_mode",
            "set_volume",
            "seek",
            "sync_from_player",
        }:
            return lambda *args: self.calls.append((name, *args))
        raise AttributeError(name)


class _SyncBridge:
    """Корутины и колбэки — сразу, в этом же потоке."""

    def schedule(self, coro) -> None:
        asyncio.run(coro)

    def invoke_main(self, callback) -> None:
        callback()


class _QueuedBridge(_SyncBridge):
    """Корутины ждут, пока тест не запустит их сам — в нужном порядке."""

    def __init__(self) -> None:
        self.pending: list = []

    def schedule(self, coro) -> None:
        self.pending.append(coro)

    def run(self, coros) -> None:
        for coro in coros:
            asyncio.run(coro)


class _FakeDownloader:
    def __init__(self) -> None:
        self.downloaded: list[Track] = []

    async def ensure_covers(self, tracks, limit: int = 40) -> int:
        return 0

    async def download_track(self, track: Track) -> None:
        self.downloaded.append(track)

    async def download_cover(self, track: Track) -> None:
        pass


class _FakeMusic:
    def __init__(self) -> None:
        self.downloader = _FakeDownloader()


class _FakeLiked:
    liked: set[str] = set()

    async def is_liked(self, track: Track) -> bool:
        return repr(track) in self.liked

    async def toggle(self, track: Track) -> bool:
        key = repr(track)
        if key in self.liked:
            self.liked.discard(key)
            return False
        self.liked.add(key)
        return True


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(tmp_path / "music"))
    monkeypatch.setattr(PathProvider, "COVERS_FOLDER", str(tmp_path / "covers"))
    monkeypatch.setattr(PathProvider, "PLAYLISTS_FOLDER", str(tmp_path / "pl"))
    monkeypatch.setattr(player_bar, "LikedTracksService", _FakeLiked)
    _FakeLiked.liked = set()
    return PathProvider()


def _track(track_id: str = "1", **kwargs) -> Track:
    fields = {"title": "Song", "author": "Band", "source": "yandex"} | kwargs
    return Track(track_id=track_id, **fields)


def _button(bar: PlayerBar, *tooltips: str) -> QToolButton:
    found = [b for b in bar.findChildren(QToolButton) if b.toolTip() in tooltips]
    assert len(found) == 1, tooltips
    return found[0]


def _label(bar: PlayerBar, name: str) -> QLabel:
    return bar.findChild(QLabel, name)


def _volume(bar: PlayerBar) -> QSlider:
    return bar.findChild(QSlider, "volSlider")


def _seek(bar: PlayerBar) -> WaveformSeekSlider:
    return bar.findChild(WaveformSeekSlider)


def _cover_center(bar: PlayerBar) -> QColor:
    image = bar.findChild(QLabel, "coverLabel").grab().toImage()
    return image.pixelColor(image.width() // 2, image.height() // 2)


def _is_red(color: QColor) -> bool:
    return color.red() > 200 and color.green() < 60 and color.blue() < 60


def _like(bar: PlayerBar) -> QToolButton:
    return _button(bar, "В любимые", "Убрать из любимых")


def test_initial_state_restores_volume(qapp, storage) -> None:
    UiPreferences().set_volume(37)
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    assert _volume(bar).value() == 37
    assert ("set_volume", 37) in vm.calls
    assert vm.calls[-1] == ("sync_from_player",)
    assert _label(bar, "trackTitle").fullText() == "Ничего не играет"
    assert not _like(bar).isEnabled()
    assert not _button(bar, "В плейлист").isEnabled()
    assert not _button(bar, "Скачать").isEnabled()


def test_track_change_fills_meta(qapp, storage) -> None:
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    vm.track_changed.emit(_track(author=""))
    assert _label(bar, "trackTitle").fullText() == "Song"
    assert _label(bar, "trackArtist").isHidden()
    assert _like(bar).isEnabled()
    assert _button(bar, "В плейлист").isEnabled()
    assert _button(bar, "Скачать").isEnabled()

    vm.track_changed.emit(_track("2", downloaded=True))
    assert not _label(bar, "trackArtist").isHidden()
    assert _label(bar, "trackArtist").fullText() == "Band"
    assert not _button(bar, "Скачать").isEnabled()


def test_transport_buttons_drive_view_model(qapp, storage) -> None:
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    vm.calls.clear()
    for tooltip in ("Назад", "Play", "Далее", "Повтор плейлиста"):
        _button(bar, tooltip).click()
    assert vm.calls == [
        ("play_previous",),
        ("toggle_pause",),
        ("play_next",),
        ("cycle_repeat_mode",),
    ]


def test_repeat_mode_updates_button(qapp, storage) -> None:
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    repeat = bar.findChild(QToolButton, "repeatButton")
    assert repeat.property("repeatMode") == "playlist"
    assert repeat.property("state") == "active"
    vm.repeat_mode_changed.emit(RepeatMode.TRACK)
    assert repeat.property("repeatMode") == "track"
    assert repeat.toolTip() == "Повтор трека"
    vm.repeat_mode_changed.emit(RepeatMode.PLAYLIST)
    assert repeat.property("repeatMode") == "playlist"
    assert repeat.toolTip() == "Повтор плейлиста"


def test_volume_sync_does_not_echo(qapp, storage) -> None:
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    vm.calls.clear()
    vm.volume_changed.emit(64)
    assert _volume(bar).value() == 64
    assert vm.calls == []
    _volume(bar).setValue(20)
    assert vm.calls == [("set_volume", 20)]


def test_timeline_and_seek(qapp, storage) -> None:
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    seek = _seek(bar)
    vm.duration_changed.emit(180_000)
    vm.position_changed.emit(61_000)
    labels = [lbl.text() for lbl in bar.findChildren(QLabel, "timeLabel")]
    assert labels == ["1:01", "3:00"]
    assert seek.maximum() == 180_000
    assert seek.value() == 61_000

    seek.sliderPressed.emit()
    vm.position_changed.emit(90_000)
    assert seek.value() == 61_000  # пока тянут — головку не дёргаем
    seek.setValue(120_000)
    vm.calls.clear()
    seek.sliderReleased.emit()
    assert vm.calls == [("seek", 120_000)]


def test_playing_marks_title(qapp, storage) -> None:
    vm = _FakeVM()
    bar = PlayerBar(vm, storage)
    vm.is_playing_changed.emit(True)
    assert _label(bar, "trackTitle").property("playing") is True
    vm.is_playing_changed.emit(False)
    assert _label(bar, "trackTitle").property("playing") is False


def test_like_toggle(qapp, storage) -> None:
    changed: list[bool] = []
    vm = _FakeVM()
    bar = PlayerBar(
        vm,
        storage,
        bridge=_SyncBridge(),
        music=_FakeMusic(),
        on_liked_changed=lambda: changed.append(True),
    )
    _FakeLiked.liked = {"yandex:2"}
    vm.track_changed.emit(_track("2"))
    assert _like(bar).property("liked") is True
    assert _like(bar).toolTip() == "Убрать из любимых"

    _like(bar).click()
    assert _like(bar).property("liked") is False
    assert _like(bar).toolTip() == "В любимые"
    assert changed == [True]

    bar.toggle_like()  # горячая клавиша L
    assert _like(bar).property("liked") is True
    assert changed == [True, True]


def test_late_results_for_previous_track_are_ignored(qapp, storage) -> None:
    old, new = _track("old"), _track("new")
    cover_path = Path(storage.get_cover_path(old))
    cover_path.parent.mkdir(parents=True)
    red = QImage(128, 128, QImage.Format.Format_RGB32)
    noise = random.Random(1)
    for x in range(128):  # красный центр, вокруг шум: меньше 3500 байт — заглушка
        for y in range(128):
            rgb = (255, 0, 0) if 32 <= x < 96 and 32 <= y < 96 else noise.randbytes(3)
            red.setPixelColor(x, y, QColor(*rgb))
    red.save(str(cover_path))
    _FakeLiked.liked = {repr(old)}
    vm = _FakeVM()
    bridge = _QueuedBridge()
    bar = PlayerBar(vm, storage, bridge=bridge, music=_FakeMusic())
    vm.track_changed.emit(old)
    assert _is_red(_cover_center(bar))
    vm.track_changed.emit(new)
    old_jobs, new_jobs = bridge.pending[:2], bridge.pending[2:]
    bridge.run(new_jobs + old_jobs)  # ответы про old пришли последними

    assert _like(bar).property("liked") is False
    assert not _is_red(_cover_center(bar))  # не обложка old


def test_download_click(qapp, storage) -> None:
    vm = _FakeVM()
    music = _FakeMusic()
    bar = PlayerBar(vm, storage, bridge=_SyncBridge(), music=music)
    track = _track("3")
    vm.track_changed.emit(track)
    _button(bar, "Скачать").click()
    assert music.downloader.downloaded == [track]
    assert track.downloaded is True
    assert not _button(bar, "Скачать").isEnabled()


def test_chrome_signals(qapp, storage) -> None:
    bar = PlayerBar(_FakeVM(), storage)
    fired: list[str] = []
    bar.now_playing_toggle_requested.connect(lambda: fired.append("now"))
    bar.hide_ui_requested.connect(lambda: fired.append("hide"))
    _button(bar, "Now Playing").click()
    _button(bar, "Скрыть интерфейс (S)").click()
    assert fired == ["now", "hide"]


def test_plugin_buttons_follow_extensions(qapp, storage) -> None:
    host = UiExtensionHost.instance()
    clicks: list[int] = []
    bar = PlayerBar(_FakeVM(), storage)
    try:
        host.register_player_action(
            PlayerActionExtension("t.act", "Тест", None, lambda: clicks.append(1))
        )
        _button(bar, "Тест · плагин").click()
        assert clicks == [1]
    finally:
        host.unregister_player_action("t.act")
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not [b for b in bar.findChildren(QToolButton) if b.property("plugin")]


@pytest.mark.parametrize(("width", "side"), [(900, 220), (1400, 300)])
def test_side_columns_shrink_on_narrow_window(qapp, storage, width, side) -> None:
    bar = PlayerBar(_FakeVM(), storage)
    bar.show()  # скрытому виджету resizeEvent придёт только при показе
    bar.resize(width, bar.height())
    left = bar.findChild(QLabel, "trackTitle").parentWidget()
    assert left.objectName() == "playerLeft"
    assert left.maximumWidth() == side
    assert _label(bar, "trackTitle").maximumWidth() == side - 56 - 12
    right = _button(bar, "Now Playing").parentWidget()
    assert right.objectName() == "playerRight"
    assert right.maximumWidth() >= side
    bar.close()


def test_theme_and_cinematic_render(qapp, storage) -> None:
    bar = PlayerBar(_FakeVM(), storage)
    bar.resize(1200, bar.height())
    bar.set_cinematic(True)
    assert not bar.grab().isNull()
    bar.set_cinematic(False)
    bar.refresh_theme()
    assert not bar.grab().isNull()
