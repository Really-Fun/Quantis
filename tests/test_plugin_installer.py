"""Безопасная установка плагинов: zip-slip, HTTPS, лимиты размера."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from quantis.plugins.installer import (
    PluginInstallError,
    _safe_member_path,
    download_plugin_zip,
    install_plugin_from_zip,
)


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def test_zip_slip_member_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(PluginInstallError, match="Небезопасный"):
        _safe_member_path(dest, "../outside.py")
    with pytest.raises(PluginInstallError, match="Небезопасный"):
        _safe_member_path(dest, "/tmp/abs.py")
    with pytest.raises(PluginInstallError, match="Небезопасный"):
        _safe_member_path(dest, "ok/../../etc/passwd")


def test_zip_slip_archive_not_extracted(tmp_path: Path, monkeypatch) -> None:
    from quantis.plugins import installer

    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(installer, "resolve_plugins_dir", lambda: plugins)

    zip_path = tmp_path / "evil.zip"
    zip_path.write_bytes(
        _zip_bytes(
            {
                "../outside.py": "print(1)",
                "plugin.py": "x = 1\n",
            }
        )
    )
    with pytest.raises(PluginInstallError, match="Небезопасный"):
        install_plugin_from_zip(zip_path)
    assert not (tmp_path / "outside.py").exists()
    assert list(plugins.iterdir()) == []


def test_installs_nested_plugin_folder(tmp_path: Path, monkeypatch) -> None:
    from quantis.plugins import installer

    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(installer, "resolve_plugins_dir", lambda: plugins)

    zip_path = tmp_path / "good.zip"
    zip_path.write_bytes(
        _zip_bytes(
            {
                "hello_plugin/plugin.py": "class X: pass\n",
                "hello_plugin/manifest.json": '{"id": "hello_plugin"}\n',
            }
        )
    )
    plugin_id = install_plugin_from_zip(zip_path)
    assert plugin_id == "hello_plugin"
    assert (plugins / "hello_plugin" / "plugin.py").is_file()


def test_download_rejects_http() -> None:
    with pytest.raises(PluginInstallError, match="https"):
        download_plugin_zip("http://example.com/plugin.zip")


def test_download_rejects_credentials_in_url() -> None:
    with pytest.raises(PluginInstallError, match="учётными"):
        download_plugin_zip("https://user:pass@example.com/plugin.zip")
