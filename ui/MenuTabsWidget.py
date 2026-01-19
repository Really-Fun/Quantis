from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFrame, QToolButton, QHBoxLayout,
)
from PySide6.QtGui import QIcon



class MenuTabs(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedWidth(88)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ================= PANEL =================
        panel = QFrame(self)
        panel.setObjectName("navPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 16, 12, 16)
        panel_layout.setSpacing(10)
        panel_layout.setAlignment(Qt.AlignTop)

        self.btn_home = QPushButton("🏠")
        self.btn_search = QPushButton("🔍")
        self.btn_library = QPushButton("🎵")

        for btn in (
            self.btn_home,
            self.btn_search,
            self.btn_library,
        ):
            btn.setFixedHeight(44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("navButton")

        panel_layout.addWidget(self.btn_home)
        panel_layout.addWidget(self.btn_search)
        panel_layout.addWidget(self.btn_library)

        # ===== SETTINGS BUTTON =====
        self.btn_settings = QToolButton()
        self.btn_settings.setIcon(QIcon("assets/icons/setting.png"))
        self.btn_settings.setIconSize(QSize(40,40))
        self.btn_settings.setFixedSize(40,40)
        self.btn_settings.setAutoRaise(True)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setObjectName("roundButton")

        # ===== ACCOUNT BUTTON =====
        self.btn_account = QToolButton()
        self.btn_account.setIcon(QIcon("assets/icons/account.png"))
        self.btn_account.setIconSize(QSize(40, 40))
        self.btn_account.setFixedSize(40,40)
        self.btn_account.setAutoRaise(True)
        self.btn_account.setCursor(Qt.PointingHandCursor)
        self.btn_account.setObjectName("roundButton")

        panel_layout.addStretch(1)
        self.nizh_layout = QHBoxLayout()
        self.nizh_layout.addWidget(self.btn_settings)
        self.nizh_layout.addStretch(1)
        self.nizh_layout.addWidget(self.btn_account)
        panel_layout.addLayout(self.nizh_layout)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(panel)

        # ================= STYLE =================
        self.setStyleSheet("""
            QFrame#navPanel {
                background: rgba(0, 0, 0, 160);
                border-right: 1px solid rgba(0, 255, 255, 120);
            }

            QPushButton#navButton {
                color: #e6ffff;
                font-size: 18px;
                border-radius: 12px;
                background: transparent;
            }

            QPushButton#navButton:hover {
                background: rgba(0, 255, 255, 70);
            }

            QPushButton#navButton:pressed {
                background: rgba(0, 255, 255, 140);
            }

            QPushButton#navButton:checked {
                background: rgba(0, 255, 255, 160);
                color: white;
            }
            
            QToolButton#roundButton,
            QToolButton#roundButton:hover,
            QToolButton#roundButton:pressed,
            QToolButton#roundButton:checked {
                background-color: rgba(0, 0, 0, 120) !important;
                border: none !important;
                outline: none !important;
            }

        """)
