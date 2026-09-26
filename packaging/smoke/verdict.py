"""Итог проверки сборки по result.json: PASS/FAIL и код выхода."""

from __future__ import annotations

import json
import sys


def problems(result: dict) -> list[str]:
    found = [
        f"импорт {m}: {v}" for m, v in result.get("imports", {}).items() if v != "ok"
    ]
    audio = result.get("audio", {})
    if not audio:
        found.append("нет аудиофайлов для проверки звука")
    for ext, info in audio.items():
        if info.get("error") or info.get("position_ms", 0) <= 0:
            found.append(
                f"звук {ext}: позиция {info.get('position_ms')}, ошибка {info.get('error')}"
            )
    if not result.get("svg_icon"):
        found.append("SVG-иконка не рисуется")
    if len(result.get("themes", [])) < 2:
        found.append(f"темы: {result.get('themes')}")
    if not result.get("yt_dlp_youtube"):
        found.append("в yt-dlp нет экстрактора youtube")
    if not result.get("certifi_pem"):
        found.append("нет сертификатов certifi")
    return found


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        issues = problems(json.load(fh))
    for issue in issues:
        print("FAIL:", issue)
    print("PASS" if not issues else f"FAIL: {len(issues)} проблем")
    sys.exit(1 if issues else 0)
