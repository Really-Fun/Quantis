# Quantis UI Map

Краткая схема интерфейса для навигации по коду.

## Стек страниц (`MainWindow` / `QStackedWidget`)

| Index | Страница | ViewModel | Файл |
|------:|----------|-----------|------|
| 0 | Главная | `HomeViewModel` | `ui/views/home_page.py` |
| 1 | Поиск | `SearchViewModel` | `ui/views/search_page.py` |
| 2 | Библиотека | `HomeViewModel` | `ui/views/library_page.py` |
| 3 | Статистика | `StatsViewModel` | `ui/views/stats_page.py` |
| 4 | Плагины | — | `ui/views/plugins_page.py` |
| 5 | Member | — | `ui/views/member_page.py` |
| 6 | Настройки | — | `ui/views/settings_page.py` |
| 7 | Плейлист (деталь) | `PlaylistViewModel` | `ui/views/playlist_page.py` |
| 8+ | Плагины (динамика) | — | через `UiExtensionHost` |

Страницы 1–7 создаются лениво (`_ensure_*_page` в `main_window.py`).

## Оболочка

```
QuantisMainWindow
├── BackgroundFrame
│   ├── AppHeader
│   ├── UpdateBanner (скрыта, пока нет новой версии)
│   └── BodyWithWallpaper
│       ├── SideNavRail
│       ├── QStackedWidget (страницы)
│       ├── NowPlayingPanel
│       └── PlayerBar
└── NowPlayingFullscreen (overlay)
```

## EventBus (основные сигналы)

- `track_changed` — смена трека
- `playback_paused` / `playback_resumed` / `track_finished`
- `next_requested` / `previous_requested`
- `history_updated` / `playlists_updated`
- `error_occurred` — ошибки для UI

## Настройки UI

`UiPreferences` (`ui/preferences.py`) — QSettings: тема, обои, качество/FPS видео-фона, eco, громкость, кэш проверки обновлений.

## Services → UI

- `SearchViewModel` → `AsyncFinder`
- `PlayerViewModel` → `PlaybackController` / `Player`
- `HomeViewModel` → `TrackHistoryService`, `MusicService`, `LikedTracksService`
- Настройки / плашка обновления → `app_update.fetch_latest_release` (GitHub Releases)
