"""QLabel, который переносит текст не больше чем на ``max_lines`` строк и ставит «…»."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QFontMetrics, QTextLayout
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


def elide_lines(text: str, font: QFont, width: int, max_lines: int) -> str:
    """Текст с переносами ``\\n``, не длиннее ``max_lines`` строк шириной ``width``."""
    if width <= 0 or not text:
        return text
    metrics = QFontMetrics(font)
    layout = QTextLayout(text, font)
    layout.beginLayout()
    lines: list[str] = []
    while len(lines) < max_lines:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        start, length = line.textStart(), line.textLength()
        if len(lines) == max_lines - 1:
            rest = text[start:].strip()
            lines.append(metrics.elidedText(rest, Qt.TextElideMode.ElideRight, width))
        else:
            lines.append(text[start : start + length].rstrip())
    layout.endLayout()
    return "\n".join(lines)


class ElidedLabel(QLabel):
    def __init__(
        self, text: str = "", max_lines: int = 2, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._full = text
        self._max_lines = max_lines
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._refresh()

    def setText(self, text: str) -> None:  # noqa: N802 — API QLabel
        self._full = text
        self._refresh()

    def set_max_lines(self, max_lines: int) -> None:
        if max_lines != self._max_lines:
            self._max_lines = max_lines
            self._refresh()

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh()

    def _refresh(self) -> None:
        metrics = QFontMetrics(self.font())
        shown = elide_lines(
            self._full, self.font(), self.contentsRect().width(), self._max_lines
        )
        self.setToolTip(self._full if "…" in shown else "")
        super().setText(shown)
        self.setFixedHeight(
            metrics.lineSpacing() * max(1, shown.count("\n") + 1)
            + self.contentsMargins().top()
            + self.contentsMargins().bottom()
        )
