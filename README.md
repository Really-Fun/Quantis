# CleanPlayer

[![Python](https://img.shields.io/badge/python-3.14.2-informational)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen)](https://github.com/Really-Fun/CleanPlayer)
[![Status](https://img.shields.io/badge/status-Active-success)](https://github.com/Really-Fun/CleanPlayer)
[![Release](https://img.shields.io/github/v/release/Really-Fun/CleanPlayer)](https://github.com/Really-Fun/CleanPlayer/releases)

Быстрый десктопный плеер на `PySide6 + asyncio`: поиск, стриминг, скачивание, история и нормальная архитектура без каши.

---

## Что уже работает

- Поиск треков из `Yandex` и `YouTube`.
- Стабильное воспроизведение через `VLC`.
- Скачивание треков + обложек.
- История прослушивания в `SQLite` с автосохранением позиции.
- Системные плейлисты: `Скачанные`, `Недавно прослушанные`.
- Настройки UI: фон и параметры визуализатора.
- Страница профиля (заглушка под API-ключи/токены).
- Кнопка быстрого открытия рабочей папки приложения (`music/`, `covers/`, `assets/`).

---

## Стек

- Python `3.13+`
- `PySide6`, `qasync`, `python-vlc`
- `ytmusicapi`, `yt-dlp`, `yandex-music`
- `aiosqlite`
- `qt-material`

Полный список зависимостей — в `requirements.txt`.

---

## Быстрый старт

```bash
git clone https://github.com/Really-Fun/CleanPlayer.git
cd CleanPlayer
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Требование: установлен `VLC` в системе (для `python-vlc`).

---

## Ключи и токены

Секреты берутся из системного `keyring`.

Используемые записи:

- `YANDEX_TOKEN_NEON_APP` (user: `NEON_APP`)
- `LASTFM_API_NEON_APP` (user: `NEON_APP`)
- `LASTFM_SECRET_NEON_APP` (user: `NEON_APP`)

Пример, как записать значения через Python:

```python
import keyring

keyring.set_password("YANDEX_TOKEN_NEON_APP", "NEON_APP", "<ваш_token>")
keyring.set_password("LASTFM_API_NEON_APP", "NEON_APP", "<ваш_api_key>")
keyring.set_password("LASTFM_SECRET_NEON_APP", "NEON_APP", "<ваш_api_secret>")
```

---

## Архитектура истории прослушивания

История разбита на 3 слоя:

- `database/async_database.py` — асинхронная обертка над SQLite.
- `database/track_history_repository.py` — SQL-репозиторий.
- `services/TrackHistoryService.py` — бизнес-логика (частота сохранения, финализация прослушивания, сборка “Недавно прослушанных”).

Таблица `track_history` хранит:

- `track_key` (`source:id`)
- `title`, `author`, `source`
- `position_ms`, `duration_ms`
- `listen_count`
- `last_played_at`

Для скорости и стабильности включены PRAGMA:

- `journal_mode=WAL`
- `synchronous=NORMAL`
- `temp_store=MEMORY`
- `cache_size` (увеличенный кеш)

---

## Структура проекта

```text
config/      # инициализация внешних клиентов
database/    # SQLite + репозиторий истории
models/      # модели треков/плейлистов
player/      # воспроизведение и движок VLC
providers/   # менеджеры путей и плейлистов
services/    # поиск, стриминг, скачивание, история
ui/          # интерфейс и страницы приложения
utils/       # файловые и вспомогательные утилиты
```

---

## Интерфейс (скриншоты / GIF)

Если картинки не отображаются, просто положи их в `assets/readme/`.

### Главная

![Главная](assets/readme/home.png)

### Поисковик

![Поисковик](assets/readme/search.png)

### Плейлист

![Плейлист](assets/readme/playlist.png)

### Настройки

![Настройки](assets/readme/settings.png)

### Плеер (GIF)

![Плеер](assets/readme/player.gif)

---

## Ближайший план

- Сохранение ключей из UI страницы профиля.
- Проверка валидности ключей прямо из интерфейса.
- Доработка сетевой диагностики и UX при ошибках соединения.
- Рекомендации на основе Spotipy
- Улучшенная оптимизация
- Читска кода

---

## Лицензия

MIT

