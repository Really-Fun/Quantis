# Теги и обложки в скачанных треках — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Скачанные треки получают вшитые теги и обложку, человеческое имя `Исполнитель - Название.ext`, а Quantis находит свои файлы по служебному тегу через индекс; кнопка в настройках мигрирует старые файлы `ID_…`.

**Architecture:** Новый модуль `services/track_tags.py` пишет/читает теги через mutagen. `providers/library_index.py` — единая точка правды «(source, id) → файл», строится сканированием папки (теги, иначе разбор старого имени) с кэшем на диске. `AsyncDownloader.download_full` склеивает трек → обложку → теги → переименование → индекс и вызывается из трёх мест скачивания. `services/library_retag.py` + кнопка в настройках мигрируют старые файлы.

**Tech Stack:** Python 3, PySide6 + qasync, yt-dlp, yandex-music, mutagen (новая зависимость), pytest + pytest-asyncio, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-11-02-embedded-tags-design.md`

## Global Constraints

- Формат и качество звука не меняются; ffmpeg в приложение не добавляется.
- mutagen — единственная новая runtime-зависимость (`pyproject.toml`, `[project].dependencies`), должна попадать в сборку PyInstaller.
- mp3: ID3v2.3 (`save(v2_version=3)`). m4a: стандартные атомы + freeform `----:com.quantis:<KEY>`.
- Служебные ключи — константы в `services/track_tags.py`: `QUANTIS_SOURCE_KEY = "QUANTIS_SOURCE"`, `QUANTIS_ID_KEY = "QUANTIS_ID"`. `QUANTIS_SOURCE` ∈ `yandex|youtube|soundcloud`; `QUANTIS_ID` — id как в `track_id`, для SoundCloud числовой, без `sc`.
- Нет данных — поле не пишется (никаких догадок).
- Новое имя: `{Исполнитель} - {Название}.{ext}`, коллизии ` (2)`, ` (3)`…; санитизация `PathProvider._sanitize_filename_part`.
- Файл с нашими служебными тегами не перезаписывается ни при повторном скачивании, ни кнопкой.
- Переименование только после успешной записи и проверки тегов (ID и название читаются обратно); иначе файл остаётся с именем `ID_…`.
- Ошибка тегов/переименования не делает скачивание неуспешным.
- Чтение тегов при сканировании — не в UI-потоке; кэш индекса на диске обязателен.
- Запись тегов атомарна: копия `*.part` → теги → `replace`.
- Пользовательский текст — по-русски.

## Review Focus

1. Название/исполнитель с запрещёнными в Windows символами, зарезервированными именами (`CON`, `NUL`, `COM1`), точкой в конце, эмодзи или длиной 300+ символов → корректное имя файла ≤ лимита. Тест — Task 4.
2. Битый, пустой или чужой аудиофайл в папке (mp3 с мусором, m4a без атомов, 0 байт) → сканирование пропускает его без исключения. Тест — Task 3.
3. Файл удалён/переименован вне Quantis во время работы → `path_for` не возвращает несуществующий путь, следующий `refresh` подхватывает новое имя. Тест — Task 3.
4. Обложка не jpg (png у SoundCloud) или отсутствует/битая → правильный mime / теги без обложки. Тест — Task 1.
5. Сбой посреди записи тегов → исходный файл не испорчен, `*.part` не остаётся. Тест — Task 1.

Плюс: два одновременных скачивания одного трека → один файл, без ` (2)`. Тест — Task 6.

---

### Task 1: Модуль тегов (mutagen)

**Files:**
- Modify: `pyproject.toml` (добавить `"mutagen (>=1.47.0,<2.0.0)"`), `poetry.lock`
- Create: `src/quantis/services/track_tags.py`
- Create: `tests/fixtures/audio/silence.mp3`, `tests/fixtures/audio/silence.m4a` (~1 с тишины, несколько КБ; сделать один раз локально:
  `ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -b:a 32k tests/fixtures/audio/silence.mp3` и
  `ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -c:a aac -b:a 32k tests/fixtures/audio/silence.m4a`; закоммитить файлы)
- Test: `tests/test_track_tags.py`

**Interfaces:**
- Produces:
  - `@dataclass class TrackMeta: source: str; track_id: str; title: str; artist: str; album: str = ""; album_artist: str = ""; year: int | None = None; genre: str = ""; track_number: int | None = None; source_url: str = ""`
  - `@dataclass(frozen=True) class TagIdentity: source: str; track_id: str; title: str; artist: str`
  - `class TagWriteError(Exception)`
  - `def write_tags(path: Path, meta: TrackMeta, cover: Path | None) -> None` — raises `TagWriteError`
  - `def read_identity(path: Path) -> TagIdentity | None` — None, если наших служебных тегов нет или файл не читается (никогда не бросает)
  - `def source_url(source: str, track_id: str) -> str`
  - константы `QUANTIS_SOURCE_KEY`, `QUANTIS_ID_KEY`

- [ ] **Step 1: Добавить зависимость** — `poetry add "mutagen>=1.47.0,<2.0.0"`; проверить `poetry run python -c "import mutagen"`.
- [ ] **Step 2: Сделать и положить фикстуры** (команды выше). Тесты копируют фикстуру в `tmp_path` перед изменением.
- [ ] **Step 3: Write the failing tests**

```python
@pytest.mark.parametrize("name", ["silence.mp3", "silence.m4a"])
def test_roundtrip_identity(tmp_path, name):
    path = copy_fixture(tmp_path, name)
    meta = TrackMeta(source="youtube", track_id="a_b-c_d_e_f", title="Песня", artist="Артист",
                     album="Альбом", year=2021, genre="Rock", track_number=3,
                     source_url="https://music.youtube.com/watch?v=a_b-c_d_e_f")
    write_tags(path, meta, cover=JPEG_FIXTURE)
    assert read_identity(path) == TagIdentity("youtube", "a_b-c_d_e_f", "Песня", "Артист")

