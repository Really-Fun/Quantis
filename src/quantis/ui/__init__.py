from __future__ import annotations

from typing import Any

__all__ = ["Quantis", "QuantisMainWindow"]


def __getattr__(name: str) -> Any:
    if name in {"Quantis", "QuantisMainWindow"}:
        from quantis.ui.main_window import Quantis, QuantisMainWindow

        return {"Quantis": Quantis, "QuantisMainWindow": QuantisMainWindow}[name]
    raise AttributeError(name)
