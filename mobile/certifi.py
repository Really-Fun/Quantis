"""Замена пакета certifi в APK: путь к сертификатам, записанным при запуске.

yt-dlp загружает сертификаты через certifi.where(), а без certifi берёт
системные — их у Python на Android нет, и SSL_CERT_FILE он при этом не
учитывает. Настоящий certifi в APK положить нельзя: buildozer не
упаковывает его cacert.pem. Файл пишет main._install_ca_bundle().
"""

from __future__ import annotations

import os


def where() -> str:
    return os.environ.get("QUANTIS_CA_FILE", "")


def contents() -> str:
    with open(where(), encoding="ascii") as bundle:
        return bundle.read()