def test_mp3_is_id3v23_with_standard_frames(tmp_path):
    # ID3(path).version == (2, 3, 0); TIT2/TPE1/TALB/TCON/TRCK == "3"; год присутствует (TYER или TDRC→"2021");
    # COMM.text == [meta.source_url]; TXXX:QUANTIS_SOURCE == "youtube"; APIC mime "image/jpeg", type 3

def test_m4a_standard_atoms(tmp_path):
    # MP4: ©nam, ©ART, ©alb, ©gen, ©day == "2021", trkn == [(3, 0)], ©cmt == url,
    # "----:com.quantis:QUANTIS_ID" == [b"a_b-c_d_e_f"], covr[0].imageformat == MP4Cover.FORMAT_JPEG

def test_empty_fields_not_written(tmp_path):
    # genre="" и album="" → в mp3 нет TCON/TALB, в m4a нет ©gen/©alb

def test_png_cover_gets_png_mime(tmp_path):
    # PNG-обложка → APIC.mime == "image/png"; в m4a MP4Cover.FORMAT_PNG

def test_missing_or_broken_cover_writes_tags_without_art(tmp_path):
    # cover=None и cover=<файл без маркера JPEG/PNG> → теги есть, APIC/covr нет, исключения нет

def test_failure_mid_write_leaves_original_intact(tmp_path, monkeypatch):
    # monkeypatch save mutagen-объекта бросить OSError → TagWriteError; байты исходного файла не изменились;
    # в tmp_path нет файлов *.part

@pytest.mark.parametrize("content", [b"", b"garbage" * 100])
def test_read_identity_never_raises(tmp_path, content):
    # foo.mp3 / foo.m4a с content → read_identity(...) is None

def test_source_urls():
    assert source_url("yandex", "123") == "https://music.yandex.ru/track/123"
    assert source_url("youtube", "abcdefghijk") == "https://music.youtube.com/watch?v=abcdefghijk"
    assert source_url("soundcloud", "42") == "https://api.soundcloud.com/tracks/42"  # = soundcloud.watch_url
