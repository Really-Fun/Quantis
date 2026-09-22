"""Версия: pyproject.toml в исходниках, штамп в frozen-сборке."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantis import version as version_mod
from quantis.version import VERSION_STAMP_NAME, get_version, project_version


def test_project_version_matches_pyproject() -> None:
    assert project_version()
    assert project_version() == get_version()


def test_stamp_name_is_version_txt() -> None:
    # PyInstaller datas сохраняет имя файла; runtime читает его рядом с version.py.
    assert VERSION_STAMP_NAME == "version.txt"


def test_spec_writes_stamp_with_runtime_filename() -> None:
    spec = (
        Path(__file__).resolve().parents[1] / "packaging" / "pyinstaller" / "main.spec"
    ).read_text(encoding="utf-8")
    assert "_stamp = _stamp_dir / VERSION_STAMP_NAME" in spec
    assert '_stamp_dir / "quantis_version.txt"' not in spec


def test_frozen_uses_stamp_not_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(version_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(version_mod, "_version_from_stamp", lambda: "0.3.2")
    monkeypatch.setattr(version_mod, "_version_from_metadata", lambda: "0.3.0")
    monkeypatch.setattr(version_mod, "project_version", lambda: "0.3.2")
    assert get_version() == "0.3.2"


def test_frozen_ignores_stale_metadata_without_stamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(version_mod.sys, "frozen", True, raising=False)
    monkeypatch.setattr(version_mod, "_version_from_stamp", lambda: "")
    monkeypatch.setattr(version_mod, "_version_from_metadata", lambda: "0.3.0")
    monkeypatch.setattr(version_mod, "project_version", lambda: "0.3.2")
    assert get_version() == "0.0.0"


def test_version_from_stamp_reads_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp = tmp_path / VERSION_STAMP_NAME
    stamp.write_text("9.9.9\n", encoding="utf-8")
    monkeypatch.setattr(version_mod, "__file__", str(tmp_path / "version.py"))
    monkeypatch.delattr(version_mod.sys, "_MEIPASS", raising=False)
    assert version_mod._version_from_stamp() == "9.9.9"


def test_version_from_stamp_reads_meipass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundled = tmp_path / "quantis"
    bundled.mkdir()
    (bundled / VERSION_STAMP_NAME).write_text("1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(
        version_mod, "__file__", str(tmp_path / "elsewhere" / "version.py")
    )
    monkeypatch.setattr(version_mod.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert version_mod._version_from_stamp() == "1.2.3"
