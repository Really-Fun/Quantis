"""Текст диктора: факт + «а сейчас играет»."""

from __future__ import annotations

from quantis.models.playlist import RecommendationPlaylist, WavePlaylist

FALLBACK_FACTS = (
    "На волне Quantis сегодня без лишних слов.",
    "Держим скорость, не сбавляем громкость.",
)

_SENTENCE_ENDS = (". ", "! ", "? ", ".\n", "!\n", "?\n")


def is_radio_playlist(playlist: object | None) -> bool:
    """Говорим только на «Моей волне» и радио по треку."""
    return isinstance(playlist, (WavePlaylist, RecommendationPlaylist))


def now_playing_line(title: str, author: str) -> str:
    clean_title = " ".join(str(title or "").split()) or "этот трек"
    clean_author = " ".join(str(author or "").split()) or "неизвестный исполнитель"
    return f"А сейчас играет «{clean_title}» — {clean_author}."


def first_sentence(text: str, max_len: int = 140) -> str:
    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    cut = len(raw)
    for mark in _SENTENCE_ENDS:
        index = raw.find(mark)
        if 0 < index < cut:
            cut = index + 1
    sentence = raw[:cut].strip()
    if len(sentence) <= max_len:
        return sentence
    clipped = sentence[: max_len + 1]
    space = clipped.rfind(" ")
    if space >= 40:
        clipped = clipped[:space]
    else:
        clipped = sentence[:max_len]
    return clipped.rstrip(" ,;:") + "…"


def build_script(
    title: str,
    author: str,
    fact: str | None = None,
    *,
    fallback: str | None = None,
) -> str:
    lead = " ".join(str(fact or "").split())
    if not lead:
        lead = fallback or FALLBACK_FACTS[0]
    return f"{lead} {now_playing_line(title, author)}"
