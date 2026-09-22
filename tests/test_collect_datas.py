"""Сборка не должна тащить credentials и историю прослушивания."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_COLLECT = (
    Path(__file__).resolve().parents[1]
    / "packaging"
    / "pyinstaller"
    / "collect_datas.py"
)


@pytest.fixture(scope="module")
def collect_mod():
    spec = importlib.util.spec_from_file_location("quantis_collect_datas", _COLLECT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_collect_styles_skips_user_data(tmp_path: Path, collect_mod) -> None:
    styles = tmp_path / "styles"
    (styles / "themes" / "neon").mkdir(parents=True)
    (styles / "credentials").mkdir()
    (styles / "covers").mkdir()
    (styles / "themes" / "neon" / "design.qss").write_text("QWidget {}", encoding="utf-8")
    (styles / "light.qss").write_text("QWidget {}", encoding="utf-8")
    (styles / "player_history.db").write_bytes(b"sqlite")
    (styles / "credentials" / "youtube_cookies.txt").write_text("secret", encoding="utf-8")
    (styles / "covers" / "a.jpg").write_bytes(b"x")

    items = collect_mod.collect_styles(styles)
    dest_files = {Path(src).name for src, _dest in items}
    assert dest_files == {"design.qss", "light.qss"}
    joined = " ".join(src for src, _dest in items)
    assert "youtube_cookies" not in joined
    assert "player_history" not in joined
    assert "covers" not in joined


def test_collect_assets_skips_credentials(tmp_path: Path, collect_mod) -> None:
    assets = tmp_path / "assets"
    (assets / "icons").mkdir(parents=True)
    (assets / "credentials").mkdir()
    (assets / "icons" / "logo.png").write_bytes(b"png")
    (assets / "credentials" / "token.txt").write_text("secret", encoding="utf-8")

    items = collect_mod.collect_assets(assets)
    assert len(items) == 1
    assert items[0][0].endswith("logo.png")


def test_collect_assets_skips_wallpapers(tmp_path: Path, collect_mod) -> None:
    assets = tmp_path / "assets"
    (assets / "icons").mkdir(parents=True)
    (assets / "background").mkdir()
    (assets / "icons" / "play.svg").write_text("<svg/>", encoding="utf-8")
    (assets / "background" / "nebula.jpg").write_bytes(b"jpg")

    items = collect_mod.collect_assets(assets)
    assert [Path(src).name for src, _dest in items] == ["play.svg"]


def test_spec_uses_collect_helper() -> None:
    spec = (
        Path(__file__).resolve().parents[1]
        / "packaging"
        / "pyinstaller"
        / "main.spec"
    ).read_text(encoding="utf-8")
    assert "collect_styles" in spec
    assert 'datas.append((str(QUANTIS / "styles"), "quantis/styles"))' not in spec
