# CleanPlayer

[![Python](https://img.shields.io/badge/python-3.14.2-informational)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20|%20macOS%20|
%20Linux-brightgreen)]()
[![SOON](https://img.shields.io/badge/SOON-Android-green)]()
[![Status](https://img.shields.io/badge/status-Active-success)]()
[![Release](https://img.shields.io/github/v/release/Really-Fun/CleanPlayer)]
()

Десктопный музыкальный плеер на `PySide6 + asyncio` с поиском треков, стримингом, скачиванием и историей прослушивания.

Проект развивается как реальный рабочий плеер: с понятной структурой и нормальной декомпозицией по слоям.

---

## Что уже работает

- Поиск треков из нескольких источников (`Yandex`, `YouTube`).
- Воспроизведение через VLC-движок.
- Скачивание треков и обложек.
- История прослушивания в `SQLite` с восстановлением позиции трека.
- Системные плейлисты:
  - `Скачанные`
  - `Недавно прослушанные`
- Настройки интерфейса:
  - фон
  - параметры визуализатора
- Отдельная страница профиля (пока заглушка под API-ключи/токены).
- Кнопка быстрого открытия папки приложения (там же `music/`, `covers/`, `assets/`).

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

---

## Переменные и ключи

Клиенты берут секреты из системного keyring.

Используемые сервисные ключи:

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

Слой истории разделен на 3 части:

- `database/async_database.py` — асинхронная обертка над SQLite.
- `database/track_history_repository.py` — SQL-операции.
- `services/TrackHistoryService.py` — бизнес-логика (частота сохранения, финализация прослушивания, сборка “Недавно прослушанных”).

Таблица `track_history` хранит:

- `track_key` (`source:id`)
- `title`, `author`, `source`
- `position_ms`, `duration_ms`
- `listen_count`
- `last_played_at`

Для нормальной работы под нагрузкой включены PRAGMA:

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

## Интерфейс

> Добавь файлы в `assets/readme/`, и блок начнет показывать реальные скриншоты/GIF без доп. правок.

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
- Валидация ключей и проверка подключения к сервисам прямо из интерфейса.
- Улучшение диагностики сетевых ошибок.

---

## Лицензия

MIT

