"""ElidedLabel: не больше max_lines строк, в конце «…», полный текст в подсказке."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontMetrics

from quantis.ui.views.widgets.elided_label import ElidedLabel, elide_lines

LONG = "Высоцкий - В заповедных и дремучих... (Песня про нечисть) " * 2


def test_elide_lines_limits_lines(qapp) -> None:
    font = QFont()
    font.setPointSize(16)
    shown = elide_lines(LONG, font, 300, 2)
    lines = shown.split("\n")
    assert len(lines) == 2
    assert lines[-1].endswith("…")
    metrics = QFontMetrics(font)
    assert all(metrics.horizontalAdvance(line) <= 300 for line in lines)


def test_short_text_untouched(qapp) -> None:
    assert elide_lines("Коротко", QFont(), 300, 2) == "Коротко"


def test_label_height_and_tooltip(qapp) -> None:
    label = ElidedLabel(LONG, max_lines=2)
    label.resize(300, 100)
    label.show()
    qapp.processEvents()
    assert label.text().count("\n") == 1
    assert label.toolTip() == LONG
    assert label.height() == 2 * QFontMetrics(label.font()).lineSpacing()
    label.setText("Коротко")
    assert label.toolTip() == ""
