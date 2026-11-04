"""Конвейер download_full: скачать, обложка, теги, имя, индекс."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest
import pytest_asyncio

import quantis.models  # noqa: F401  (порядок импорта: циклическая зависимость)
from quantis.models import YandexTrack
from quantis.providers.library_index import LibraryIndex
from quantis.providers.path_provider import PathProvider
from quantis.services import async_downloader as ad
from quantis.services.async_downloader import AsyncDownloader, DownloadedAudio
from quantis.services.track_tags import TrackMeta, read_identity, write_tags

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture
def music(tmp_path, monkeypatch):
    folder = tmp_path / "music"
    folder.mkdir()
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(folder))
    return folder


@pytest_asyncio.fixture
async def index(music, tmp_path):
    idx = LibraryIndex(music_dir=music, cache_path=tmp_path / "idx.json")
    await idx.refresh()
    return idx


def make_track(track_id="1", title="T", author="A") -> YandexTrack:
    return YandexTrack(track_id=track_id, title=title, author=author)


def make_downloader(index, music, calls=None, delay=0.0):
    dl = AsyncDownloader(index=index)

    async def fake_download(track):
        if calls is not None:
            calls.append(track.track_id)
        if delay:
            await asyncio.sleep(delay)
        path = music / f"{track.track_id}_{track.title}_{track.author}.mp3"
        shutil.copy(FIXTURES / "silence.mp3", path)
        meta = TrackMeta(
            source="yandex",
            track_id=str(track.track_id),
            title=track.title,
            artist=track.author,
        )
        return DownloadedAudio(path=path, meta=meta)

    async def no_cover(track):
        return False

    dl.download_track = fake_download
    dl.ensure_cover = no_cover
    return dl


@pytest.mark.asyncio
async def test_full_pipeline_tags_and_renames(index, music):
    dl = make_downloader(index, music)
    track = make_track()
    assert await dl.download_full(track) is True
    target = music / "A - T.mp3"
    assert target.is_file()
    assert not (music / "1_T_A.mp3").exists()
    ident = read_identity(target)
    assert (ident.source, ident.track_id) == ("yandex", "1")
    assert index.path_for("yandex", "1") == target
    assert track.downloaded is True


@pytest.mark.asyncio
async def test_tag_failure_keeps_legacy_name_and_succeeds(index, music, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("no tags")

    monkeypatch.setattr(ad, "write_tags", boom)
    dl = make_downloader(index, music)
    track = make_track()
    assert await dl.download_full(track) is True
    legacy = music / "1_T_A.mp3"
    assert legacy.is_file()
    assert not (music / "A - T.mp3").exists()
    assert index.has("yandex", "1")
    assert track.downloaded is True


@pytest.mark.asyncio
async def test_tag_verification_mismatch_keeps_name(index, music, monkeypatch):
    monkeypatch.setattr(ad, "read_identity", lambda path: None)
    dl = make_downloader(index, music)
    assert await dl.download_full(make_track()) is True
    assert (music / "1_T_A.mp3").is_file()
    assert not (music / "A - T.mp3").exists()


@pytest.mark.asyncio
async def test_cover_missing_still_tags(index, music):
    dl = make_downloader(index, music)
    captured = []
    real = ad.write_tags

    def spy(path, meta, cover):
        captured.append(cover)
        real(path, meta, cover)

    ad.write_tags = spy
    try:
        assert await dl.download_full(make_track()) is True
    finally:
        ad.write_tags = real
    assert captured == [None]
    assert read_identity(music / "A - T.mp3") is not None


@pytest.mark.asyncio
async def test_existing_tagged_file_untouched(index, music):
    mine = music / "My name.mp3"
    shutil.copy(FIXTURES / "silence.mp3", mine)
    write_tags(
        mine, TrackMeta(source="yandex", track_id="1", title="T", artist="A"), None
    )
    os.utime(mine, (1_000_000, 1_000_000))
    await index.refresh()
    calls: list = []
    dl = make_downloader(index, music, calls)
    track = make_track()
    assert await dl.download_full(track) is True
    assert calls == []
    assert track.downloaded is True
    assert mine.stat().st_mtime == 1_000_000
    assert [p.name for p in music.iterdir()] == ["My name.mp3"]


@pytest.mark.asyncio
async def test_download_failure_returns_false(index, music):
    dl = make_downloader(index, music)

    async def fail(track):
        return None

    dl.download_track = fail
    track = make_track()
    assert await dl.download_full(track) is False
    assert track.downloaded is False


@pytest.mark.asyncio
async def test_concurrent_calls_single_file(index, music):
    calls: list = []
    dl = make_downloader(index, music, calls, delay=0.05)
    track = make_track()
    results = await asyncio.gather(dl.download_full(track), dl.download_full(track))
    assert results == [True, True]
    assert calls == ["1"]
    assert sorted(p.name for p in music.iterdir()) == ["A - T.mp3"]


@pytest.mark.asyncio
async def test_same_name_different_tracks_get_suffix(index, music):
    dl = make_downloader(index, music, delay=0.01)
    t1 = make_track("1")
    t2 = make_track("2")
    results = await asyncio.gather(dl.download_full(t1), dl.download_full(t2))
    assert results == [True, True]
    assert sorted(p.name for p in music.iterdir()) == ["A - T (2).mp3", "A - T.mp3"]
    assert index.path_for("yandex", "1") != index.path_for("yandex", "2")


@pytest.mark.asyncio
async def test_index_failure_does_not_fail_download(index, music, monkeypatch):
    def boom(path):
        raise RuntimeError("index")

    monkeypatch.setattr(index, "put", boom)
    dl = make_downloader(index, music)
    track = make_track()
    assert await dl.download_full(track) is True
    assert track.downloaded is True


@pytest.mark.asyncio
async def test_waits_for_index_ready(music, tmp_path):
    idx = LibraryIndex(music_dir=music, cache_path=tmp_path / "idx.json")
    calls: list = []
    dl = make_downloader(idx, music, calls)
    task = asyncio.ensure_future(dl.download_full(make_track()))
    await asyncio.sleep(0.05)
    assert calls == []
    await idx.refresh()
    assert await task is True
    assert calls == ["1"]


@pytest.mark.asyncio
async def test_cover_error_still_succeeds(index, music):
    dl = make_downloader(index, music)

    async def boom(track):
        raise asyncio.TimeoutError

    dl.ensure_cover = boom
    assert await dl.download_full(make_track()) is True
    assert read_identity(music / "A - T.mp3") is not None
    assert index.path_for("yandex", "1") == music / "A - T.mp3"


@pytest.mark.asyncio
async def test_cover_error_on_shortcut_path(index, music):
    mine = music / "My name.mp3"
    shutil.copy(FIXTURES / "silence.mp3", mine)
    write_tags(
        mine, TrackMeta(source="yandex", track_id="1", title="T", artist="A"), None
    )
    await index.refresh()
    dl = make_downloader(index, music)

    async def boom(track):
        raise OSError("disk")

    dl.ensure_cover = boom
    track = make_track()
    assert await dl.download_full(track) is True
    assert track.downloaded is True


@pytest.mark.asyncio
async def test_cover_present_passed_to_write_tags(index, music, monkeypatch):
    dl = make_downloader(index, music)

    async def has_cover(track):
        return True

    dl.ensure_cover = has_cover
    captured = []

    def spy(path, meta, cover):
        captured.append(cover)

    monkeypatch.setattr(ad, "write_tags", spy)
    await dl.download_full(make_track())
    assert captured == [Path(PathProvider().get_cover_path(make_track()))]


@pytest.mark.asyncio
async def test_stale_index_does_not_overwrite_own_tagged_file(index, music):
    own = music / "A - T.mp3"
    shutil.copy(FIXTURES / "silence.mp3", own)
    write_tags(
        own, TrackMeta(source="yandex", track_id="1", title="T", artist="A"), None
    )
    os.utime(own, (1_000_000, 1_000_000))
    before = own.read_bytes()
    assert not index.has("yandex", "1")
    dl = make_downloader(index, music)
    assert await dl.download_full(make_track()) is True
    assert own.read_bytes() == before
    assert own.stat().st_mtime == 1_000_000
    assert sorted(p.name for p in music.iterdir()) == ["A - T.mp3"]
    assert index.path_for("yandex", "1") == own


@pytest.mark.asyncio
async def test_empty_title_readback_blocks_rename(index, music, monkeypatch):
    real = ad.read_identity

    def empty_title(path):
        ident = real(path)
        return ident and type(ident)(ident.source, ident.track_id, "", ident.artist)

    monkeypatch.setattr(ad, "read_identity", empty_title)
    dl = make_downloader(index, music)
    assert await dl.download_full(make_track()) is True
    assert (music / "1_T_A.mp3").is_file()
    assert not (music / "A - T.mp3").exists()


@pytest.mark.asyncio
async def test_soundcloud_ids_with_and_without_prefix_dedupe(index, music):
    from quantis.models.track import SoundCloudTrack

    dl = AsyncDownloader(index=index)
    calls: list = []
    gate = asyncio.Event()

    async def slow_download(track):
        calls.append(track.track_id)
        await gate.wait()
        return None

    dl.download_track = slow_download
    first = asyncio.ensure_future(
        dl.download_full(SoundCloudTrack(track_id="sc123", title="T", author="A"))
    )
    await asyncio.sleep(0.01)
    second = asyncio.ensure_future(
        dl.download_full(SoundCloudTrack(track_id="123", title="T", author="A"))
    )
    await asyncio.sleep(0.01)
    assert dl.is_downloading("soundcloud", "123")
    assert dl.is_downloading("soundcloud", "sc123")
    gate.set()
    assert await asyncio.gather(first, second) == [False, False]
    assert calls == ["sc123"]


@pytest.mark.parametrize(
    ("source", "track_id"),
    [
        ("soundcloud", "sc123"),
        ("SoundCloud", "sc123"),
        ("SoundCloud", "123"),
        ("YANDEX", "42"),
        ("youtube", "scAbCdEfGhI"),
    ],
)
def test_download_guard_and_index_share_one_key(source, track_id):
    """Замок скачивания и индекс должны считать одни и те же id одним треком."""
    from quantis.providers.library_index import track_key

    s, t = track_key(source, track_id)
    assert AsyncDownloader._guard_key(source, track_id) == f"{s}:{t}"


@pytest.mark.asyncio
async def test_rename_failure_still_succeeds(index, music, monkeypatch):
    real_replace = Path.replace

    def locked(self, target):
        if self.suffix == ".mp3":
            raise PermissionError("file in use")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", locked)
    dl = make_downloader(index, music)
    track = make_track()
    assert await dl.download_full(track) is True
    assert track.downloaded is True
    path = music / "1_T_A.mp3"
    assert read_identity(path).track_id == "1"
    assert index.path_for("yandex", "1") == path


@pytest.mark.asyncio
async def test_tag_and_rename_reports_rename_failure(index, music, monkeypatch):
    real_replace = Path.replace
    path = music / "1_T_A.mp3"
    shutil.copy(FIXTURES / "silence.mp3", path)
    dl = make_downloader(index, music)
    meta = TrackMeta(source="yandex", track_id="1", title="T", artist="A")

    def locked(self, target):
        if self.suffix == ".mp3":
            raise PermissionError("file in use")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", locked)
    outcome = await dl.tag_and_rename(path, meta, make_track())
    assert outcome.verified and not outcome.renamed and not outcome.complete
    assert outcome.path == path
    monkeypatch.setattr(Path, "replace", real_replace)
    outcome = await dl.tag_and_rename(path, meta, make_track())
    assert outcome.complete and outcome.path == music / "A - T.mp3"
