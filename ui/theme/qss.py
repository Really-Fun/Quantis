"""Переиспользуемые QSS-фрагменты."""


def scroll_qss(content_object_name: str = "_sc") -> str:
    """Возвращает стиль вертикального скролла."""
    return f"""
        QScrollArea {{ background: transparent; border: none; }}
        QWidget#{content_object_name} {{ background: transparent; }}
        QScrollBar:vertical {{
            width: 5px; background: transparent;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255,255,255,30); border-radius: 2px; min-height: 30px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """


COMBO_QSS = """
    QComboBox {
        color: white; background: rgba(255,255,255,10);
        border: 1px solid rgba(255,255,255,20); border-radius: 8px;
        padding: 6px 12px; font-size: 13px; min-width: 120px;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 20px; border: none;
    }
    QComboBox QAbstractItemView {
        color: white; background: #1a1a2e;
        selection-background-color: rgba(0,220,255,60);
        border: 1px solid rgba(255,255,255,15);
        outline: none;
    }
"""
