"""Индекс скачанных файлов: теги, старые имена, кэш."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import quantis.models  # noqa: F401  (порядок импорта: циклическая зависимость)
from quantis.providers import library_index as li
from quantis.providers.library_index import IndexEntry, LibraryIndex
from quantis.services.track_tags import TrackMeta, write_tags

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
VID = "a_b-c_d_e_f"


def make_audio(folder: Path, name: str) -> Path:
    dst = folder / name
    shutil.copy(FIXTURES / ("silence" + dst.suffix), dst)
    return dst


def make_tagged(folder: Path, name: str, source="youtube", track_id=VID) -> Path:
    path = make_audio(folder, name)
    write_tags(
        path,
        TrackMeta(source=source, track_id=track_id, title="Песня", artist="Артист"),
        None,
    )
    return path


@pytest.fixture
def music(tmp_path):
    folder = tmp_path / "music"
    folder.mkdir()
    return folder


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache" / "library_index.json"


def new_index(music, cache) -> LibraryIndex:
    return LibraryIndex(music_dir=music, cache_path=cache)


@pytest.mark.asyncio
async def test_refresh_indexes_tagged_and_legacy(music, cache):
    make_tagged(music, "Артист - Песня.mp3")
    make_audio(music, "42_Song_A.mp3")
    make_audio(music, "Artist - Foreign.mp3")
    index = new_index(music, cache)
    await index.refresh()
    assert index.is_ready
    assert index.has("youtube", VID)
    assert index.has("yandex", "42")
    entries = index.entries()
    assert len(entries) == 2
    by_source = {e.source: e for e in entries}
    assert by_source["youtube"].tagged is True
    assert by_source["yandex"].tagged is False
    assert by_source["yandex"].title == "Song"
    assert by_source["yandex"].author == "A"


@pytest.mark.asyncio
async def test_renamed_tagged_file_found_after_refresh(music, cache):
    old = make_tagged(music, "Артист - Песня.mp3")
    index = new_index(music, cache)
    await index.refresh()
    new = old.rename(music / "Другое имя.mp3")
    await index.refresh()
    assert index.path_for("youtube", VID) == new
    assert len(index.entries()) == 1


@pytest.mark.asyncio
async def test_skips_broken_files(music, cache):
    (music / "empty.mp3").write_bytes(b"")
    (music / "junk.m4a").write_bytes(b"\x00garbage" * 10)
    (music / "junk2.mp3").write_bytes(b"not audio")
    index = new_index(music, cache)
    await index.refresh()
    assert index.entries() == []
    assert index.is_ready


def test_path_for_drops_deleted_file(music, cache):
    path = make_tagged(music, "Артист - Песня.mp3")
    index = new_index(music, cache)
    entry = index.put(path)
    assert isinstance(entry, IndexEntry)
    assert index.path_for("youtube", VID) == path
    path.unlink()
    assert index.path_for("youtube", VID) is None
    assert index.entries() == []


@pytest.mark.asyncio
async def test_load_cached_skips_tag_reads(music, cache, monkeypatch):
    make_tagged(music, "Артист - Песня.mp3")
    await new_index(music, cache).refresh()

    def boom(path):
        raise AssertionError("read_identity не должен вызываться")

    monkeypatch.setattr(li, "read_identity", boom)
    fresh = new_index(music, cache)
    fresh.load_cached()
    assert fresh.has("youtube", VID)
    assert not fresh.is_ready
    await fresh.refresh()
    assert fresh.is_ready
    assert fresh.has("youtube", VID)


@pytest.mark.asyncio
async def test_cache_for_other_music_dir_ignored(tmp_path, music, cache):
    make_tagged(music, "Артист - Песня.mp3")
    await new_index(music, cache).refresh()
    other = tmp_path / "other"
    other.mkdir()
    fresh = new_index(other, cache)
    fresh.load_cached()
    assert fresh.entries() == []
    assert not fresh.is_ready


def test_corrupt_cache_is_empty(music, cache):
    cache.parent.mkdir(parents=True)
    cache.write_text("{not json", encoding="utf-8")
    index = new_index(music, cache)
    index.load_cached()
    assert index.entries() == []
    cache.write_text(json.dumps({"version": 1, "music_dir": str(music), "files": 5}))
    index.load_cached()
    assert index.entries() == []


@pytest.mark.asyncio
async def test_tagged_wins_over_legacy_same_id(music, cache):
    make_audio(music, "42_Song_A.mp3")
    tagged = make_tagged(music, "Артист - Песня.mp3", source="yandex", track_id="42")
    index = new_index(music, cache)
    await index.refresh()
    assert index.path_for("yandex", "42") == tagged
    assert index.entry_for("yandex", "42").tagged is True


@pytest.mark.asyncio
async def test_listener_called_after_refresh(music, cache):
    calls = []
    index = new_index(music, cache)
    index.add_listener(lambda: calls.append(index.is_ready))
    await index.refresh()
    assert calls == [True]


def test_has_without_source(music, cache):
    index = new_index(music, cache)
    index.put(make_audio(music, "42_Song_A.mp3"))
    assert index.has(None, "42")
    assert index.has("yandex", "42")
    assert not index.has("youtube", "42")
    assert not index.has(None, "43")


def test_soundcloud_key_normalized(music, cache):
    index = new_index(music, cache)
    index.put(make_audio(music, "sc123_Song_A.mp3"))
    assert index.has("soundcloud", "123")
    assert index.has("SoundCloud", "sc123")


@pytest.mark.asyncio
async def test_ambiguous_legacy_name_has_alias(music, cache):
    path = make_audio(music, "12345678_Ab_Song.mp3")
    index = new_index(music, cache)
    await index.refresh()
    entries = index.entries()
    assert len(entries) == 1
    assert entries[0].source == "yandex"
    assert entries[0].track_id == "12345678"
    assert entries[0].ambiguous is True
    assert index.path_for("yandex", "12345678") == path
    # алиас по YouTube-прочтению (первые 11 символов) указывает на ту же запись
    assert index.has("youtube", "12345678_Ab")
    assert index.path_for("youtube", "12345678_Ab") == path
    assert index.entry_for("youtube", "12345678_Ab") == entries[0]


@pytest.mark.asyncio
async def test_ambiguous_survives_cache(music, cache):
    from quantis.providers.legacy_names import parse_legacy_names

    path = make_audio(music, "12345678_Ab_Song.mp3")
    readings = parse_legacy_names(path.name)
    assert [r.source for r in readings] == ["yandex", "youtube"]
    yt = readings[1]
    await new_index(music, cache).refresh()
    fresh = new_index(music, cache)
    fresh.load_cached()
    assert fresh.has("youtube", yt.track_id)
    assert fresh.path_for("youtube", yt.track_id) == path
    assert fresh.entries()[0].ambiguous is True


def test_unambiguous_legacy_not_marked(music, cache):
    index = new_index(music, cache)
    entry = index.put(make_audio(music, "42_Song_A.mp3"))
    assert entry.ambiguous is False


def test_tagged_file_ignores_legacy_name(music, cache):
    index = new_index(music, cache)
    path = make_tagged(music, "12345678_Ab_Song.mp3", source="soundcloud", track_id="9")
    entry = index.put(path)
    assert (entry.source, entry.track_id, entry.ambiguous) == ("soundcloud", "9", False)
    assert not index.has("yandex", "12345678")
    assert not index.has("youtube", "12345678_Ab")


def test_default_music_dir_is_lazy(tmp_path, monkeypatch):
    from quantis.providers.path_provider import PathProvider

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    index = LibraryIndex(cache_path=tmp_path / "c.json")
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(a))
    assert index.music_dir == a
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(b))
    assert index.music_dir == b


def test_discard_and_reset(music, cache):
    index = new_index(music, cache)
    path = make_audio(music, "42_Song_A.mp3")
    index.put(path)
    index.discard(path)
    assert index.entries() == []
    index.put(path)
    index.reset()
    assert index.entries() == [] and not index.is_ready


def test_singleton_isolated_by_conftest():
    LibraryIndex.reset_instance()
    first = LibraryIndex.instance()
    assert first is LibraryIndex.instance()
    assert LibraryIndex.CACHE_PATH is not None
    assert first.cache_path == LibraryIndex.CACHE_PATH
    LibraryIndex.reset_instance()
    assert LibraryIndex.instance() is not first


def _slow_reads(monkeypatch, started, release):
    """read_identity блокируется, пока тест не отпустит скан."""
    orig = li.read_identity

    def slow(path):
        started.set()
        release.wait(5)
        return orig(path)

    monkeypatch.setattr(li, "read_identity", slow)
    return orig


@pytest.mark.asyncio
async def test_put_during_refresh_is_kept(music, cache, monkeypatch):
    import asyncio
    import threading

    make_audio(music, "1_S_A.mp3")
    started, release = threading.Event(), threading.Event()
    orig = _slow_reads(monkeypatch, started, release)
    index = new_index(music, cache)
    task = asyncio.create_task(index.refresh())
    while not started.is_set():
        await asyncio.sleep(0.01)
    new = make_audio(music, "99_New_A.mp3")
    monkeypatch.setattr(li, "read_identity", orig)
    assert index.put(new) is not None
    release.set()
    await task
    assert index.has("yandex", "99")
    assert index.has("yandex", "1")


@pytest.mark.asyncio
async def test_discard_during_refresh_is_kept(music, cache, monkeypatch):
    import asyncio
    import threading

    gone = make_audio(music, "2_Gone_A.mp3")
    index = new_index(music, cache)
    index.put(gone)
    make_audio(music, "1_S_A.mp3")
    started, release = threading.Event(), threading.Event()
    _slow_reads(monkeypatch, started, release)
    task = asyncio.create_task(index.refresh())
    while not started.is_set():
        await asyncio.sleep(0.01)
    index.discard(gone)  # запись убрана, файл на диске остался
    release.set()
    await task
    assert not index.has("yandex", "2")
    assert index.has("yandex", "1")


@pytest.mark.asyncio
async def test_wait_ready_survives_reset(music, cache):
    import asyncio

    index = new_index(music, cache)
    waiter = asyncio.create_task(index.wait_ready())
    await asyncio.sleep(0)
    index.reset()
    await index.refresh()
    await asyncio.wait_for(waiter, 1)


@pytest.mark.asyncio
async def test_stale_scan_after_reset_is_discarded(tmp_path, music, cache, monkeypatch):
    import asyncio
    import threading

    other = tmp_path / "music_b"
    other.mkdir()
    make_audio(music, "1_S_A.mp3")
    make_audio(other, "7_B_A.mp3")
    started, release = threading.Event(), threading.Event()
    orig = _slow_reads(monkeypatch, started, release)
    index = LibraryIndex(music_dir=music, cache_path=cache)
    task = asyncio.create_task(index.refresh())
    while not started.is_set():
        await asyncio.sleep(0.01)
    monkeypatch.setattr(li, "read_identity", orig)
    index.reset()
    index._music_dir = other
    release.set()
    await task
    assert not index.is_ready
    assert index.entries() == []
    assert not index.has("yandex", "1")
    await index.refresh()
    assert index.is_ready
    assert [e.track_id for e in index.entries()] == ["7"]


@pytest.mark.asyncio
async def test_overlapping_refreshes_keep_put(music, cache, monkeypatch):
    import asyncio
    import threading

    make_audio(music, "1_S_A.mp3")
    started, release = threading.Event(), threading.Event()
    orig = _slow_reads(monkeypatch, started, release)
    index = new_index(music, cache)
    first = asyncio.create_task(index.refresh())
    while not started.is_set():
        await asyncio.sleep(0.01)
    second = asyncio.create_task(index.refresh())
    await asyncio.sleep(0.05)
    monkeypatch.setattr(li, "read_identity", orig)
    assert index.put(make_audio(music, "99_New_A.mp3")) is not None
    release.set()
    await asyncio.gather(first, second)
    assert index.has("yandex", "99")
    assert index.has("yandex", "1")


@pytest.mark.asyncio
async def test_refresh_mid_scan_waits_for_fresh_scan(music, cache, monkeypatch):
    import asyncio
    import threading

    make_audio(music, "1_S_A.mp3")
    started, release = threading.Event(), threading.Event()
    _slow_reads(monkeypatch, started, release)
    index = new_index(music, cache)
    first = asyncio.create_task(index.refresh())
    while not started.is_set():
        await asyncio.sleep(0.01)
    make_audio(music, "5_Late_A.mp3")  # появился после старта первого скана
    second = asyncio.create_task(index.refresh())
    third = asyncio.create_task(index.refresh())  # делит проход со вторым
    await asyncio.sleep(0.05)
    release.set()
    await asyncio.gather(first, second, third)
    assert index.has("yandex", "5")


@pytest.mark.asyncio
async def test_cancelled_refresh_does_not_overlap_scans(music, cache, monkeypatch):
    import asyncio
    import threading

    make_audio(music, "1_S_A.mp3")
    orig = li.read_identity
    counter = threading.Lock()
    state = {"now": 0, "max": 0}
    started, release = threading.Event(), threading.Event()

    def slow(path):
        with counter:
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
        started.set()
        release.wait(5)
        try:
            return orig(path)
        finally:
            with counter:
                state["now"] -= 1

    monkeypatch.setattr(li, "read_identity", slow)
    index = new_index(music, cache)
    first = asyncio.create_task(index.refresh())
    while not started.is_set():
        await asyncio.sleep(0.01)
    second = asyncio.create_task(index.refresh())
    await asyncio.sleep(0.05)
    first.cancel()
    await asyncio.sleep(0.05)
    new = make_audio(music, "99_New_A.mp3")
    monkeypatch.setattr(li, "read_identity", orig)  # put читает теги синхронно
    assert index.put(new) is not None  # put во время сканов
    release.set()
    await second
    assert state["max"] == 1
    assert index.has("yandex", "99")
    assert index.has("yandex", "1")


@pytest.mark.asyncio
async def test_cache_save_failure_does_not_block_ready(music, cache, monkeypatch):
    import asyncio

    make_audio(music, "1_S_A.mp3")
    index = new_index(music, cache)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(index, "_save_cache", boom)
    waiter = asyncio.create_task(index.wait_ready())
    await asyncio.sleep(0)
    await index.refresh()
    await asyncio.wait_for(waiter, 1)
    assert index.is_ready
    assert index.has("yandex", "1")


def _no_tag_reads(monkeypatch):
    def boom(path):
        raise AssertionError("read_identity не должен вызываться")

    monkeypatch.setattr(li, "read_identity", boom)


def test_load_cached_without_cache_seeds_legacy_names(music, cache, monkeypatch):
    make_audio(music, "42_Song_A.mp3")
    amb = make_audio(music, "12345678_Ab_Song.mp3")
    make_audio(music, "Artist - Foreign.mp3")
    _no_tag_reads(monkeypatch)
    index = new_index(music, cache)
    index.load_cached()
    assert not index.is_ready
    assert index.has("yandex", "42")
    assert index.path_for("yandex", "12345678") == amb
    from quantis.providers.legacy_names import parse_legacy_names

    yt = parse_legacy_names(amb.name)[1]
    assert index.has("youtube", yt.track_id)
    assert len(index.entries()) == 2


def test_load_cached_other_dir_cache_seeds_legacy_names(
    tmp_path, music, cache, monkeypatch
):
    other = tmp_path / "other"
    other.mkdir()
    index = new_index(other, cache)
    index.put(make_audio(other, "7_Old_B.mp3"))  # кэш для другой папки
    make_audio(music, "42_Song_A.mp3")
    _no_tag_reads(monkeypatch)
    fresh = new_index(music, cache)
    fresh.load_cached()
    assert fresh.has("yandex", "42")
    assert not fresh.has("yandex", "7")
    assert not fresh.is_ready


@pytest.mark.asyncio
async def test_refresh_reads_tags_of_seeded_legacy_named_file(music, cache):
    # Имя в старом формате, но в файле уже есть наши теги — теги главнее.
    make_tagged(music, "42_Song_A.mp3", source="youtube", track_id=VID)
    index = new_index(music, cache)
    index.load_cached()
    assert index.has("yandex", "42")  # до скана — только по имени
    await index.refresh()
    assert index.is_ready
    assert index.has("youtube", VID)
    assert not index.has("yandex", "42")
    entry = index.entry_for("youtube", VID)
    assert entry is not None and entry.tagged and entry.title == "Песня"


@pytest.mark.asyncio
async def test_scan_error_releases_waiters(music, cache, monkeypatch):
    import asyncio

    index = new_index(music, cache)

    def boom(_music_dir):
        raise RuntimeError("scan")

    monkeypatch.setattr(index, "_scan", boom)
    waiter = asyncio.create_task(index.wait_ready())
    await asyncio.sleep(0)
    try:
        await index.refresh()
    except RuntimeError:
        pass
    await asyncio.wait_for(waiter, 1)
    assert index.is_ready
    await asyncio.wait_for(index.wait_ready(), 1)
