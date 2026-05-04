<div align="center">
  <img src="assets/readme/quantis.png" alt="Quantis Logo" width="400">

  <br><br>

  [![Python](https://img.shields.io/badge/python-3.13%2B-informational?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![License](https://img.shields.io/badge/license-GPL3.0-blue?style=for-the-badge)](LICENSE)
  [![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen?style=for-the-badge)](https://github.com/Really-Fun/Quantis)
  [![Status](https://img.shields.io/badge/status-Active-success?style=for-the-badge)](https://github.com/Really-Fun/Quantis)
  [![Release](https://img.shields.io/github/v/release/Really-Fun/Quantis?style=for-the-badge)](https://github.com/Really-Fun/Quantis/releases)

[![Platform](https://img.shields.io/badge/soon-Anroid-brightred?style=for-the-badge)](https://github.com/Really-Fun/Quantis/releases)
</div>

<br>

> **Quantis** — быстрый кроссплатформенный десктопный плеер на `PySide6` и `asyncio`.  
> Обеспечивает поиск, стриминг, скачивание треков и ведение истории прослушивания, опираясь на чистую асинхронную архитектуру.
---

## Почему Quantis?

- Поиск треков из `Yandex` и `YouTube`.
- Стабильное воспроизведение через `VLC`.
- Скачивание треков + обложек.
- История прослушивания в `SQLite` с автосохранением позиции.
- Системные плейлисты: `Скачанные`, `Недавно прослушанные`.
- Настройки UI: фон и параметры визуализатора.
- Страница профиля (оффлайн, для загрузки токенов).
- Кнопка быстрого открытия рабочей папки приложения (`music/`, `covers/`, `assets/`).
- Бесплатный (открытый исходный код)

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
git clone https://github.com/Really-Fun/Quantis.git
cd Quantis
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Требование: установлен `VLC` в системе (для `python-vlc`).

### Сборка exe (Windows)

```bat
pip install pyinstaller
pyinstaller main.spec
```

Исполняемый файл и ресурсы появятся в `dist\Quantis\`. Запуск: `dist\Quantis\Quantis.exe`. В spec подключены локали **ytmusicapi** (в т.ч. RU) через `collect_all('ytmusicapi')`.

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

### Главная

![Главная](assets/readme/home.png)

### Поисковик

![Поисковик](assets/readme/search.png)

### Плейлист

![Плейлист](assets/readme/playlist.png)

### Настройки

![Настройки](assets/readme/settings.png)

### Обновленный вид (Update)

![Обновление](assets/readme/update.jpg)


---

## Ближайший план

- Доработка сетевой диагностики и UX при ошибках соединения.
- Улучшенная оптимизация
- Рефакторинг и оптимизация кодовой базы
- Настройка пользовательской темы

---
