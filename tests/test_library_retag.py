"""Миграция старых файлов: теги и имя «Исполнитель - Название»."""

from __future__ import annotations

import dataclasses
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
    """lookup_meta из словаря {(source, id): TrackMeta | Exception}."""

    def __init__(self, index, metas=None):
        super().__init__(index=index)
        self.metas = metas or {}
        self.fetched: list[tuple[str, str]] = []

    async def lookup_meta(self, track):
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


async def test_fetch_meta_error_skips_file(music, index):
    # Сбой сервиса — не «трека нет»: следующий запуск должен повторить.
    legacy(music, "42_Song_A.mp3")
    dl = FakeDownloader(index, {("yandex", "42"): RuntimeError("net")})
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    assert (music / "42_Song_A.mp3").exists()
    assert read_identity(music / "42_Song_A.mp3") is None


async def test_not_found_uses_local_data(music, index):
    legacy(music, "42_Song_A.mp3")
    dl = FakeDownloader(index)  # чистое «нет такого трека»
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
        # Название сервиса должно совпасть с именем: у YouTube-прочтения это «Song».
        {("youtube", yt.track_id): meta("youtube", yt.track_id, "Song", "Chan")},
    )
    report = await retag_legacy(dl, index)
    assert report.done == 1
    new = music / "Chan - Song.mp3"
    ident = read_identity(new)
    assert (ident.source, ident.track_id) == ("youtube", yt.track_id)


@pytest.mark.parametrize("both", [True, False])
async def test_ambiguous_both_or_neither_skipped(music, index, both):
    name, readings = _two_readings()
    legacy(music, name)
    metas = {}
    if both:
        # Оба прочтения совпадают с именем по названию: выбрать нельзя.
        titles = {"yandex": "Ab", "youtube": "Song"}
        for r in readings:
            metas[(r.source, r.track_id)] = meta(
                r.source, r.track_id, titles[r.source], "Z"
            )
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

    dl.lookup_meta = slow_fetch
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


# --- значения сервиса вместо искажённого имени ---


async def test_retag_uses_service_title_and_artist(music, index):
    legacy(music, "123_Who Are You__AC_DC.mp3")
    dl = FakeDownloader(
        index, {("yandex", "123"): meta("yandex", "123", "Who Are You?", "AC/DC")}
    )
    report = await retag_legacy(dl, index)
    assert report.done == 1
    expected = PathProvider().human_track_path(
        "AC/DC", "Who Are You?", "mp3", owner=("yandex", "123")
    )
    assert expected.name == "AC_DC - Who Are You_.mp3"
    assert expected.exists() and not (music / "123_Who Are You__AC_DC.mp3").exists()
    from mutagen.id3 import ID3

    tags = ID3(expected)
    assert (str(tags["TIT2"]), str(tags["TPE1"])) == ("Who Are You?", "AC/DC")


async def test_retag_real_yandex_lookup_uses_service_names(music, index):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    legacy(music, "123_Who Are You__AC_DC.mp3")
    dl = AsyncDownloader(index=index)

    async def no_cover(_track):
        return False

    dl.ensure_cover = no_cover
    ya = SimpleNamespace(
        title="Who Are You?", artists=[SimpleNamespace(name="AC/DC")], albums=[]
    )
    yandex = dl._yandex_downloader
    yandex._client = SimpleNamespace(token="t", tracks=AsyncMock(return_value=[ya]))
    yandex._client_ready = True
    report = await retag_legacy(dl, index)
    assert report.done == 1
    ident = read_identity(music / "AC_DC - Who Are You_.mp3")
    assert ident.title == "Who Are You?"


async def test_fallback_meta_strips_and_cleans_youtube_author(music):
    from quantis.providers.library_index import IndexEntry
    from quantis.services.library_retag import _fallback_meta

    yt = IndexEntry(
        path=music / "x.m4a",
        source="youtube",
        track_id="dQw4w9WgXcQ",
        title=" Song ",
        author=" Chan • 1,2 млн просмотров",
        tagged=False,
    )
    m = _fallback_meta(yt)
    assert (m.title, m.artist) == ("Song", "Chan")
    ya = dataclasses.replace(yt, source="yandex", track_id="5", author=" A ")
    assert (_fallback_meta(ya).title, _fallback_meta(ya).artist) == ("Song", "A")


# --- неоднозначные имена: только проверенный ответ сервиса ---