```

- [ ] **Step 4: Run** `poetry run pytest tests/test_track_tags.py -v` — Expected: FAIL (module not found).
- [ ] **Step 5: Implement** `track_tags.py`. Формат по суффиксу (`.mp3` → `mutagen.id3.ID3` / `MP3`, `.m4a` → `mutagen.mp4.MP4`), остальное → `TagWriteError`. Обложку определять по магическим байтам (`\xff\xd8` jpeg, `\x89PNG` png) и проверять `cover_validate.cover_file_ok`. Атомарность: `shutil.copy2(path, part)`, теги в `part`, `part.replace(path)`; при любом исключении удалить `part` и бросить `TagWriteError`. Существующие кадры/атомы, которых нет в `meta`, не трогать (чужие теги не стирать) — кроме служебных и тех, что пишем.
- [ ] **Step 6: Run** — Expected: PASS.
- [ ] **Step 7: Commit** `feat: write embedded tags and cover with mutagen`

---

### Task 2: Разбор старых имён `ID_…`

**Files:**
- Create: `src/quantis/providers/legacy_names.py`
- Test: `tests/test_legacy_names.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class LegacyName: source: str; track_id: str; title: str; author: str` и `def parse_legacy_name(filename: str) -> LegacyName | None`

Правила (по порядку): суффикс только `.mp3`/`.m4a`; `sc<цифры>_` → soundcloud (id без `sc`); первые 11 символов проходят `url_resolver.is_youtube_video_id`, 12-й символ `_`, и id не состоит только из цифр → youtube; `<цифры>_` → yandex; иначе None. Остаток после `ID_` делится как в нынешнем `get_tracks_from_music_dir`: `rest.split("_", 1)` → title, author; если `_` нет — author `""`.

- [ ] **Step 1: Write the failing tests**

```python
def test_youtube_id_with_underscore():
    assert parse_legacy_name("a_b-c_d_e_f_Song_Artist.m4a") == LegacyName("youtube", "a_b-c_d_e_f", "Song", "Artist")
def test_youtube_plain():  # "1cnR-iFl3D0_Real For Me_Nikkie.m4a" → youtube, "1cnR-iFl3D0"
def test_yandex():          # "42_Song_Artist.mp3" → yandex, "42"
def test_long_numeric_is_yandex():  # "12345678901_Song_A.mp3" (11 цифр) → yandex
def test_soundcloud():      # "sc987_Song_A.mp3" → soundcloud, "987"
@pytest.mark.parametrize("name", ["Artist - Song.mp3", "42_Song_A.webm", "42.mp3", "_x_y.mp3", "notes.txt"])
def test_not_legacy(name): assert parse_legacy_name(name) is None
```

- [ ] **Step 2: Run** `poetry run pytest tests/test_legacy_names.py -v` — FAIL.
- [ ] **Step 3: Implement** `parse_legacy_name`.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat: robust parsing of legacy track file names`

---

### Task 3: Индекс библиотеки

**Files:**
- Create: `src/quantis/providers/library_index.py`
- Test: `tests/test_library_index.py`

