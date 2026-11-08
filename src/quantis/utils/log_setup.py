"""Логи в консоль и в файл.

Файл — ``<data_dir>/logs/quantis.log``. При каждом запуске старый лог
стирается, а за один запуск логи не занимают больше ``MAX_TOTAL_BYTES``:
два файла по половине лимита, при переполнении старая половина выбрасывается.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_NAME = "quantis.log"
MAX_TOTAL_BYTES = 1024 * 1024
"""Потолок на все файлы лога вместе."""


def log_dir() -> Path:
    from quantis.utils import app_paths

    return app_paths.data_dir() / "logs"


def setup_logging(
    directory: Path | None = None, level: int = logging.INFO
) -> Path | None:
    """Настраивает корневой логгер. Возвращает путь к файлу лога или None,
    если писать в файл не получилось (тогда логи только в консоль)."""
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)

    # В собранной под Windows версии без консоли sys.stdout — None.
    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

    try:
        file_handler = _file_handler(directory or log_dir())
    except OSError:
        logging.getLogger(__name__).warning(
            "Не удалось открыть файл лога", exc_info=True
        )
        return None
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    sys.excepthook = _log_uncaught
    return Path(file_handler.baseFilename)


def _log_uncaught(exc_type, exc, tb) -> None:
    """Необработанное исключение — в лог: без консоли иначе его не увидеть."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("quantis").critical(
        "Необработанное исключение", exc_info=(exc_type, exc, tb)
    )


def _file_handler(directory: Path) -> RotatingFileHandler:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_NAME
    # Новый запуск — чистый лог. RotatingFileHandler с maxBytes всегда
    # дописывает в конец, поэтому старые файлы удаляем сами.
    for old in (path, path.with_name(f"{LOG_NAME}.1")):
        old.unlink(missing_ok=True)
    # backupCount=0 не ротирует вовсе (файл растёт бесконечно), поэтому
    # держим один запасной файл и делим лимит пополам.
    return RotatingFileHandler(
        path,
        maxBytes=MAX_TOTAL_BYTES // 2,
        backupCount=1,
        encoding="utf-8",
    )
