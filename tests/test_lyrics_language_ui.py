import asyncio
from types import SimpleNamespace

from quantis.models.track import YoutubeTrack
from quantis.services.lyrics import LyricLine, Lyrics
from quantis.ui.main_window import QuantisMainWindow
from quantis.ui.views.widgets.side_panel import SidePanel


def test_subtitle_language_requests_follow_track_and_selection(qapp):
    requests = []
    tasks = []
    callbacks = []
    panel = SidePanel(None)
    window = SimpleNamespace(
        _side_panel=panel,
        _ui_prefs=SimpleNamespace(youtube_captions_enabled=True),
        _lyrics_track=None,
        _lyrics_request=0,
        _lyrics_language="",
        _bridge=SimpleNamespace(schedule=tasks.append, invoke_main=callbacks.append),
    )

    async def fetch(track, language, *, youtube_captions):
        assert youtube_captions
        requests.append((track.track_id, language))
        if language == "de" and requests.count((track.track_id, "de")) == 1:
            return Lyrics()
        lyrics = Lyrics([LyricLine(0, language or track.title)], True, "YouTube")
        lyrics.translations = {"fr": "Français", "de": "Deutsch"}
        return lyrics

    window._lyrics_service = SimpleNamespace(fetch=fetch)
    track = YoutubeTrack("1", "First", "Artist")
    panel.lyrics_language_requested.connect(
        lambda language: QuantisMainWindow._load_lyrics(window, track, language)
    )
    QuantisMainWindow._load_lyrics(window, track)
    asyncio.run(tasks.pop())
    callbacks.pop()()
    combo = panel._language_combo
    assert not combo.isHidden()
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Оригинал",
        "Français",
        "Deutsch",
    ]

    for index in (1, 2):
        combo.setCurrentIndex(index)
        combo.activated.emit(index)
        asyncio.run(tasks.pop())
    callbacks.pop()()
    callbacks.pop()()
    assert panel.lyrics.state == "translation_failed"
    assert not combo.isHidden()
    assert combo.itemData(0) == ""
    assert combo.currentData() == "de"
    combo.activated.emit(combo.currentIndex())
    asyncio.run(tasks.pop())
    callbacks.pop()()
    assert panel.lyrics._lyrics.lines[0].text == "de"

    combo.setCurrentIndex(0)
    combo.activated.emit(0)
    asyncio.run(tasks.pop())
    track = YoutubeTrack("2", "Next", "Artist")
    QuantisMainWindow._load_lyrics(window, track)
    assert combo.isHidden()
    callbacks.pop()()
    assert panel.lyrics.state == "loading"
    asyncio.run(tasks.pop())
    callbacks.pop()()
    assert panel.lyrics._lyrics.lines[0].text == "Next"
    assert requests == [
        ("1", ""),
        ("1", "fr"),
        ("1", "de"),
        ("1", "de"),
        ("1", ""),
        ("2", ""),
    ]