**Interfaces:**
- Consumes: `read_identity` (Task 1), `parse_legacy_name` (Task 2), `app_paths.music_dir()`, `app_paths.data_dir()`
- Produces:
  - `@dataclass(frozen=True) class IndexEntry: source: str; track_id: str; title: str; author: str; path: Path; tagged: bool`
  - `class LibraryIndex` (синглтон `LibraryIndex.instance()`; конструктор `LibraryIndex(music_dir: Path | None = None, cache_path: Path | None = None)` для тестов):
    - `load_cached() -> None` — синхронно читает кэш; если `music_dir` в кэше ≠ текущей — индекс пуст, не ready
    - `async refresh() -> None` — в `asyncio.to_thread`: листинг папки, для файлов с изменившимися (имя, size, mtime_ns) — `read_identity`, иначе `parse_legacy_name`; сохраняет кэш; ставит ready; зовёт слушателей
    - `async wait_ready() -> None`, `is_ready: bool`
    - `path_for(source: str, track_id: str) -> Path | None` — проверяет `is_file()`; несуществующую запись удаляет и возвращает None
    - `entry_for(source: str, track_id: str) -> IndexEntry | None` (та же проверка)
    - `has(source: str | None, track_id: str) -> bool` — `source=None` → любой источник
    - `entries() -> list[IndexEntry]`
    - `put(path: Path) -> IndexEntry | None` — синхронно индексирует один файл (после скачивания/переименования), сохраняет кэш
    - `discard(path: Path) -> None`
    - `reset() -> None` — очистить, не ready (смена папки)
    - `add_listener(callback: Callable[[], None]) -> None` — зовётся из рабочего потока после `refresh`
- Нормализация ключа: `(str(source).lower(), str(track_id))`; для soundcloud id без `sc`. Кэш: `data_dir()/library_index.json`, `{"version": 1, "music_dir": str, "files": {filename: {size, mtime_ns, source, track_id, title, author, tagged}}}`; запись атомарно через `.part`. Битый кэш = пустой.
- При двух файлах одного (source, id) приоритет у `tagged=True`.

- [ ] **Step 1: Write the failing tests** (`tmp_path` как music_dir и cache)

```python
async def test_refresh_indexes_tagged_and_legacy(...):
    # tagged "Артист - Песня.mp3" (write_tags youtube/abc…) + "42_Song_A.mp3" + "Artist - Foreign.mp3" без тегов
    # → has("youtube", id), has("yandex", "42"), entries() длиной 2, tagged флаги верные
async def test_renamed_tagged_file_found_after_refresh(...)
async def test_skips_broken_files(...):  # b"" и мусор в .mp3/.m4a → refresh без исключения, 0 записей
def test_path_for_drops_deleted_file(...): # put(), удалить файл → path_for is None, entries() пуст
def test_load_cached_skips_tag_reads(...):
    # refresh → новый LibraryIndex с тем же cache_path → load_cached(); monkeypatch read_identity бросить AssertionError;
    # has(...) True, is_ready False; затем refresh() без изменения файлов не вызывает read_identity
def test_cache_for_other_music_dir_ignored(...)
def test_corrupt_cache_is_empty(...)
async def test_tagged_wins_over_legacy_same_id(...)
async def test_listener_called_after_refresh(...)
def test_has_without_source(...)
```

