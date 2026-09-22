"""Общий пул потоков для I/O (поиск, стрим, скачивание)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

_pool: ThreadPoolExecutor | None = None


def get_worker_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="quantis")
    return _pool


def shutdown_worker_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        _pool = None
