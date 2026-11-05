"""Радиус угла для рисования кодом — с учётом темы.

У тем без скруглений (``ThemeSpec.radius == 0``, «Редакционная») все углы
прямые: и в QSS (токены ``${rN}``), и в paintEvent через ``corner()``.
"""

from __future__ import annotations


def corner(radius: float) -> float:
    from quantis.ui.preferences import UiPreferences

    return UiPreferences().theme.corner(radius)