- [ ] **Step 2: Run** `poetry run pytest tests/test_library_index.py -v` — FAIL.
- [ ] **Step 3: Implement** `library_index.py` (внутри `threading.Lock` вокруг словаря; ready — `asyncio.Event`, создавать лениво в running loop).
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat: library index of downloaded tracks by embedded tags`

---

### Task 4: Человеческие имена файлов

**Files:**
- Modify: `src/quantis/providers/path_provider.py`
- Test: `tests/test_human_names.py`

**Interfaces:**
- Consumes: `read_identity` (Task 1)
- Produces: `PathProvider.human_track_path(self, artist: str, title: str, ext: str, *, owner: tuple[str, str] | None = None) -> Path` — `{artist} - {title}.{ext}` в `music_folder()`; если файл существует и его `read_identity` не совпадает с `owner` (source, id) → ` (2)`, ` (3)`…; если совпадает — возвращает этот же путь. Ограничение: имя без суффикса ≤ 150 символов (обрезка по title, затем artist; `…` не добавлять). Зарезервированные имена Windows (`CON PRN AUX NUL COM1-9 LPT1-9`, без учёта регистра) → добавить `_`. Пустые artist/title → `unknown` (как `_sanitize_filename_part`).

- [ ] **Step 1: Write the failing tests**

```python
def test_basic_name(provider): assert provider.human_track_path("Artist", "Song", "mp3").name == "Artist - Song.mp3"
def test_invalid_chars(provider): # 'AC/DC', 'Who? "Me"' → 'AC_DC - Who_ _Me_.mp3'
def test_reserved_names(provider): # artist="", title="CON"? → имя не равно reserved; "nul - x" ok
def test_trailing_dot_and_emoji(provider): # "Song." → "… - Song.mp3"; "🔥" сохраняется
def test_long_name_capped(provider): # artist 300 символов → len(path.stem) <= 150
def test_collision_with_foreign_file(provider, tmp_path): # существующий чужой "Artist - Song.mp3" → "Artist - Song (2).mp3"
def test_same_owner_reuses_path(provider, tmp_path): # файл с тегами youtube/x и owner=("youtube","x") → тот же путь
```

- [ ] **Step 2: Run** `poetry run pytest tests/test_human_names.py -v` — FAIL.
- [ ] **Step 3: Implement** `human_track_path`; `get_track_path` (старый шаблон) не трогать — он остаётся временным именем при скачивании.
- [ ] **Step 4: Run** вместе с `tests/test_find_track_file.py` — PASS.
- [ ] **Step 5: Commit** `feat: human-readable track file names`

---

### Task 5: Загрузчики возвращают файл и метаданные

**Files:**
- Modify: `src/quantis/services/async_downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `TrackMeta`, `source_url` (Task 1)
- Produces:
  - `@dataclass class DownloadedAudio: path: Path; meta: TrackMeta`
  - У `AsyncYandexDownloader`, `AsyncYoutubeDownloader`, `AsyncSoundCloudDownloader` и `AsyncDownloader`: `async download_track(track) -> DownloadedAudio | None` (None при неудаче, исключения не наружу)
  - Они же: `async fetch_meta(track) -> TrackMeta | None` — метаданные без скачивания (для Task 8)
  - Чистые функции: `meta_from_yandex(track: Track, ya_track: Any) -> TrackMeta`, `meta_from_ydl(track: Track, info: dict) -> TrackMeta`
  - `sync_download(...)` у YouTube/SoundCloud возвращает `info: dict` (результат `extract_info`)

Правила метаданных: title/artist — из Quantis `Track` (уже очищены `strip_youtube_stats`). Яндекс: `ya_track.albums[0]` → `title`, `year`, `genre`, `track_position.index`, `artists` альбома → album_artist (через `", "`); если `albums` пуст — поля пустые. yt-dlp: `album`, `genre`, `release_year`, иначе `int(upload_date[:4])`, `track_number`; `webpage_url` не используем — ссылка из `source_url`. Путь файла из yt-dlp: `info["requested_downloads"][0]["filepath"]`, суффикс должен быть в `_AUDIO_EXTENSIONS`, иначе None. `extension` у `YoutubeTrack`/`SoundCloudTrack` выставлять из пути.

Баг из спеки: `_apply_downloaded_extension` с `Path(self.path_provider.MUSIC_FOLDER)` удаляется (путь теперь из info). Нужен ли он ещё где-то — проверить `grep`, удалить оба метода.

- [ ] **Step 1: Write the failing tests**

```python
def test_meta_from_yandex_full(): # fake ya_track с albums[0](title="Alb", year=2020, genre="pop", track_position.index=5, artists=[name "X"])
    # → TrackMeta(album="Alb", year=2020, genre="pop", track_number=5, album_artist="X", source_url="https://music.yandex.ru/track/1")
def test_meta_from_yandex_no_albums(): # albums=[] → album=="" and year is None
def test_meta_from_ydl_youtube(): # info {"album": "A", "release_year": 2019} → year 2019, genre ""
def test_meta_from_ydl_soundcloud_upload_date(): # {"genre": "House", "upload_date": "20180102"} → year 2018, genre "House"
async def test_youtube_download_returns_path_from_info(tmp_path):
    # patch sync_download → создаёт tmp_path/"vid_T_A.m4a" и возвращает {"requested_downloads": [{"filepath": str(...)}]}
    # → result.path == файл, track.extension == "m4a"; PathProvider.MUSIC_FOLDER = None (как в проде) не ломает
async def test_youtube_download_failure_returns_none(): # оба attempt бросают → None
```
Обновить существующие `test_download_track_skips_video_when_wallpaper_off` / `..._on`: `_download_audio` теперь возвращает `DownloadedAudio | None`.

