"""Страница настроек NFS-диктора."""

from __future__ import annotations

from config import (
    DUCK_LEVELS,
    VOICE_DMITRY,
    VOICE_SVETLANA,
    SpeakerConfig,
)
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from quantis.ui.views.widgets.glass_panel import GlassPanel

_VOICE_CHOICES = (
    (VOICE_DMITRY, "Dmitry — мужской (как радио-диджей)"),
    (VOICE_SVETLANA, "Svetlana — женский"),
)
_RATE_CHOICES = (
    ("+0%", "Обычная"),
    ("+8%", "Чуть быстрее"),
    ("+12%", "Радио (+12%)"),
    ("+20%", "Бодро"),
)
_DUCK_CHOICES = (
    (0.20, "20% — трек почти шёпотом"),
    (0.30, "30% — как в NFS"),
    (0.40, "40% — трек слышнее"),
)


class SpeakerPage(QWidget):
    config_changed = Signal(object)
    preview_requested = Signal()

    def __init__(
        self,
        config: SpeakerConfig,
        settings: QSettings | None,
        parent: QWidget | None = None,
        *,
        tts_ready: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setWindowFlags(Qt.WindowType.Widget)
        self._config = config
        self._settings = settings
        self._loading = True

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 8, 16, 20)
        root.setSpacing(12)

        panel = GlassPanel()
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(14)

        panel_layout.addWidget(QLabel("Диктор", objectName="settingsSectionLabel"))
        subtitle = QLabel(
            "На «Моей волне» и радио по треку перед композицией звучит короткий "
            "факт и название. Трек приглушается, слайдер громкости не двигается."
        )
        subtitle.setObjectName("settingsRowDesc")
        subtitle.setWordWrap(True)
        panel_layout.addWidget(subtitle)

        self._tts_hint = QLabel(
            "Нет пакета edge-tts. Установите группу: poetry install --with dj"
        )
        self._tts_hint.setObjectName("settingsRowDesc")
        self._tts_hint.setWordWrap(True)
        self._tts_hint.setVisible(not tts_ready)
        panel_layout.addWidget(self._tts_hint)

        enabled_row, enabled_body = self._row(
            "Объявлять треки",
            "Только волна и радио. Обычные плейлисты молчат",
        )
        self._enabled_cb = QCheckBox("Включить диктора")
        self._enabled_cb.setObjectName("settingsCheck")
        self._enabled_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._enabled_cb.toggled.connect(self._on_enabled_toggled)
        enabled_body.addWidget(self._enabled_cb)
        panel_layout.addWidget(enabled_row)

        self._voice_combo = self._combo_row(
            panel_layout,
            "Голос",
            "Нейронные голоса Microsoft. Официального диктора NFS здесь нет",
            _VOICE_CHOICES,
            self._on_voice_changed,
        )
        self._rate_combo = self._combo_row(
            panel_layout,
            "Скорость речи",
            "Чуть быстрее обычного — ближе к радиостанции из гонок",
            _RATE_CHOICES,
            self._on_rate_changed,
        )
        self._duck_combo = self._combo_row(
            panel_layout,
            "Трек под голосом",
            "Какая доля громкости остаётся у музыки, пока говорит диктор",
            _DUCK_CHOICES,
            self._on_duck_changed,
        )

        preview_row, preview_body = self._row(
            "Превью",
            "Произнести пример фразы, не приглушая текущий трек",
        )
        self._preview_btn = QPushButton("Произнести пример")
        self._preview_btn.setObjectName("settingsButton")
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_btn.setEnabled(tts_ready)
        self._preview_btn.clicked.connect(self.preview_requested.emit)
        preview_body.addWidget(self._preview_btn)
        panel_layout.addWidget(preview_row)

        root.addWidget(panel)
        root.addStretch(1)
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._sync_from_config()
        self._loading = False

    def set_tts_ready(self, ready: bool) -> None:
        self._tts_hint.setVisible(not ready)
        self._preview_btn.setEnabled(ready)

    def _row(self, title: str, desc: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("settingsRow")
        column = QVBoxLayout(frame)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(8)
        column.addWidget(QLabel(title, objectName="settingsRowTitle"))
        column.addWidget(QLabel(desc, objectName="settingsRowDesc"))
        return frame, column

    def _combo_row(
        self,
        parent_layout: QVBoxLayout,
        title: str,
        desc: str,
        choices,
        handler,
    ) -> QComboBox:
        row, body = self._row(title, desc)
        combo = QComboBox()
        combo.setObjectName("themeCombo")
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for value, label in choices:
            combo.addItem(label, value)
        combo.currentIndexChanged.connect(handler)
        body.addWidget(combo)
        parent_layout.addWidget(row)
        return combo

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index < 0:
            if isinstance(value, (int, float)):
                index = min(
                    range(combo.count()),
                    key=lambda i: abs(float(combo.itemData(i)) - float(value)),
                )
            else:
                index = 0
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _sync_from_config(self) -> None:
        config = self._config
        self._enabled_cb.blockSignals(True)
        self._enabled_cb.setChecked(config.enabled)
        self._enabled_cb.blockSignals(False)
        self._select(self._voice_combo, config.voice)
        self._select(self._rate_combo, config.rate)
        duck = min(DUCK_LEVELS, key=lambda item: abs(item - config.duck_gain))
        self._select(self._duck_combo, duck)

    def _apply(self, **kwargs) -> None:
        if self._loading:
            return
        self._config = self._config.with_values(**kwargs)
        self._config.save(self._settings)
        self.config_changed.emit(self._config)

    def _on_enabled_toggled(self, checked: bool) -> None:
        self._apply(enabled=checked)

    def _on_voice_changed(self) -> None:
        self._apply(voice=str(self._voice_combo.currentData()))

    def _on_rate_changed(self) -> None:
        self._apply(rate=str(self._rate_combo.currentData()))

    def _on_duck_changed(self) -> None:
        self._apply(duck_gain=float(self._duck_combo.currentData()))
