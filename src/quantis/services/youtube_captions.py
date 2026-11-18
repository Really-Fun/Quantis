"""Субтитры YouTube и их переводы через тот же прокси, что и поток."""

from __future__ import annotations

import html
import json
from urllib.parse import parse_qs, urlsplit

from yt_dlp import YoutubeDL
from yt_dlp.networking import Request
from yt_dlp.utils import update_url_query

from quantis.config.credentials import youtube_yt_dlp_cookiefile
from quantis.models.track import Track
from quantis.services.lyrics import LyricLine, Lyrics
from quantis.services.net_proxy import with_youtube_proxy


def _json3_tracks(groups: dict) -> dict:
    tracks = {}
    for code, formats in groups.items():
        for fmt in formats:
            if fmt.get("ext") == "json3" and fmt.get("url"):
                tracks[code] = fmt
                break
    return tracks


def _caption_choices(info: dict) -> tuple[dict, dict]:
    manual = _json3_tracks(info.get("subtitles") or {})
    auto = _json3_tracks(info.get("automatic_captions") or {})
    original_code = next((key[:-5] for key in auto if key.endswith("-orig")), "")
    preferred = info.get("language") or original_code
    originals = {
        key: fmt
        for key, fmt in auto.items()
        if "tlang" not in parse_qs(urlsplit(fmt["url"]).query)
    }
    original = (
        manual.get(preferred)
        or manual.get(original_code)
        or originals.get(f"{preferred}-orig")
        or originals.get(preferred)
        or next(iter(manual.values()), None)
        or next(iter(originals.values()), None)
    )
    if original is None:
        return {}, {}
    original_lang = parse_qs(urlsplit(original["url"]).query).get("lang", [preferred])[
        0
    ]
    choices = {}
    # YouTube может переводить несколько исходных дорожек на один язык.
    # Выбираем перевод именно с воспроизводимой дорожки.
    for code, fmt in auto.items():
        params = parse_qs(urlsplit(fmt["url"]).query)
        target = params.get("tlang", [""])[0]
        # Для перевода ручных субтитров yt-dlp добавляет язык источника к
        # ключу (ru-en). Некоторые версии добавляют его также к самому tlang.
        if (
            target == code
            and original_lang in manual
            and code.endswith(f"-{original_lang}")
        ):
            target = code.removesuffix(f"-{original_lang}")
            fmt = {**fmt, "url": update_url_query(fmt["url"], {"tlang": target})}
        if (
            target
            and target not in {original_lang, "und"}
            and params.get("lang", [original_lang])[0] == original_lang
        ):
            choices.setdefault(target, fmt)
    for code, fmt in manual.items():
        if code != original_lang and fmt is not original:
            choices[code] = fmt
    return original, choices


def _parse_json3(payload: bytes) -> list[LyricLine]:
    lines = []
    for event in json.loads(payload).get("events", []):
        start = event.get("tStartMs")
        words = "".join(seg.get("utf8", "") for seg in event.get("segs", []))
        words = html.unescape(words).strip()
        if isinstance(start, int) and words:
            lines.append(LyricLine(start, words))
    return sorted(lines, key=lambda line: line.t)


def fetch_captions(track: Track, language: str) -> Lyrics | None:
    options = with_youtube_proxy(
        {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writeautomaticsub": True,  # включает список автопереводов в метаданных
            "ignore_no_formats_error": True,
            "socket_timeout": 10,
            "retries": 1,
            "extractor_retries": 1,
            "cookiefile": youtube_yt_dlp_cookiefile(),
        }
    )
    with YoutubeDL(options) as client:
        info = client.extract_info(
            f"https://www.youtube.com/watch?v={track.track_id}",
            download=False,
            process=False,
        )
        original, choices = _caption_choices(info or {})
        selected = choices.get(language) if language else original
        translations = {code: fmt.get("name") or code for code, fmt in choices.items()}
        if not selected:
            return Lyrics(translations=translations) if language else None
        request = Request(selected["url"], headers=selected.get("http_headers", {}))
        with client.urlopen(request) as response:
            lines = _parse_json3(response.read())
    return (
        Lyrics(lines, bool(lines), "YouTube", translations)
        if lines or language
        else None
    )