- [ ] **Step 2: Run** `poetry run pytest tests/test_downloader.py -v` — FAIL.
- [ ] **Step 3: Implement.** Яндекс: путь — `get_track_path(track)` (mp3), объект трека от `client.tracks` уже есть — из него `meta_from_yandex`; `fetch_meta` — тот же `client.tracks` без скачивания. YouTube/SoundCloud `fetch_meta` — `extract_info(download=False)` в executor (для YouTube с теми же двумя наборами opts).
- [ ] **Step 4: Run** `poetry run pytest tests/test_downloader.py tests/test_soundcloud.py -v` — PASS.
- [ ] **Step 5: Commit** `refactor: downloaders return file path and metadata; fix youtube MUSIC_FOLDER bug`

---

### Task 6: Конвейер `download_full`

**Files:**
- Modify: `src/quantis/services/async_downloader.py` (класс `AsyncDownloader`)
- Test: `tests/test_download_full.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4, 5
- Produces: `AsyncDownloader.__init__(self, index: LibraryIndex | None = None)` и `async AsyncDownloader.download_full(track: Track) -> bool`

Алгоритм:
1. Дедупликация параллельных вызовов по ключу `f"{source}:{id}"` (как `_cover_tasks`).
2. `await index.wait_ready()`.
3. Если `index.path_for(source, id)` есть (любая запись, tagged или legacy) → `ensure_cover`, `track.downloaded = True`, вернуть True; файл не трогать.
4. `audio = await self.download_track(track)`; None → False.
5. `cover_ok = await self.ensure_cover(track)`.
6. `write_tags(audio.path, audio.meta, cover_path if cover_ok else None)`; затем проверка `read_identity(audio.path)` совпадает по source/id; затем `target = provider.human_track_path(meta.artist, meta.title, ext, owner=(source, id))`, `audio.path.replace(target)`. Любая ошибка этого шага → `logger.warning`, файл остаётся на `audio.path`.
7. `index.put(итоговый путь)`, `track.downloaded = True`, True.

- [ ] **Step 1: Write the failing tests** (fake per-source `download_track`, реальные фикстуры из Task 1, индекс на `tmp_path`)

```python
async def test_full_pipeline_tags_and_renames(...):  # итог: "A - T.mp3", read_identity совпадает, index.path_for → он, старого имени нет
async def test_tag_failure_keeps_legacy_name_and_succeeds(...):  # write_tags бросает → True, файл "id_T_A.mp3", index.has
async def test_cover_missing_still_tags(...)
async def test_existing_tagged_file_untouched(...):  # файл с тегами, пользователь переименовал в "My name.mp3" → True, download_track не вызван, mtime не изменился
async def test_download_failure_returns_false(...):  # track.downloaded остаётся False
async def test_concurrent_calls_single_file(...):  # gather(download_full(t), download_full(t)) → download_track вызван 1 раз, нет "(2)"
async def test_waits_for_index_ready(...):  # индекс не ready → download_track не вызван, пока refresh не завершился
```

- [ ] **Step 2: Run** `poetry run pytest tests/test_download_full.py -v` — FAIL.
- [ ] **Step 3: Implement** `download_full`.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat: download pipeline embeds tags and renames files`

---

### Task 7: Перевести поиск файлов и UI на индекс

