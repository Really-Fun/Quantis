"""Потребители индекса библиотеки: поиск файлов, «Скачанные», места скачивания."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import quantis.models  # noqa: F401  (порядок импорта: циклическая зависимость)
from quantis.models import SoundCloudTrack, YandexTrack, YoutubeTrack
from quantis.models.playlist import DownloadPlaylist
from quantis.providers import PathProvider, TrackManager
from quantis.providers.library_index import LibraryIndex
from quantis.services.track_tags import TrackMeta, write_tags

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
VID = "a_b-c_d_e_f"


def make_audio(folder: Path, name: str) -> Path:
    dst = folder / name
    shutil.copy(FIXTURES / ("silence" + dst.suffix), dst)
    return dst


def make_tagged(
    folder: Path,
    name: str,
    source: str = "youtube",
    track_id: str = VID,
    title: str = "Песня",
    artist: str = "Артист",
) -> Path:
    path = make_audio(folder, name)
    write_tags(
        path,
        TrackMeta(source=source, track_id=track_id, title=title, artist=artist),
        None,
    )
    return path


@pytest.fixture
def music(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "music"
    covers = tmp_path / "covers"
    folder.mkdir()
    covers.mkdir()
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(folder))
    monkeypatch.setattr(PathProvider, "COVERS_FOLDER", str(covers))
    return folder


def _refresh() -> LibraryIndex:
    index = LibraryIndex.instance()
    asyncio.run(index.refresh())
    return index


# --- TrackManager ---------------------------------------------------------


def test_is_downloaded_uses_index_for_human_named_file(music: Path) -> None:
    make_tagged(music, "Артист - Песня.mp3")
    _refresh()
    manager = TrackManager()
    assert manager.is_downloaded(VID, "youtube") is True
    # Источник известен — чужой источник с тем же id не считается.
    assert manager.is_downloaded(VID, "yandex") is False
    assert manager.is_downloaded("other", "youtube") is False


def test_is_downloaded_soundcloud_storage_id(music: Path) -> None:
    make_tagged(music, "SC - Трек.mp3", source="soundcloud", track_id="12345")
    _refresh()
    manager = TrackManager()
    assert manager.is_downloaded("12345", "soundcloud") is True
    assert manager.is_downloaded("sc12345", "soundcloud") is True
    assert manager.is_downloaded("12345", "yandex") is False


def test_is_downloaded_unknown_source_falls_back_to_any(music: Path) -> None:
    make_audio(music, "42_Song_A.mp3")
    _refresh()
    manager = TrackManager()
    assert manager.is_downloaded("42") is True
    assert manager.is_downloaded(42, "yandex") is True
    assert manager.is_downloaded("43") is False


def test_track_manager_still_accepts_music_dir(tmp_path: Path) -> None:
    manager = TrackManager(music_dir=tmp_path)
    assert manager.music_dir == tmp_path


def test_playlist_track_marked_downloaded_from_index(music: Path) -> None:
    make_tagged(music, "Артист - Песня.mp3")
    _refresh()
    track = TrackManager().get_track_from_playlist(
        VID, "Песня", "Артист", source="youtube"
    )
    assert isinstance(track, YoutubeTrack)
    assert track.downloaded is True


# --- PathProvider.find_track_file ----------------------------------------


def test_find_track_file_human_name(music: Path) -> None:
    path = make_tagged(
        music, "Artist - Song.mp3", source="yandex", track_id="42",
        title="Song", artist="Artist",
    )
    _refresh()
    track = YandexTrack(track_id=42, title="Song", author="Artist")
    assert PathProvider().find_track_file(track) == str(path)


def test_find_track_file_soundcloud_human_name(music: Path) -> None:
    path = make_tagged(music, "SC - Трек.mp3", source="soundcloud", track_id="777")
    _refresh()
    track = SoundCloudTrack(track_id="777", title="Трек", author="SC")
    assert PathProvider().find_track_file(track) == str(path)


# --- DownloadPlaylist ----------------------------------------------------


def test_delete_track_removes_human_named_file(music: Path) -> None:
    path = make_tagged(
        music, "Artist - Song.mp3", source="yandex", track_id="42",
        title="Song", artist="Artist",
    )
    legacy = make_audio(music, "42_Song_Artist.mp3")
    index = _refresh()
    track = YandexTrack(track_id=42, title="Song", author="Artist", downloaded=True)
    cover = Path(PathProvider().get_cover_path(track))
    cover.write_bytes(b"jpg")

    playlist = DownloadPlaylist(tracks=[track])
    assert playlist.delete_track(track) is True
    assert not path.exists()
    assert not legacy.exists()
    assert not cover.exists()
    assert track.downloaded is False
    assert index.has("yandex", "42") is False
    assert index.entries() == []


def test_downloaded_playlist_titles_from_tags(music: Path) -> None:
    # Имя файла ничего не говорит — название и автор берутся из тегов.
    make_tagged(music, "whatever.m4a", title="Из тегов", artist="Автор тегов")
    make_audio(music, "42_Song_A.mp3")
    make_tagged(music, "SC.mp3", source="soundcloud", track_id="9", title="Звук")
    _refresh()

    tracks = DownloadPlaylist.get_tracks_from_music_dir()
    by_source = {str(t.source): t for t in tracks}
    assert len(tracks) == 3

    yt = by_source["youtube"]
    assert isinstance(yt, YoutubeTrack)
    assert (yt.track_id, yt.title, yt.author) == (VID, "Из тегов", "Автор тегов")
    assert yt.extension == "m4a"
    assert yt.downloaded is True

    ya = by_source["yandex"]
    assert isinstance(ya, YandexTrack)
    assert (str(ya.track_id), ya.title, ya.author) == ("42", "Song", "A")

    sc = by_source["soundcloud"]
    assert isinstance(sc, SoundCloudTrack)
    assert (str(sc.track_id), sc.title, sc.extension) == ("9", "Звук", "mp3")


def test_downloaded_playlist_dedupes_one_track_two_files(music: Path) -> None:
    make_audio(music, "42_Old title_Artist.mp3")
    make_tagged(
        music, "Artist - Song.mp3", source="yandex", track_id="42",
        title="Song", artist="Artist",
    )
    _refresh()

    tracks = DownloadPlaylist.get_tracks_from_music_dir()
    assert len(tracks) == 1
    assert tracks[0].title == "Song"  # предпочитаем файл с тегами


def test_downloaded_playlist_empty_before_index(music: Path) -> None:
    make_audio(music, "42_Song_A.mp3")
    assert DownloadPlaylist.get_tracks_from_music_dir() == ()


# --- места скачивания: search / home ------------------------------------


class _SyncBridge:
    def __init__(self) -> None:
        self.scheduled: list = []

    def invoke_main(self, callback) -> None:
        callback()

    def schedule(self, coro) -> None:
        self.scheduled.append(coro)

    def close(self) -> None:
        for coro in self.scheduled:
            coro.close()


class _FullDownloader:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.calls: list = []

    async def download_full(self, track) -> bool:
        self.calls.append(track)
        if self.ok:
            track.downloaded = True
        return self.ok


def _playback(downloader: _FullDownloader) -> MagicMock:
    playback = MagicMock()
    playback.music.downloader = downloader
    return playback


@pytest.mark.asyncio
@pytest.mark.parametrize("ok", [True, False])
async def test_search_vm_marks_downloaded_only_on_success(qapp, ok: bool) -> None:
    from quantis.ui.viewmodels.search_vm import SearchViewModel

    bridge = _SyncBridge()
    downloader = _FullDownloader(ok)
    vm = SearchViewModel(MagicMock(), _playback(downloader), bridge)
    track = YandexTrack(track_id=7, title="T", author="A")
    vm.model.set_tracks([track])
    finished, errors, loading = [], [], []
    vm.download_finished.connect(lambda: finished.append(True))
    vm.error_occurred.connect(errors.append)
    vm.loading_changed.connect(loading.append)

    await vm.download_track_at(0)

    assert downloader.calls == [track]
    assert track.downloaded is ok
    assert bool(finished) is ok
    assert bool(errors) is (not ok)
    assert loading[-1] is False
    bridge.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ok", [True, False])
async def test_home_vm_marks_downloaded_only_on_success(qapp, ok: bool) -> None:
    from quantis.ui.viewmodels.home_vm import HomeViewModel

    bridge = _SyncBridge()
    downloader = _FullDownloader(ok)
    vm = HomeViewModel(MagicMock(), _playback(downloader), music=MagicMock())
    vm._bridge = bridge
    track = YandexTrack(track_id=8, title="T", author="A")
    vm.recent_model.set_tracks([track])
    errors, loading = [], []
    vm.error_occurred.connect(errors.append)
    vm.loading_changed.connect(loading.append)

    await vm.download_recent_at(0)

    assert downloader.calls == [track]
    assert track.downloaded is ok
    assert bool(errors) is (not ok)
    assert loading[-1] is False
    # «Скачанные» перечитываются только после успешной загрузки.
    assert bool(bridge.scheduled) is ok
    bridge.close()


# --- смена папки музыки в настройках -------------------------------------


@pytest.mark.parametrize("handler", ["pick", "reset"])
def test_settings_music_dir_change_resets_and_refreshes_index(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, handler: str
) -> None:
    from quantis.ui.preferences import UiPreferences
    from quantis.ui.views import settings_page
    from quantis.ui.views.settings_page import SettingsPage

    calls: list[str] = []
    index = MagicMock()
    index.reset.side_effect = lambda: calls.append("reset")

    async def refresh() -> None:
        calls.append("refresh-ran")

    index.refresh.side_effect = lambda: (calls.append("refresh"), refresh())[1]
    monkeypatch.setattr(LibraryIndex, "instance", classmethod(lambda cls: index))

    prefs = UiPreferences()
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    prefs.set_music_dir(str(old_dir))
    bridge = _SyncBridge()
    page = SettingsPage(prefs, bridge)
    try:
        if handler == "pick":
            monkeypatch.setattr(
                settings_page.QFileDialog,
                "getExistingDirectory",
                staticmethod(lambda *a, **k: str(new_dir)),
            )
            page._on_pick_music_dir()
        else:
            page._on_reset_music_dir()

        assert calls == ["reset", "refresh"]
        assert len(bridge.scheduled) == 1
        asyncio.run(bridge.scheduled.pop())
        assert calls == ["reset", "refresh", "refresh-ran"]
    finally:
        bridge.close()
        prefs.set_music_dir("")
        page.deleteLater()


def test_settings_same_music_dir_does_not_reset_index(
    qapp, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quantis.ui.preferences import UiPreferences
    from quantis.ui.views.settings_page import SettingsPage

    index = MagicMock()
    monkeypatch.setattr(LibraryIndex, "instance", classmethod(lambda cls: index))
    prefs = UiPreferences()
    prefs.set_music_dir("")
    bridge = _SyncBridge()
    page = SettingsPage(prefs, bridge)
    page._on_reset_music_dir()  # уже по умолчанию — папка не сменилась
    index.reset.assert_not_called()
    assert bridge.scheduled == []
    page.deleteLater()


@pytest.mark.parametrize("other_source", ["youtube", "yandex"])
def test_delete_track_keeps_other_tracks_file_with_same_prefix(
    music: Path, other_source: str
) -> None:
    # Человеческое имя чужого трека начинается с «42_» (исполнитель «42_Band»).
    foreign = make_tagged(
        music, "42_Band - Song.mp3", source=other_source,
        track_id=VID if other_source == "youtube" else "4242",
        title="Song", artist="42_Band",
    )
    legacy = make_audio(music, "42_Song_A.mp3")
    index = _refresh()
    track = YandexTrack(track_id=42, title="Song", author="A", downloaded=True)

    DownloadPlaylist(tracks=[track]).delete_track(track)

    assert not legacy.exists()
    assert foreign.exists()
    assert index.has(other_source, VID if other_source == "youtube" else "4242")


def test_delete_track_before_index_keeps_foreign_tagged_file(music: Path) -> None:
    foreign = make_tagged(
        music, "42_Band - Song.mp3", source="yandex", track_id="4242",
        title="Song", artist="42_Band",
    )
    legacy = make_audio(music, "42_Song_A.mp3")
    track = YandexTrack(track_id=42, title="Song", author="A", downloaded=True)

    DownloadPlaylist(tracks=[track]).delete_track(track)

    assert not legacy.exists()
    assert foreign.exists()


def test_find_track_file_fallback_skips_foreign_tagged_file(music: Path) -> None:
    make_tagged(
        music, "42_Band - Song.mp3", source="yandex", track_id="4242",
        title="Song", artist="42_Band",
    )
    track = YandexTrack(track_id=42, title="Song", author="A")
    assert PathProvider().find_track_file(track) is None
