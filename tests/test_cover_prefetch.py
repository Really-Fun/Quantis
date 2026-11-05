"""Докачанная обложка объявляется в главном потоке — виджеты её подхватывают."""

from __future__ import annotations

import asyncio
from pathlib import Path

from quantis.models.track import YandexTrack
from quantis.ui import cover_prefetch
from quantis.ui.views.widgets import cover_art


class _Bridge:
    def __init__(self) -> None:
        self.main_calls = 0

    def schedule(self, coro) -> None:  # type: ignore[no-untyped-def]
        asyncio.run(coro)

    def invoke_main(self, callback) -> None:  # type: ignore[no-untyped-def]
        self.main_calls += 1
        callback()


class _Downloader:
    """Качает обложки ``fetched``; остальные не нашлись."""

    def __init__(self, folder: Path, fetched: set[str]) -> None:
        self.folder, self.fetched = folder, fetched

    async def ensure_covers(self, tracks, *, limit: int = 40) -> int:  # type: ignore[no-untyped-def]
        from test_cover_art import _write_banded_jpeg

        got = [t for t in tracks[:limit] if t.track_id in self.fetched]
        for track in got:
            _write_banded_jpeg(self.folder / f"{track.track_id}.jpg")
        return len(got)


def test_prefetch_announces_downloaded_covers_on_main(
    qapp, monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        cover_art, "track_cover_file", lambda t: tmp_path / f"{t.track_id}.jpg"
    )
    monkeypatch.setattr(
        cover_prefetch, "track_cover_file", lambda t: tmp_path / f"{t.track_id}.jpg"
    )
    tracks = [YandexTrack(track_id=f"t{i}", title="x", author="a") for i in range(3)]
    from test_cover_art import _write_banded_jpeg

    _write_banded_jpeg(tmp_path / "t0.jpg")  # была и раньше — не объявляем
    heard: list[str] = []
    cover_art.CoverEvents.instance().cover_ready.connect(heard.append)
    done: list[bool] = []
    bridge = _Bridge()

    cover_prefetch.schedule_cover_prefetch(
        tracks, _Downloader(tmp_path, {"t1"}), bridge, on_done=lambda: done.append(True)
    )

    assert heard == [str(tmp_path / "t1.jpg")]
    assert done == [True]
    assert bridge.main_calls == 1