**Files:**
- Modify: `src/quantis/providers/TrackManager.py` (`is_downloaded`, `ids`, `_load_ids`)
- Modify: `src/quantis/providers/path_provider.py` (`find_track_file`)
- Modify: `src/quantis/models/playlist.py` (`DownloadPlaylist.delete_track`, `get_tracks_from_music_dir`)
- Modify: `src/quantis/ui/views/player_bar.py:526-535`, `src/quantis/ui/viewmodels/search_vm.py:282-300`, `src/quantis/ui/viewmodels/home_vm.py:886-905`
- Modify: `src/quantis/main.py` (старт), `src/quantis/ui/main_window.py` (слушатель), `src/quantis/ui/views/settings_page.py` (`_on_pick_music_dir`, `_on_reset_music_dir`)
- Test: `tests/test_find_track_file.py`, `tests/test_player_bar.py`, `tests/test_search_integration.py`, новый `tests/test_index_consumers.py`

**Interfaces:**
- Consumes: `LibraryIndex` (Task 3), `download_full` (Task 6)

Поведение:
- `TrackManager.is_downloaded(track_id, source)` → `LibraryIndex.instance().has(source, str(track_id))` (soundcloud id нормализовать через `parse_storage_id`). `ids`/`_load_ids` удалить, если нигде больше не используются (проверить grep).
- `find_track_file`: сначала `index.path_for`, затем прежний поиск (точное имя, glob по префиксу) — для времени до готовности индекса.
- `delete_track`: удалить `index.path_for(...)` + прежние кандидаты, `index.discard`, обложку как сейчас.
- `get_tracks_from_music_dir()`: строит `Track` из `index.entries()` (title/author из записи); тип трека по `entry.source`, `extension` из суффикса.
- Три места скачивания: `ok = await downloader.download_full(track)`; `downloaded`/обновление UI — только при `ok`; при `not ok` — то же, что сейчас при исключении (player_bar: `_on_download_finished(track, False)` → кнопка снова активна; search/home: снять loading, без `downloaded = True`).
- Старт: `main.py` до `Quantis(bundle)` — `LibraryIndex.instance().load_cached()`; в `_post_show` — `bridge.schedule(LibraryIndex.instance().refresh())`.
- `main_window`: `LibraryIndex.instance().add_listener(lambda: self._bridge.invoke_main(lambda: self._home_vm.refresh_downloaded(self._bridge)))`.
- Смена папки в настройках: после `set_music_dir` — `index.reset()` и `schedule(index.refresh(), bridge)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_is_downloaded_uses_index_for_human_named_file(...):  # tagged "A - T.mp3" → TrackManager(...).is_downloaded("x", "youtube")
def test_find_track_file_human_name(...):
def test_delete_track_removes_human_named_file(...):
def test_downloaded_playlist_titles_from_tags(...):  # title из тегов, не из имени
async def test_player_bar_failed_download_reenables_button(...):  # download_full → False: track.downloaded False, кнопка enabled
async def test_search_vm_marks_downloaded_only_on_success(...)
```
Существующие тесты `test_find_track_file.py` должны остаться зелёными без правок (запасной путь).

- [ ] **Step 2: Run** `poetry run pytest tests/test_index_consumers.py tests/test_find_track_file.py tests/test_player_bar.py -v` — новые FAIL.
- [ ] **Step 3: Implement** по списку выше.
- [ ] **Step 4: Run полный набор** `poetry run pytest -q` — PASS.
- [ ] **Step 5: Ручная проверка** через скилл `run`: запустить приложение, скачать по треку из Яндекса, YouTube и SoundCloud → в папке `Исполнитель - Название.ext`, трек в «Скачанных», воспроизводится, удаляется.
- [ ] **Step 6: Commit** `feat: find downloaded tracks through the library index`

---

### Task 8: Миграция старых файлов и кнопка в настройках

**Files:**
- Create: `src/quantis/services/library_retag.py`
- Modify: `src/quantis/ui/views/settings_page.py` (строка «Папка для скачанной музыки», `music_buttons`), `src/quantis/ui/main_window.py:589` (передать `self._bundle.music`)
- Test: `tests/test_library_retag.py`

