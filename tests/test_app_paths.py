"""Каталоги пользовательских данных: выбор корня, портативный режим, миграция."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from quantis.utils import app_paths


@pytest.fixture(autouse=True)
def clean_paths_cache(monkeypatch: pytest.MonkeyPatch):
    for name in ("QUANTIS_DATA_DIR", "QUANTIS_PORTABLE"):
        monkeypatch.delenv(name, raising=False)
    app_paths.reset_cache()
    yield
    app_paths.reset_cache()


def _freeze(monkeypatch: pytest.MonkeyPatch, exe_dir: Path) -> None:
    """Имитирует сборку PyInstaller с exe в указанном каталоге."""
    monkeypatch.setattr(app_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(app_paths, "app_dir", lambda: exe_dir)


def test_explicit_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "custom"
    monkeypatch.setenv("QUANTIS_DATA_DIR", str(target))
    assert app_paths.data_dir() == target
    assert app_paths.database_path() == target / "player_history.db"


def test_dev_run_uses_project_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(app_paths, "app_dir", lambda: tmp_path)
    assert app_paths.data_dir() == tmp_path
    assert app_paths.default_music_dir() == tmp_path / "music"


def test_portable_marker_keeps_data_next_to_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe_dir = tmp_path / "portable"
    exe_dir.mkdir()
    (exe_dir / "portable.txt").write_text("", encoding="utf-8")
    _freeze(monkeypatch, exe_dir)

    assert app_paths.is_portable() is True
    assert app_paths.data_dir() == exe_dir
    assert app_paths.default_music_dir() == exe_dir / "music"


def test_installed_build_uses_user_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe_dir = tmp_path / "Program Files" / "Quantis"
    exe_dir.mkdir(parents=True)
    _freeze(monkeypatch, exe_dir)
    user_dir = tmp_path / "userdata"
    monkeypatch.setattr(app_paths, "_platform_data_dir", lambda: user_dir)

    assert app_paths.is_portable() is False
    assert app_paths.data_dir() == user_dir
    assert app_paths.covers_dir() == user_dir / "covers"


def test_readonly_dir_falls_back_to_user_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Портативная сборка в Program Files не должна падать по правам."""
    exe_dir = tmp_path / "locked"
    exe_dir.mkdir()
    (exe_dir / "portable.txt").write_text("", encoding="utf-8")
    _freeze(monkeypatch, exe_dir)
    user_dir = tmp_path / "fallback"
    monkeypatch.setattr(app_paths, "_platform_data_dir", lambda: user_dir)
    monkeypatch.setattr(app_paths, "_is_writable", lambda path: path != exe_dir)

    assert app_paths.data_dir() == user_dir


def test_migration_copies_legacy_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe_dir = tmp_path / "old"
    (exe_dir / "playlists").mkdir(parents=True)
    (exe_dir / "playlists" / "mix.json").write_text("[]", encoding="utf-8")
    (exe_dir / "player_history.db").write_text("db", encoding="utf-8")
    _freeze(monkeypatch, exe_dir)

    target = tmp_path / "new"
    monkeypatch.setenv("QUANTIS_DATA_DIR", str(target))
    app_paths.reset_cache()

    app_paths.migrate_legacy_data()

    assert (target / "playlists" / "mix.json").read_text(encoding="utf-8") == "[]"
    assert (target / "player_history.db").is_file()
    # Источник не тронут: он может быть read-only
    assert (exe_dir / "player_history.db").is_file()

    # Повторный вызов не перезаписывает уже изменённые данные
    (target / "player_history.db").write_text("changed", encoding="utf-8")
    app_paths.migrate_legacy_data()
    assert (target / "player_history.db").read_text(encoding="utf-8") == "changed"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-специфичный путь")
def test_xdg_data_home_respected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert app_paths._platform_data_dir() == tmp_path / "share" / "quantis"


def test_dev_app_dir_ignores_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запуск из подкаталога не должен раскладывать данные в нём."""
    from quantis.utils import resource_path

    root = resource_path.source_root()
    if root is None:
        pytest.skip("пакет установлен не из исходников")
    monkeypatch.chdir(tmp_path)
    assert resource_path.app_dir() == root
