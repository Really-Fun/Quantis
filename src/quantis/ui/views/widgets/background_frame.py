from __future__ import annotations

import math

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QWidget

from quantis.ui.cover_accent import CoverPalette
from quantis.ui.themes import registry
from quantis.ui.themes.spec import ThemeSpec
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor


class BackgroundFrame(QFrame):
    """Каркас окна: рисует фон всего окна из ``BackdropCompositor`` (тема,
    обои, видео) и ведёт фазу свечения по таймеру."""

    def __init__(
        self,
        wallpaper: str | None = None,
        theme: ThemeSpec | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("appShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._theme = theme or registry.default()
        self._phase = 0.0
        _ = wallpaper
        self._compositor = BackdropCompositor(self._theme, self)
        self._compositor.frame_changed.connect(self.update)

        self._content = QWidget(self)
        self._content.setObjectName("appContent")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._content.setAutoFillBackground(False)
        self._content.setStyleSheet("#appContent { background: transparent; }")

        self._eco = False
        self._cinematic = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        # Pulse после первого кадра — не конкурирует с layout/show.
        QTimer.singleShot(400, self._sync_timer)

    @property
    def compositor(self) -> BackdropCompositor:
        return self._compositor

    def _animated(self) -> bool:
        return self._theme.backdrop.glow is not None

    def _sync_timer(self) -> None:
        if self._animated() and not self._eco and not self._cinematic:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def content_host(self) -> QWidget:
        return self._content

    def set_eco(self, enabled: bool) -> None:
        """В фоне останавливаем pulse (~25 fps) — главный GPU-расход UI."""
        if self._eco == enabled:
            return
        self._eco = enabled
        self._sync_timer()

    def set_cinematic(self, enabled: bool) -> None:
        if self._cinematic == enabled:
            return
        self._cinematic = enabled
        self._sync_timer()
        self._compositor.set_cinematic(enabled)

    def set_theme(self, theme: ThemeSpec) -> None:
        if self._theme is not theme:
            self._theme = theme
            self._sync_timer()
            self._compositor.set_theme(theme)

    def set_palette(self, palette: CoverPalette) -> None:
        """Палитра трека (и кадры перехода между треками)."""
        self._compositor.set_palette(palette)

    def _tick(self) -> None:
        if self._eco or self._cinematic or not self._animated():
            return
        self._phase = (self._phase + 0.012) % (math.tau)
        self._compositor.set_phase(self._phase)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._content.setGeometry(self.rect())
        self._compositor.set_size(self.size(), self.devicePixelRatioF())

    def paintEvent(self, event) -> None:
        # окно переехало на экран с другим масштабом — resizeEvent не придёт
        self._compositor.set_size(self.size(), self.devicePixelRatioF())
        frame = self._compositor.frame()
        dpr = frame.devicePixelRatio()
        target = event.rect()
        source = QRect(
            round(target.x() * dpr),
            round(target.y() * dpr),
            round(target.width() * dpr),
            round(target.height() * dpr),
        )
        painter = QPainter(self)
        painter.drawImage(target, frame, source)
        painter.end()
