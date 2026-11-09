"""Установка плагинов из zip / URL."""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from quantis.plugins.loader import resolve_plugins_dir
from quantis.utils import app_paths

logger = logging.getLogger(__name__)

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
_MAX_ZIP_BYTES = 32 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_MEMBER_BYTES = 16 * 1024 * 1024
_READ_CHUNK = 64 * 1024


class PluginInstallError(Exception):
    pass


def _safe_plugin_id(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_")
    if not cleaned or not _SAFE_ID.match(cleaned):
        raise PluginInstallError(f"Недопустимое имя плагина: {name!r}")
    return cleaned


def _require_https_url(url: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise PluginInstallError("URL должен начинаться с https://")
    if parsed.username or parsed.password:
        raise PluginInstallError("URL с учётными данными не допускается")
    if not parsed.hostname:
        raise PluginInstallError("В URL нет хоста")


def _find_plugin_root(extracted: Path) -> Path:
    """Ищет каталог с plugin.py (корень zip или одна вложенная папка)."""
    if (extracted / "plugin.py").is_file():
        return extracted
    children = [
        p for p in extracted.iterdir() if p.is_dir() and not p.name.startswith("__")
    ]
    if len(children) == 1 and (children[0] / "plugin.py").is_file():
        return children[0]
    for child in extracted.rglob("plugin.py"):
        try:
            if not child.resolve().is_relative_to(extracted.resolve()):
                continue
        except (OSError, ValueError):
            continue
        return child.parent
    raise PluginInstallError("В архиве не найден plugin.py")


def _safe_member_path(dest_root: Path, member_name: str) -> Path:
    """Путь файла внутри dest_root; иначе PluginInstallError (zip-slip)."""
    name = member_name.replace("\\", "/")
    if not name or name.endswith("/"):
        raise PluginInstallError("Небезопасный путь в архиве")
    if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
        raise PluginInstallError("Небезопасный путь в архиве")
    parts = [part for part in name.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise PluginInstallError("Небезопасный путь в архиве")
    target = dest_root.joinpath(*parts).resolve()
    try:
        if not target.is_relative_to(dest_root.resolve()):
            raise PluginInstallError("Небезопасный путь в архиве")
    except (OSError, ValueError) as exc:
        raise PluginInstallError("Небезопасный путь в архиве") from exc
    return target


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    total_out = 0
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        if info.file_size < 0 or info.file_size > _MAX_MEMBER_BYTES:
            raise PluginInstallError("Файл в архиве слишком большой")
        total_out += info.file_size
        if total_out > _MAX_UNCOMPRESSED_BYTES:
            raise PluginInstallError("Архив слишком большой")
        target = _safe_member_path(dest, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, open(target, "wb") as out:
            copied = 0
            while True:
                chunk = src.read(_READ_CHUNK)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > _MAX_MEMBER_BYTES:
                    raise PluginInstallError("Файл в архиве слишком большой")
                out.write(chunk)


BACKUP_PREFIX = "_backup_"
STAGING_PREFIX = "_new_"


def _manifest_id(root: Path) -> str | None:
    try:
        data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("id") if isinstance(data, dict) else None
    return str(value) if value else None


def install_plugin_from_zip(
    zip_path: str | Path,
    *,
    overwrite: bool = True,
    plugin_id: str | None = None,
    plugins_dir: Path | None = None,
    keep_backup: bool = False,
) -> str:
    """Распаковывает zip в plugins_dir. Возвращает plugin_id.

    plugin_id — id из магазина: папка называется им, и id в manifest.json
    обязан совпасть. Старая версия на время замены переезжает в
    ``_backup_<id>``; с keep_backup она остаётся до ``drop_backup`` или
    ``restore_backup`` (откат, если новая версия не запустилась).
    """
    path = Path(zip_path)
    if not path.is_file():
        raise PluginInstallError(f"Файл не найден: {path}")
    if path.suffix.lower() != ".zip":
        raise PluginInstallError("Нужен архив .zip")
    try:
        if path.stat().st_size > _MAX_ZIP_BYTES:
            raise PluginInstallError("Архив слишком большой")
    except OSError as exc:
        raise PluginInstallError(f"Не удалось прочитать архив: {exc}") from exc

    plugins_dir = plugins_dir or resolve_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="quantis_plugin_") as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(path, "r") as zf:
                _safe_extract_zip(zf, tmp_path)
        except zipfile.BadZipFile as exc:
            raise PluginInstallError("Повреждённый zip-архив") from exc

        root = _find_plugin_root(tmp_path)
        if plugin_id is not None:
            plugin_id = _safe_plugin_id(plugin_id)
            found = _manifest_id(root)
            if found != plugin_id:
                raise PluginInstallError(
                    f"id в архиве ({found or 'нет'}) не совпадает с магазином ({plugin_id})"
                )
        elif root == tmp_path:
            plugin_id = _safe_plugin_id(path.stem)
        else:
            plugin_id = _safe_plugin_id(root.name)

        target = plugins_dir / plugin_id
        if target.exists() and not overwrite:
            raise PluginInstallError(f"Плагин «{plugin_id}» уже установлен")

        staging = plugins_dir / f"{STAGING_PREFIX}{plugin_id}"
        backup = plugins_dir / f"{BACKUP_PREFIX}{plugin_id}"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(root, staging, symlinks=False)
        if not (staging / "plugin.py").is_file():
            shutil.rmtree(staging, ignore_errors=True)
            raise PluginInstallError("После установки нет plugin.py")

        shutil.rmtree(backup, ignore_errors=True)
        try:
            if target.exists():
                target.rename(backup)
            staging.rename(target)
        except OSError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise PluginInstallError(f"Не удалось заменить плагин: {exc}") from exc

    if not keep_backup:
        drop_backup(plugin_id, plugins_dir)
    logger.info("Плагин установлен: %s → %s", plugin_id, target)
    return plugin_id


def restore_backup(plugin_id: str, plugins_dir: Path | None = None) -> bool:
    """Возвращает прежнюю версию из ``_backup_<id>``. False — бэкапа нет."""
    plugins_dir = plugins_dir or resolve_plugins_dir()
    backup = plugins_dir / f"{BACKUP_PREFIX}{plugin_id}"
    if not backup.is_dir():
        return False
    target = plugins_dir / plugin_id
    shutil.rmtree(target, ignore_errors=True)
    backup.rename(target)
    logger.info("Плагин %s откачен на прежнюю версию", plugin_id)
    return True


def drop_backup(plugin_id: str, plugins_dir: Path | None = None) -> None:
    plugins_dir = plugins_dir or resolve_plugins_dir()
    shutil.rmtree(plugins_dir / f"{BACKUP_PREFIX}{plugin_id}", ignore_errors=True)


def download_plugin_zip(url: str, dest_dir: Path | None = None) -> Path:
    """Скачивает zip по HTTPS во временный/указанный каталог."""
    _require_https_url(url)

    dest_dir = dest_dir or app_paths.cache_dir() / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "plugin.zip"

    req = Request(url.strip(), headers={"User-Agent": "Quantis/1.0"})
    try:
        with urlopen(req, timeout=60) as resp:
            final = urlparse(resp.geturl())
            if final.scheme != "https":
                raise PluginInstallError("Редирект на не-HTTPS отклонён")
            length = resp.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > _MAX_ZIP_BYTES:
                        raise PluginInstallError("Скачиваемый файл слишком большой")
                except ValueError:
                    pass
            written = 0
            with open(dest, "wb") as out:
                while True:
                    chunk = resp.read(_READ_CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _MAX_ZIP_BYTES:
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise PluginInstallError("Скачиваемый файл слишком большой")
                    out.write(chunk)
    except PluginInstallError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise PluginInstallError(f"Не удалось скачать: {exc}") from exc

    if dest.stat().st_size < 32:
        dest.unlink(missing_ok=True)
        raise PluginInstallError("Скачанный файл пуст или слишком маленький")
    return dest


def install_plugin_from_url(url: str, *, overwrite: bool = True) -> str:
    zip_path = download_plugin_zip(url)
    try:
        return install_plugin_from_zip(zip_path, overwrite=overwrite)
    finally:
        zip_path.unlink(missing_ok=True)
