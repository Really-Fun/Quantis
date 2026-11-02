"""Миграция старых файлов: теги и имя «Исполнитель - Название»."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import pytest_asyncio

import quantis.models  # noqa: F401  (порядок импорта: циклическая зависимость)
from quantis.providers.library_index import LibraryIndex
from quantis.providers.path_provider import PathProvider
from quantis.services import async_downloader as ad
from quantis.services.async_downloader import AsyncDownloader
from quantis.services.library_retag import RetagReport, retag_legacy
from quantis.services.track_tags import TrackMeta, read_identity, write_tags

pytestmark = pytest.mark.asyncio

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture
def music(tmp_path, monkeypatch):
    folder = tmp_path / "music"
    folder.mkdir()
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(folder))
    return folder


@pytest_asyncio.fixture
async def index(music, tmp_path):
    return LibraryIndex(music_dir=music, cache_path=tmp_path / "idx.json")


class FakeDownloader(AsyncDownloader):
    """Метаданные берутся из словаря {(source, id): TrackMeta | Exception}."""

    def __init__(self, index, metas=None):
        super().__init__(index=index)
        self.metas = metas or {}
        self.fetched: list[tuple[str, str]] = []

    async def fetch_meta(self, track):
        key = (str(track.source), str(track.track_id))
        self.fetched.append(key)
        value = self.metas.get(key)
        if isinstance(value, Exception):
            raise value
        return value

    async def ensure_cover(self, track):
        return False


def legacy(music, name):
    path = music / name
    shutil.copy(FIXTURES / "silence.mp3", path)
    return path


def meta(source="yandex", track_id="42", title="Song", artist="A", album=""):
    return TrackMeta(
        source=source, track_id=track_id, title=title, artist=artist, album=album
    )


async def test_retag_legacy_file(music, index):
    legacy(music, "42_Song_A.mp3")
    dl = FakeDownloader(index, {("yandex", "42"): meta(album="X")})
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=1, already=0, skipped=0)
    assert not (music / "42_Song_A.mp3").exists()
    new = music / "A - Song.mp3"
    assert new.exists()
    from mutagen.id3 import ID3

    assert str(ID3(new)["TALB"]) == "X"
    assert read_identity(new).track_id == "42"
    assert index.path_for("yandex", "42") == new


async def test_already_tagged_untouched(music, index):
    path = legacy(music, "My edit.mp3")
    write_tags(path, meta(), None)
    before = path.stat().st_mtime_ns
    dl = FakeDownloader(index)
    report = await retag_legacy(dl, index)
    assert report.already == 1 and report.done == 0
    assert path.exists() and path.stat().st_mtime_ns == before
    assert dl.fetched == []


async def test_fetch_meta_failure_uses_local_data(music, index):
    legacy(music, "42_Song_A.mp3")
    dl = FakeDownloader(index, {("yandex", "42"): RuntimeError("net")})
    report = await retag_legacy(dl, index)
    assert report.done == 1
    new = music / "A - Song.mp3"
    ident = read_identity(new)
    assert (ident.title, ident.track_id) == ("Song", "42")


async def test_tag_write_failure_skips_without_rename(music, index, monkeypatch):
    legacy(music, "42_Song_A.mp3")

    def boom(*_a, **_k):
        raise RuntimeError("disk")

    monkeypatch.setattr(ad, "write_tags", boom)
    dl = FakeDownloader(index, {("yandex", "42"): meta()})
    report = await retag_legacy(dl, index)
    assert report.skipped == 1 and report.done == 0
    assert (music / "42_Song_A.mp3").exists()


async def test_progress_reported(music, index):
    for n in (1, 2, 3):
        legacy(music, f"{n}_S{n}_A.mp3")
    calls = []
    dl = FakeDownloader(index)
    await retag_legacy(dl, index, lambda i, t: calls.append((i, t)))
    assert calls == [(1, 3), (2, 3), (3, 3)]


async def test_second_run_is_noop(music, index):
    legacy(music, "42_Song_A.mp3")
    dl = FakeDownloader(index, {("yandex", "42"): meta()})
    first = await retag_legacy(dl, index)
    second = await retag_legacy(dl, index)
    assert second == RetagReport(done=0, already=first.done, skipped=0)


def _two_readings():
    from quantis.providers.legacy_names import parse_legacy_names

    name = "12345678_Ab_Song.mp3"
    return name, parse_legacy_names(name)


async def test_ambiguous_only_youtube_resolves(music, index):
    name, readings = _two_readings()
    assert len(readings) == 2
    yt = next(r for r in readings if r.source == "youtube")
    legacy(music, name)
    dl = FakeDownloader(
        index,
        {("youtube", yt.track_id): meta("youtube", yt.track_id, "Yt Title", "Chan")},
    )
    report = await retag_legacy(dl, index)
    assert report.done == 1
    new = music / "Chan - Yt Title.mp3"
    ident = read_identity(new)
    assert (ident.source, ident.track_id) == ("youtube", yt.track_id)


@pytest.mark.parametrize("both", [True, False])
async def test_ambiguous_both_or_neither_skipped(music, index, both):
    name, readings = _two_readings()
    legacy(music, name)
    metas = {}
    if both:
        for r in readings:
            metas[(r.source, r.track_id)] = meta(r.source, r.track_id, "T", "Z")
    dl = FakeDownloader(index, metas)
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    assert (music / name).exists()
    assert read_identity(music / name) is None


def _blocking_download(dl, music, created, release):
    async def fake_download(track):
        path = music / f"{track.track_id}_{track.title}_{track.author}.mp3"
        shutil.copy(FIXTURES / "silence.mp3", path)
        created.set()
        await release.wait()
        return ad.DownloadedAudio(
            path=path,
            meta=meta("yandex", str(track.track_id), track.title, track.author),
        )

    dl.download_track = fake_download


async def test_retag_skips_track_being_downloaded(music, index):
    import asyncio

    from quantis.models import YandexTrack

    await index.refresh()
    dl = FakeDownloader(index, {("yandex", "1"): meta(track_id="1", title="T")})
    created, release = asyncio.Event(), asyncio.Event()
    _blocking_download(dl, music, created, release)
    task = asyncio.ensure_future(
        dl.download_full(YandexTrack(track_id="1", title="T", author="A"))
    )
    await created.wait()
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    assert (music / "1_T_A.mp3").exists()
    assert read_identity(music / "1_T_A.mp3") is None
    release.set()
    assert await task is True
    assert (music / "A - T.mp3").exists()
    assert not (music / "1_T_A.mp3").exists()


async def test_download_waits_for_retag_of_same_track(music, index):
    import asyncio

    from quantis.models import YandexTrack

    legacy(music, "1_T_A.mp3")
    await index.refresh()
    gate = asyncio.Event()
    entered = asyncio.Event()
    dl = FakeDownloader(index)
    downloads = []

    async def slow_fetch(track):
        entered.set()
        await gate.wait()
        return meta(track_id="1", title="T")

    async def fake_download(track):
        downloads.append(track.track_id)
        return None

    dl.fetch_meta = slow_fetch
    dl.download_track = fake_download
    retag = asyncio.ensure_future(retag_legacy(dl, index))
    await entered.wait()
    full = asyncio.ensure_future(
        dl.download_full(YandexTrack(track_id="1", title="T", author="A"))
    )
    await asyncio.sleep(0.05)
    assert downloads == [] and not full.done()
    gate.set()
    report = await retag
    assert report.done == 1
    # После миграции файл уже есть в индексе: повторного скачивания нет.
    assert await full is True
    assert downloads == []
    assert (music / "A - T.mp3").exists()