**Interfaces:**
- Consumes: `fetch_meta`, `ensure_cover`, `write_tags`, `read_identity`, `human_track_path`, `LibraryIndex`
- Produces:
  - `@dataclass class RetagReport: done: int = 0; already: int = 0; skipped: int = 0`
  - `async def retag_legacy(downloader: AsyncDownloader, index: LibraryIndex, on_progress: Callable[[int, int], None] | None = None) -> RetagReport`
  - `SettingsPage.__init__(..., music: MusicService | None = None)`

Алгоритм `retag_legacy`: `await index.refresh()`; по `index.entries()` последовательно (не параллельно — бережём лимит Яндекса):
- `entry.tagged` → `already += 1`, файл не трогать.
- иначе `meta = await downloader.fetch_meta(track)`; None/исключение → `TrackMeta(source, id, title=entry.title, artist=entry.author, source_url=source_url(...))`.
- `ensure_cover(track)`; `write_tags`; `read_identity` совпадает по source/id и title непустой → `human_track_path(..., owner=...)` + `replace` + `index.discard(old)` + `index.put(new)` → `done += 1`; иначе `skipped += 1` (имя не меняется).
- `on_progress(i, total)` после каждого файла.

UI: кнопка `"Записать теги"` в `music_buttons` (тот же `settingsButton`), под кнопками `QLabel` статуса (`settingsRowDesc`). Описание строки дополнить: «Кнопка «Записать теги» вшивает обложку и данные в ранее скачанные треки и называет файлы «Исполнитель - Название».» Во время работы кнопка disabled, статус «Обработано N из M»; в конце «Готово: N, уже были: A, пропущено: K». Прогресс в UI — через `bridge.invoke_main`. Без `music` кнопка скрыта.

- [ ] **Step 1: Write the failing tests**

```python
async def test_retag_legacy_file(...):  # "42_Song_A.mp3", fetch_meta → TrackMeta(album="X") → "A - Song.mp3", тег album "X", report.done == 1
async def test_already_tagged_untouched(...):  # tagged "My edit.mp3" → already == 1, mtime/имя прежние
async def test_fetch_meta_failure_uses_local_data(...):  # fetch_meta бросает → всё равно done, теги title/artist из имени
async def test_tag_write_failure_skips_without_rename(...):  # write_tags бросает → skipped == 1, имя "42_Song_A.mp3"
async def test_progress_reported(...):  # 3 файла → on_progress вызван (1,3),(2,3),(3,3)
async def test_second_run_is_noop(...):  # повторный вызов → done 0, already == прежний done
```

- [ ] **Step 2: Run** `poetry run pytest tests/test_library_retag.py -v` — FAIL.
- [ ] **Step 3: Implement** `retag_legacy` и кнопку.
- [ ] **Step 4: Run** `poetry run pytest -q` — PASS.
- [ ] **Step 5: Ручная проверка** (скилл `run`): положить в папку копии старых файлов `ID_…`, нажать кнопку → прогресс, итог, файлы переименованы, «Скачанные» обновились; повторное нажатие → «уже были».
- [ ] **Step 6: Commit** `feat: settings button to tag and rename legacy downloads`

---

### Task 9: Сборка

**Files:**
- Modify: `packaging/pyinstaller/main.spec` (если нужно)
- Test: `packaging/scripts/smoke_bundle.sh`

- [ ] **Step 1:** Проверить, что `mutagen` попадает в сборку: собрать (`docs/build.md`), в собранном приложении скачать трек → теги записаны. Если модуль не найден — `hiddenimports += collect_submodules("mutagen")` рядом с `quantis.ui.themes`.
- [ ] **Step 2:** `poetry run ruff check src tests && poetry run mypy src` — без новых ошибок.
- [ ] **Step 3: Commit** `build: bundle mutagen` (если были изменения).