async def test_ambiguous_youtube_error_skips_even_if_yandex_hits(music, index):
    name, readings = _two_readings()
    ya = next(r for r in readings if r.source == "yandex")
    yt = next(r for r in readings if r.source == "youtube")
    legacy(music, name)
    dl = FakeDownloader(
        index,
        {
            # Яндекс отдаёт трек с тем же названием, но YouTube недоступен.
            ("yandex", ya.track_id): meta("yandex", ya.track_id, "Ab", "Song"),
            ("youtube", yt.track_id): RuntimeError("network down"),
        },
    )
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    assert (music / name).exists() and read_identity(music / name) is None


async def test_ambiguous_title_mismatch_not_accepted(music, index):
    name, readings = _two_readings()
    ya = next(r for r in readings if r.source == "yandex")
    legacy(music, name)
    dl = FakeDownloader(
        index, {("yandex", ya.track_id): meta("yandex", ya.track_id, "Other", "Z")}
    )
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    assert (music / name).exists() and read_identity(music / name) is None


async def test_ambiguous_single_matching_hit_tagged(music, index):
    name, readings = _two_readings()
    ya = next(r for r in readings if r.source == "yandex")
    yt = next(r for r in readings if r.source == "youtube")
    legacy(music, name)
    dl = FakeDownloader(
        index,
        {
            # Совпадает с названием в имени после санитизации и casefold.
            ("yandex", ya.track_id): meta("yandex", ya.track_id, "AB", "Song"),
            ("youtube", yt.track_id): meta("youtube", yt.track_id, "Zzz", "Chan"),
        },
    )
    report = await retag_legacy(dl, index)
    assert report.done == 1
    ident = read_identity(music / "Song - AB.mp3")
    assert (ident.source, ident.track_id) == ("yandex", ya.track_id)


async def test_title_match_uses_legacy_sanitising():
    from quantis.services.library_retag import _title_matches

    assert _title_matches("What? Why", "What_ Why_Artist")
    assert _title_matches("what? why", "What_ Why")
    assert _title_matches("AC/DC.", "AC_DC_X")
    assert not _title_matches("Other", "What_ Why_Artist")
    assert not _title_matches("", "unknown_A")


# --- лимит Яндекса и сбой переименования ---


async def test_yandex_rate_limited_twice_then_full_meta(music, index, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(ad, "_backoff_sleep", no_sleep)
    legacy(music, "42_Song_A.mp3")
    dl = AsyncDownloader(index=index)

    async def no_cover(_track):
        return False

    dl.ensure_cover = no_cover
    album = SimpleNamespace(
        title="Alb", year=2001, genre="rock", track_position=None, artists=[]
    )
    ya = SimpleNamespace(
        title="Song!", artists=[SimpleNamespace(name="A")], albums=[album]
    )
    tracks = AsyncMock(side_effect=[RuntimeError("(429)"), RuntimeError("(429)"), [ya]])
    yandex = dl._yandex_downloader
    yandex._client = SimpleNamespace(token="t", tracks=tracks)
    yandex._client_ready = True
    report = await retag_legacy(dl, index)
    assert report.done == 1
    from mutagen.id3 import ID3

    tags = ID3(music / "A - Song!.mp3")
    assert str(tags["TALB"]) == "Alb" and str(tags["TIT2"]) == "Song!"


async def test_yandex_rate_limited_persistently_skips(music, index, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(ad, "_backoff_sleep", no_sleep)
    legacy(music, "42_Song_A.mp3")
    dl = AsyncDownloader(index=index)
    yandex = dl._yandex_downloader
    yandex._client = SimpleNamespace(
        token="t", tracks=AsyncMock(side_effect=RuntimeError("Concurrency limit"))
    )
    yandex._client_ready = True
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    assert (music / "42_Song_A.mp3").exists()
    assert read_identity(music / "42_Song_A.mp3") is None


async def test_rename_failure_counts_as_skipped(music, index, monkeypatch):
    legacy(music, "42_Song_A.mp3")
    real_replace = Path.replace

    def locked(self, target):
        if self.suffix == ".mp3":
            raise PermissionError("file in use")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", locked)
    dl = FakeDownloader(index, {("yandex", "42"): meta()})
    report = await retag_legacy(dl, index)
    assert report == RetagReport(done=0, already=0, skipped=1)
    # Теги записаны и проверены, имя осталось старым.
    assert read_identity(music / "42_Song_A.mp3").track_id == "42"
