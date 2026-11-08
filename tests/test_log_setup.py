"""Логи в файл: чистый файл на каждый запуск и потолок в 1 МБ."""

from __future__ import annotations

import logging

import pytest

from quantis.utils import log_setup


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    root.handlers = []
    yield root
    for handler in root.handlers:
        handler.close()
    root.handlers = saved_handlers
    root.setLevel(saved_level)


def _total(directory):
    return sum(p.stat().st_size for p in directory.iterdir())


def test_old_log_is_wiped_on_start(tmp_path, clean_root):
    (tmp_path / "quantis.log").write_text("прошлый запуск\n", encoding="utf-8")
    (tmp_path / "quantis.log.1").write_text("ещё старее\n", encoding="utf-8")
    path = log_setup.setup_logging(tmp_path)
    logging.getLogger("t").info("новый запуск")
    for handler in clean_root.handlers:
        handler.flush()
    text = path.read_text(encoding="utf-8")
    assert "прошлый запуск" not in text
    assert "новый запуск" in text
    assert not (tmp_path / "quantis.log.1").exists()


def test_logs_never_exceed_one_megabyte(tmp_path, clean_root):
    log_setup.setup_logging(tmp_path)
    clean_root.handlers = [
        h for h in clean_root.handlers if isinstance(h, logging.FileHandler)
    ]
    logger = logging.getLogger("flood")
    line = "x" * 1000
    for _ in range(5000):  # ~5 МБ сообщений
        logger.info(line)
    for handler in clean_root.handlers:
        handler.flush()
    assert _total(tmp_path) <= log_setup.MAX_TOTAL_BYTES
    assert {p.name for p in tmp_path.iterdir()} == {"quantis.log", "quantis.log.1"}
