"""Запись и чтение встроенных тегов (mp3/m4a) через mutagen."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from mutagen.id3 import ID3
from mutagen.mp4 import MP4, MP4Cover

from quantis.services import track_tags
from quantis.services.track_tags import (
    TagIdentity,
    TagWriteError,
    TrackMeta,
    read_identity,
    source_url,
    write_tags,
)

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
VID = "a_b-c_d_e_f"
URL = "https://music.youtube.com/watch?v=a_b-c_d_e_f"


def _noise_image(path: Path, fmt: str) -> Path:
    from PIL import Image

    data = os.urandom(128 * 128 * 3)
    Image.frombytes("RGB", (128, 128), data).save(path, fmt)
    return path


@pytest.fixture
def jpeg(tmp_path):
    return _noise_image(tmp_path / "cover.jpg", "JPEG")


@pytest.fixture
def png(tmp_path):
    return _noise_image(tmp_path / "cover.png", "PNG")


def copy_fixture(tmp_path: Path, name: str) -> Path:
    dst = tmp_path / name
    shutil.copy(FIXTURES / name, dst)
    return dst


def _meta(**kw) -> TrackMeta:
    base = dict(
        source="youtube",
        track_id=VID,
        title="Песня",
        artist="Артист",
        album="Альбом",
        year=2021,
        genre="Rock",
        track_number=3,
        source_url=URL,
    )
    base.update(kw)
    return TrackMeta(**base)


@pytest.mark.parametrize("name", ["silence.mp3", "silence.m4a"])
def test_roundtrip_identity(tmp_path, jpeg, name):
    path = copy_fixture(tmp_path, name)
    write_tags(path, _meta(), cover=jpeg)
    assert read_identity(path) == TagIdentity("youtube", VID, "Песня", "Артист")


def test_mp3_is_id3v23_with_standard_frames(tmp_path, jpeg):
    path = copy_fixture(tmp_path, "silence.mp3")
    write_tags(path, _meta(), cover=jpeg)
    tags = ID3(path)
    assert tags.version == (2, 3, 0)
    assert tags["TIT2"].text == ["Песня"]
    assert tags["TPE1"].text == ["Артист"]
    assert tags["TALB"].text == ["Альбом"]
    assert tags["TCON"].text == ["Rock"]
    assert tags["TRCK"].text == ["3"]
    year = tags["TYER"] if "TYER" in tags else tags["TDRC"]
    assert str(year.text[0]) == "2021"
    assert tags.getall("COMM")[0].text == [URL]
    assert tags["TXXX:QUANTIS_SOURCE"].text == ["youtube"]
    assert tags["TXXX:QUANTIS_ID"].text == [VID]
    apic = tags.getall("APIC")[0]
    assert apic.mime == "image/jpeg"
    assert apic.type == 3


def test_m4a_standard_atoms(tmp_path, jpeg):
    path = copy_fixture(tmp_path, "silence.m4a")
    write_tags(path, _meta(), cover=jpeg)
    tags = MP4(path).tags
    assert tags["\xa9nam"] == ["Песня"]
    assert tags["\xa9ART"] == ["Артист"]
    assert tags["\xa9alb"] == ["Альбом"]
    assert tags["\xa9gen"] == ["Rock"]
    assert tags["\xa9day"] == ["2021"]
    assert tags["trkn"] == [(3, 0)]
    assert tags["\xa9cmt"] == [URL]
    assert tags["----:com.quantis:QUANTIS_ID"] == [VID.encode()]
    assert tags["----:com.quantis:QUANTIS_SOURCE"] == [b"youtube"]
    assert tags["covr"][0].imageformat == MP4Cover.FORMAT_JPEG


def test_empty_fields_not_written(tmp_path):
    meta = _meta(genre="", album="", year=None, track_number=None, source_url="")
    mp3 = copy_fixture(tmp_path, "silence.mp3")
    write_tags(mp3, meta, cover=None)
    tags = ID3(mp3)
    for key in ("TCON", "TALB", "TRCK", "TYER", "TDRC"):
        assert key not in tags
    assert not tags.getall("COMM")
    m4a = copy_fixture(tmp_path, "silence.m4a")
    write_tags(m4a, meta, cover=None)
    atoms = MP4(m4a).tags
    for key in ("\xa9gen", "\xa9alb", "\xa9day", "trkn", "\xa9cmt"):
        assert key not in atoms


def test_png_cover_gets_png_mime(tmp_path, png):
    mp3 = copy_fixture(tmp_path, "silence.mp3")
    write_tags(mp3, _meta(), cover=png)
    assert ID3(mp3).getall("APIC")[0].mime == "image/png"
    m4a = copy_fixture(tmp_path, "silence.m4a")
    write_tags(m4a, _meta(), cover=png)
    assert MP4(m4a).tags["covr"][0].imageformat == MP4Cover.FORMAT_PNG


@pytest.mark.parametrize("name", ["silence.mp3", "silence.m4a"])
@pytest.mark.parametrize("kind", ["none", "broken"])
def test_missing_or_broken_cover_writes_tags_without_art(tmp_path, name, kind):
    path = copy_fixture(tmp_path, name)
    cover = None
    if kind == "broken":
        cover = tmp_path / "bad.jpg"
        cover.write_bytes(b"not an image" * 1000)
    write_tags(path, _meta(), cover=cover)
    assert read_identity(path) == TagIdentity("youtube", VID, "Песня", "Артист")
    if name.endswith("mp3"):
        assert not ID3(path).getall("APIC")
    else:
        assert "covr" not in MP4(path).tags


@pytest.mark.parametrize("name", ["silence.mp3", "silence.m4a"])
def test_failure_mid_write_leaves_original_intact(tmp_path, monkeypatch, jpeg, name):
    path = copy_fixture(tmp_path, name)
    before = path.read_bytes()

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(track_tags.ID3, "save", boom)
    monkeypatch.setattr(track_tags.MP4, "save", boom)
    with pytest.raises(TagWriteError):
        write_tags(path, _meta(), cover=jpeg)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.part"))


def test_unsupported_suffix_raises(tmp_path):
    path = tmp_path / "a.ogg"
    path.write_bytes(b"x")
    with pytest.raises(TagWriteError):
        write_tags(path, _meta(), cover=None)


@pytest.mark.parametrize("ext", ["mp3", "m4a"])
@pytest.mark.parametrize("content", [b"", b"garbage" * 100])
def test_read_identity_never_raises(tmp_path, ext, content):
    path = tmp_path / f"foo.{ext}"
    path.write_bytes(content)
    assert read_identity(path) is None
    assert read_identity(tmp_path / f"missing.{ext}") is None


@pytest.mark.parametrize("name", ["silence.mp3", "silence.m4a"])
def test_read_identity_none_without_our_tags(tmp_path, name):
    assert read_identity(copy_fixture(tmp_path, name)) is None


def test_foreign_tags_preserved(tmp_path):
    from mutagen.id3 import TPUB

    path = copy_fixture(tmp_path, "silence.mp3")
    tags = ID3()
    tags.add(TPUB(encoding=3, text=["Label"]))
    tags.save(path, v2_version=3)
    write_tags(path, _meta(), cover=None)
    assert ID3(path)["TPUB"].text == ["Label"]


def test_source_urls():
    assert source_url("yandex", "123") == "https://music.yandex.ru/track/123"
    assert (
        source_url("youtube", "abcdefghijk")
        == "https://music.youtube.com/watch?v=abcdefghijk"
    )
    assert source_url("soundcloud", "42") == "https://api.soundcloud.com/tracks/42"
