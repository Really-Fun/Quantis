"""Generate PyInstaller VSVersionInfo text from ``pyproject.toml``."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def _parse_version_tuple(version: str) -> tuple[int, int, int, int]:
    parts: list[int] = []
    for chunk in version.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
        if len(parts) >= 4:
            break
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


def load_project_meta(root: Path) -> dict[str, str]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        return {}
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    project = data.get("project") or {}
    authors = project.get("authors") or []
    company = ""
    if authors and isinstance(authors[0], dict):
        company = str(authors[0].get("name") or "").strip()
    return {
        "version": str(project.get("version") or "").strip(),
        "description": str(project.get("description") or "").strip(),
        "company": company or "Really-Fun",
        "license": str(project.get("license") or "").strip(),
    }


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def render_version_info(
    *,
    version: str,
    company: str,
    description: str,
    product_name: str = "Quantis",
    original_filename: str = "Quantis.exe",
    year: int | None = None,
) -> str:
    """Return a ``VSVersionInfo(...)`` source block for ``EXE(version=...)``."""
    ver = version.strip() or "0.0.0"
    filevers = _parse_version_tuple(ver)
    filevers_csv = ", ".join(str(n) for n in filevers)
    year = datetime.now().year if year is None else year

    company_raw = company.strip() or "Really-Fun"
    description_raw = description.strip() or "Quantis media player"
    product_raw = product_name.strip() or "Quantis"
    filename_raw = original_filename.strip() or "Quantis.exe"
    copyright_raw = f"Copyright (C) {year} {company_raw}"

    return f"""# UTF-8
#
# Auto-generated from pyproject.toml - do not edit by hand.
# Regenerated during PyInstaller builds (main.spec).
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({filevers_csv}),
    prodvers=({filevers_csv}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', '{_escape(company_raw)}'),
            StringStruct('FileDescription', '{_escape(description_raw)}'),
            StringStruct('FileVersion', '{_escape(ver)}'),
            StringStruct('InternalName', '{_escape(product_raw)}'),
            StringStruct('LegalCopyright', '{_escape(copyright_raw)}'),
            StringStruct('OriginalFilename', '{_escape(filename_raw)}'),
            StringStruct('ProductName', '{_escape(product_raw)}'),
            StringStruct('ProductVersion', '{_escape(ver)}'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_version_info(
    root: Path,
    *,
    product_name: str = "Quantis",
    original_filename: str | None = None,
    out_path: Path | None = None,
) -> Path | None:
    """Write ``packaging/quantis_version_info.txt``. Returns path or None."""
    meta = load_project_meta(root)
    version = meta.get("version") or ""
    if not version:
        return None
    if original_filename is None:
        original_filename = f"{product_name}.exe"
    target = out_path or (root / "packaging" / "quantis_version_info.txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = render_version_info(
        version=version,
        company=meta.get("company") or "Really-Fun",
        description=meta.get("description") or "Quantis media player",
        product_name=product_name,
        original_filename=original_filename,
    )
    target.write_text(text, encoding="utf-8")
    return target
