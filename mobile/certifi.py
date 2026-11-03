"""Замена пакета certifi в APK: путь к сертификатам, записанным при запуске.

yt-dlp загружает сертификаты через certifi.where(), а без certifi берёт
системные — их у Python на Android нет, и SSL_CERT_FILE он при этом не
учитывает. Настоящий certifi в APK положить нельзя: buildozer не
упаковывает его cacert.pem. Файл пишет main._install_ca_bundle().
"""

from __future__ import annotations

import os


def where() -> str:
    path = os.environ.get("QUANTIS_CA_FILE", "")
    if path:
        return path
    # На компьютере (запуск из этой папки) файл не пишется: системный набор.
    import ssl

    paths = ssl.get_default_verify_paths()
    return paths.cafile or paths.openssl_cafile or ""


def contents() -> str:
    with open(where(), encoding="ascii") as bundle:
        return bundle.read()
