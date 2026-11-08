# Магазин плагинов, аккаунт Quantis и Together на токенах — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Плагины ставятся и обновляются из магазина на сайте Quantis по токену аккаунта; левая панель без плейлистов с разделом «Плагины»; Together работает на том же токене.

**Architecture:** На сайте — DRF: токены, JSON API магазина и комнат, доступ к комнатам за пользователем, токен в WebSocket. В программе — сервис аккаунта (токен в keyring), клиент магазина, установка/обновление через реестр плагинов без перезапуска, новая левая панель и менеджер с вкладками. Together берёт адрес и токен у хоста.

**Tech Stack:** Сайт: Django 6, DRF 3.18 (`rest_framework.authtoken`), Channels 4. Программа: Python 3.14, PySide6, aiohttp, keyring, pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-plugin-marketplace-design.md`

## Global Constraints

- Два репозитория: программа `~/projects/Quantis` (ветка `feat/plugin-marketplace`), сайт `~/projects/QuantisSite` (создать ветку `feat/api-tokens` от `main`).
- В сайте есть чужие незакоммиченные правки `docker-compose.yml`, `nginx.conf`, `quantis_site/quantis_site/settings.py` — не откатывать, не коммитить их куски, не относящиеся к задаче (`git add -p` для settings.py).
- Тесты сайта: `cd ~/projects/QuantisSite/quantis_site && DEBUG=1 ../.venv/bin/python manage.py test <app>`.
- Тесты программы: `cd ~/projects/Quantis && uv run pytest -q <path>`; линт: `uv run ruff check src tests`.
- Тесты Together: `uv run python -P -m pytest plugins_dir/together/tests -q`. `plugins_dir/` в `.gitignore` — Together не коммитится.
- Адрес сервера по умолчанию: `https://212-87-190-34.nip.io`.
- Формат id плагина: `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`; лимит zip — 32 МБ.
- Заголовок авторизации: `Authorization: Token <key>`.
- Пароль от сайта нигде не сохраняется; токен — только в keyring.
- Тексты UI — по-русски, в стиле существующих страниц; ошибки — уведомлениями, без модальных окон (кроме подтверждения удаления).
- Коммиты: сообщения по-русски в стиле репозитория (`feat(scope): …`), в конце строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Старые клиенты (вход через форму) не поддерживаются.

## Review Focus

1. Сервер недоступен или отвечает долго при входе, загрузке магазина, скачивании → понятная ошибка в уведомлении, программа не виснет и не падает (таймауты aiohttp). Тесты: Task 5 `test_login_server_down`, Task 7 `test_fetch_store_network_error`.
2. Токен отозвали на сайте посреди сессии (401 на любом запросе) → аккаунт считается вышедшим, магазин и Together показывают «Войдите». Тест: Task 5 `test_401_logs_out`, Task 7 `test_fetch_store_401_raises_auth_error`.
3. Новая версия активного плагина падает при импорте → откат на старые файлы, старая версия снова включена. Тест: Task 8 `test_update_rolls_back_when_new_version_fails`.
4. Обрыв на середине скачивания или подмена файла → частичный файл удалён, ничего не установлено. Тест: Task 7 `test_download_rejects_sha_mismatch`, `test_download_rejects_truncated`.
5. keyring недоступен (Linux без secret-service) → вход работает до перезапуска (токен в памяти), в уведомлении сказано, что токен не сохранён. Тест: Task 5 `test_login_without_keyring_keeps_token_in_memory`.

---

## Часть 1. Сайт

### Task 1: Токены DRF и вход по API

**Files:**
- Modify: `quantis_site/quantis_site/settings.py` (INSTALLED_APPS, REST_FRAMEWORK)
- Modify: `quantis_site/quantis_site/urls.py`
- Create: `quantis_site/api/__init__.py`, `apps.py`, `urls.py`, `views.py`, `tests.py`

**Interfaces:**
- Produces: URL-префикс `api/` → `api.urls`; `POST /api/auth/token/` `{username, password}` → 200 `{"token", "username"}` / 400 `{"detail"}`; `DELETE /api/auth/token/` → 204; `GET /api/auth/me/` → `{"username"}`; 401 без токена.
- Produces (settings): `REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": [TokenAuthentication, SessionAuthentication], "DEFAULT_PERMISSION_CLASSES": [IsAuthenticated], "DEFAULT_THROTTLE_RATES": {"login": "10/min"}}`.

- [ ] **Step 1:** `cd ~/projects/QuantisSite && git checkout -b feat/api-tokens`.
- [ ] **Step 2: Тесты** в `api/tests.py` (APITestCase):
  - `test_token_login_returns_token` — POST верных данных → 200, `token` непустой, `username == "u"`.
  - `test_token_login_wrong_password` → 400, в ответе `detail`.
  - `test_me_requires_token` → без заголовка 401; с `HTTP_AUTHORIZATION="Token <key>"` → `{"username": "u"}`.
  - `test_logout_deletes_token` → DELETE с токеном 204, затем `/api/auth/me/` с тем же токеном 401.
  - `test_login_is_throttled` → 11-й POST за минуту → 429 (очистить `cache` в setUp).
- [ ] **Step 3:** запустить `... manage.py test api` → FAIL (нет приложения).
- [ ] **Step 4:** добавить `rest_framework`, `rest_framework.authtoken`, `api` в INSTALLED_APPS и `REST_FRAMEWORK`; `TokenView(APIView)` с `post` (`AllowAny`, `ScopedRateThrottle`, `throttle_scope = "login"`, `authenticate()` → `Token.objects.get_or_create`) и `delete` (удаляет `request.auth`); `MeView`; `path("api/", include("api.urls"))` в корневых urls **перед** `include(rooms.urls)`.
- [ ] **Step 5:** `manage.py makemigrations` не нужен для api (моделей нет); `manage.py test api` → PASS; `manage.py test` целиком → PASS.
- [ ] **Step 6: Commit** `feat(api): токены DRF — вход, выход, me` (settings.py — только свои хунки).

### Task 2: API магазина плагинов

**Files:**
- Modify: `quantis_site/plugins/models.py`, `admin.py`, `views.py` (вынести отдачу файла)
- Create: `quantis_site/plugins/manifest.py`, `quantis_site/plugins/files.py`, миграция
- Modify: `quantis_site/api/urls.py`, `api/views.py`; Test: `quantis_site/plugins/tests.py`

**Interfaces:**
- Produces: модель `Plugin` + поля `plugin_id = SlugField(max_length=64, unique=True, null=True, blank=True)`, `sha256 = CharField(max_length=64, blank=True)`, `size = PositiveIntegerField(default=0)`.
- Produces: `plugins.manifest.read_plugin_zip(fileobj) -> PluginManifest` (dataclass `plugin_id, title, version, description, author, sha256, size`), бросает `django.core.exceptions.ValidationError` с русским текстом.
- Produces: `plugins.files.plugin_file_response(plugin) -> HttpResponse` (X-Accel-Redirect при `not DEBUG`, иначе FileResponse) — им пользуются и HTML-скачивание, и API.
- Produces: `GET /api/plugins/` → `[{"id", "title", "version", "description", "author", "cover_url", "download_url", "size", "sha256", "updated_at"}]` (только `is_active` и `plugin_id` не пустой, абсолютные URL); `GET /api/plugins/<plugin_id>/download/` → zip.

- [ ] **Step 1: Тесты** (`plugins/tests.py`, zip собирать в памяти через `zipfile`):
  - `test_read_zip_root_layout` и `test_read_zip_single_folder_layout` → поля из манифеста, `size` = длина байтов, `sha256` = `hashlib.sha256(data).hexdigest()`.
  - `test_read_zip_rejects` — параметризовать подтестами: не zip; нет `plugin.py`; нет `manifest.json`; битый JSON; нет `version`; id `"../x"`; размер > 32 МБ (подменить лимит константой `MAX_ZIP_BYTES` через `override`/патч) → `ValidationError`.
  - `test_admin_form_fills_fields_from_manifest` — форма админки с файлом → сохранённая запись с `title/version/plugin_id/sha256`.
  - `test_admin_form_rejects_duplicate_plugin_id` — вторая запись с тем же id → ошибка формы «уже есть — загрузите новую версию в его запись».
  - `test_api_list_requires_token` (401) и `test_api_list_shape` (ключи как выше, неактивные и без `plugin_id` не попадают).
  - `test_api_download_requires_token` (401) и `test_api_download_returns_file` (DEBUG → тело = байты zip).
- [ ] **Step 2:** `manage.py test plugins` → FAIL.
- [ ] **Step 3:** реализовать: `manifest.py` (лимит `MAX_ZIP_BYTES = 32 * 1024 * 1024`, поиск корня как в программе: корень или единственная папка), поля модели + `makemigrations plugins`, `PluginAdminForm(ModelForm)` с полями `file, cover_image, is_active`; `clean_file` читает манифест, `clean` проверяет уникальность `plugin_id` (кроме самой записи), `save` заполняет поля. `PluginAdmin.form = PluginAdminForm`, `list_display` + `plugin_id`. API-вью в `api/views.py` (`ListAPIView` с простым сериализатором или `APIView`), скачивание через `plugin_file_response`. `DownloadPluginView` переписать на тот же хелпер.
- [ ] **Step 4:** `manage.py test plugins api` → PASS; весь `manage.py test` → PASS.
- [ ] **Step 5: Commit** `feat(plugins): магазин — манифест из zip, API списка и скачивания`.

### Task 3: Доступ к комнатам за пользователем и API комнат на токене

**Files:**
- Modify: `quantis_site/rooms/models.py`, `views.py`, `api.py`, `urls.py`, `consumers.py`; миграция
- Test: `quantis_site/rooms/tests.py` (новый класс `RoomAccessTests`)

**Interfaces:**
- Produces: модель `RoomAccess(room FK Room, user FK User, password_version PositiveIntegerField)`, `unique_together = (room, user)`; `Room.has_access(user) -> bool` (комната без пароля → True; иначе запись с `password_version == room.password_version`); `Room.grant_access(user) -> None` (`update_or_create`). Сессионные `access_session_key/grant_access(session)` удалить.
- Produces: `GET /api/rooms/` — DRF, тот же JSON, что сейчас (`has_access` через пользователя); `POST /api/rooms/<id>/unlock/` `{password}` → 204 / 403 `{"detail": "Неверный пароль"}` / 404.

- [ ] **Step 1: Тесты:**
  - `test_has_access_per_user_and_password_version` — grant → True; смена пароля (`set_password` + save) → False; другой пользователь → False; комната без пароля → True.
  - `test_api_rooms_with_token` → 200, `has_access` False для запароленной; без токена → 401.
  - `test_unlock_with_token` → неверный пароль 403, верный 204, затем `/api/rooms/` даёт `has_access: True`.
  - `test_web_password_form_grants_user_access` — POST формы `/rooms/<id>/password/` → `RoomAccess` создан.
  - `test_ws_requires_user_access` — WebsocketCommunicator к запароленной комнате без доступа → закрытие 4403; после `grant_access(user)` → подключается (по образцу `RoomQueueTests.connect`).
- [ ] **Step 2:** `manage.py test rooms` → новые FAIL.
- [ ] **Step 3:** реализовать модель + миграцию, перевести `PasswordRoomView`, `RoomDetailView`, `rooms_list` (→ `@api_view(["GET"])`), `load_room_if_allowed` (`room.has_access(self.user)`), вью `unlock`. Проверку хеша пароля из `PasswordRoomView.form_valid` (апгрейд старого хеша) вынести в `Room.verify_password(raw) -> bool` и звать из обоих мест.
- [ ] **Step 4:** `manage.py test` → PASS (старые `RoomQueueTests` тоже).
- [ ] **Step 5: Commit** `feat(rooms): доступ к комнате за пользователем, API комнат и unlock на токене`.

### Task 4: Токен в WebSocket и инструкция по выкладке

**Files:**
- Create: `quantis_site/rooms/ws_auth.py`
- Modify: `quantis_site/quantis_site/asgi.py`, `README.md` (раздел «Выкладка: API и токены»)
- Test: `quantis_site/rooms/tests.py` (`WsTokenAuthTests`)

**Interfaces:**
- Produces: `TokenAuthMiddleware(inner)` (ASGI): если в `scope["headers"]` есть `authorization: Token <key>` — `scope["user"]` = владелец токена или `AnonymousUser` при неверном ключе (сессию не используем); без заголовка — scope не трогает. В `asgi.py`: `BrowserOrNativeOriginValidator(AuthMiddlewareStack(TokenAuthMiddleware(URLRouter(ws_urlpatterns))))`.

- [ ] **Step 1: Тесты:** `test_ws_token_header_authenticates` (communicator с `headers=[(b"authorization", b"Token <key>")]`, приложение = `TokenAuthMiddleware(URLRouter(ws_urlpatterns))` → history получен, `username` верный); `test_ws_bad_token_rejected` → закрытие 4401; `test_ws_without_header_keeps_scope_user` (scope user выставлен заранее, как браузер через сессию → подключается).
- [ ] **Step 2:** FAIL → **Step 3:** реализовать → **Step 4:** `manage.py test` PASS.
- [ ] **Step 5:** README: шаги выкладки — `git pull`, `docker compose build web` (имя сервиса взять из `docker-compose.yml`), `docker compose run --rm web python manage.py migrate`, `docker compose up -d`; после выкладки перезалить zip плагинов в админке, чтобы у записей появился `plugin_id`.
- [ ] **Step 6: Commit** `feat(rooms): токен в WebSocket; инструкция по выкладке`.

---

## Часть 2. Программа

### Task 5: Сервис аккаунта Quantis

**Files:**
- Create: `src/quantis/services/quantis_account.py`
- Modify: `src/quantis/config/constants.py` (`SERVICE_NAME_QUANTIS = "Quantis-Site"` или в стиле соседних), `src/quantis/config/credentials.py` (`save_quantis_token(token: str) -> None`, `load_quantis_token() -> str`, `delete_quantis_token() -> None` — как Яндекс), `src/quantis/core/plugin_host.py`, `src/quantis/core/bootstrap.py`, `src/quantis/plugins/event_bus.py`
- Test: `tests/test_quantis_account.py`

**Interfaces:**
- Produces: `class AccountError(Exception)`; `class QuantisAccount(QObject)`: `changed = Signal()`; `DEFAULT_SERVER = "https://212-87-190-34.nip.io"`; свойства `server_url: str`, `username: str`, `token: str`, `is_logged_in: bool`, `token_persisted: bool`; `set_server_url(url: str) -> None`; `async login(username: str, password: str) -> None` (бросает `AccountError` с текстом для пользователя); `async logout() -> None`; `async verify() -> bool`; `auth_headers() -> dict[str, str]`; `handle_unauthorized() -> None` (забыть токен, `changed`). Имя и адрес — QSettings `ReallyFun/Quantis`, ключи `account/username`, `account/server`. Таймаут запросов — 15 с.
- Produces: `PluginHost.account: QuantisAccount | None = None`; `PluginHost.open_accounts() -> None` → `event_bus.accounts_requested.emit()`; `EventBus.accounts_requested = Signal()`; `ApplicationBundle.account`.

- [ ] **Step 1: Тесты** (aiohttp-сервер на `aiohttp.test_utils`/`TestServer` или подмена сессии; keyring — monkeypatch функций credentials):
  - `test_login_saves_token_not_password` — после входа `token` есть, `save_quantis_token` вызван с токеном, в QSettings нет пароля (проверить все ключи группы `account`).
  - `test_login_wrong_password` → `AccountError`, `is_logged_in` False.
  - `test_login_server_down` (адрес на закрытый порт) → `AccountError` с текстом «Сервер недоступен…», без зависания.
  - `test_logout_forgets_token_even_if_server_down`.
  - `test_401_logs_out` — `verify()` при 401 → False, токен удалён, `changed` эмитнут.
  - `test_login_without_keyring_keeps_token_in_memory` — `save_quantis_token` бросает `KeyringError` → `is_logged_in` True, `token_persisted` False.
  - `test_auth_headers` → `{"Authorization": "Token abc"}`; без входа → `{}`.
- [ ] **Step 2:** `uv run pytest -q tests/test_quantis_account.py` → FAIL.
- [ ] **Step 3:** реализовать сервис, хелперы credentials, поле хоста и сигнал; в `bootstrap` создать аккаунт, передать в `PluginHost` и `ApplicationBundle`, при старте `bridge.schedule(account.verify())`, если есть токен. В `main_window` подключить `accounts_requested` к переходу на `PAGE_MEMBER`.
- [ ] **Step 4:** тесты + весь `uv run pytest -q` → PASS.
- [ ] **Step 5: Commit** `feat(account): аккаунт Quantis — вход по токену, хранение в keyring`.

### Task 6: Карточка «Quantis» в «Аккаунтах»

**Files:**
- Modify: `src/quantis/ui/views/member_page.py` (`MemberPage(bridge, account)`), `src/quantis/ui/main_window.py:699`
- Test: `tests/test_member_page_quantis.py`

**Interfaces:**
- Consumes: `QuantisAccount` (Task 5).
- Produces: `_QuantisCard(account, bridge)` внутри `member_page.py`: вошли — «Вы вошли как <имя>» + «Выйти»; не вошли — поля «Логин», «Пароль» (`EchoMode.Password`), «Войти», текст ошибки, ссылка «Нет аккаунта? Открыть сайт» (`QDesktopServices.openUrl(account.server_url)`), свёрнутый блок «Дополнительно» с полем адреса сервера. Если `token_persisted` False — подпись «Токен не сохранён: системное хранилище паролей недоступно».

- [ ] **Step 1: Тесты** (фейковый аккаунт с `changed`, offscreen): `test_card_shows_login_form_when_logged_out`; `test_card_switches_on_changed` (после `changed` с `is_logged_in=True` видно имя и «Выйти»); `test_login_error_is_shown` (фейк бросает `AccountError("Неверный логин или пароль")` → текст на карточке); `test_password_field_cleared_after_login`.
- [ ] **Step 2:** FAIL → **Step 3:** реализовать в стиле `_ServiceCard` → **Step 4:** PASS + весь pytest.
- [ ] **Step 5: Commit** `feat(accounts): карточка аккаунта Quantis`.

### Task 7: Клиент магазина

**Files:**
- Create: `src/quantis/plugins/store.py`
- Test: `tests/test_plugin_store.py`

**Interfaces:**
- Consumes: `QuantisAccount.server_url`, `auth_headers()`, `handle_unauthorized()`.
- Produces: `@dataclass(frozen=True) StorePlugin(plugin_id: str, title: str, version: str, description: str, author: str, cover_url: str, download_url: str, size: int, sha256: str)`; `class StoreError(Exception)`; `class StoreAuthError(StoreError)`; `async fetch_store(account) -> list[StorePlugin]` (401 → `handle_unauthorized()` + `StoreAuthError`); `async download_plugin(account, item: StorePlugin, dest_dir: Path) -> Path` (проверка `size` ≤ 32 МБ и равенства, `sha256`; при любой ошибке частичный файл удаляется; только https, кроме `http://127.0.0.1`/`localhost` для тестов); `is_newer(remote: str, local: str) -> bool` (числовое сравнение частей, `1.10.0 > 1.9.0`, нечисловые хвосты — строкой после чисел; пустая/битая локальная версия → True); `store_action(item: StorePlugin, installed_version: str | None) -> Literal["install", "update", "installed"]`.

- [ ] **Step 1: Тесты:** `test_is_newer` (таблица: `("1.10.0","1.9.0",True)`, `("1.0","1.0.0",False)`, `("0.5.1","0.5.0",True)`, `("1.0.0","",True)`, `("1.0.0","2.0",False)`); `test_store_action`; `test_fetch_store_parses_items`; `test_fetch_store_401_raises_auth_error` (и `handle_unauthorized` вызван); `test_fetch_store_network_error` → `StoreError`; `test_download_ok`; `test_download_rejects_sha_mismatch`; `test_download_rejects_truncated` (сервер отдаёт меньше `size`) — в обоих файла в `dest_dir` нет.
- [ ] **Step 2:** FAIL → **Step 3:** реализовать (aiohttp, таймаут 60 с на скачивание) → **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(plugins): клиент магазина — список, скачивание с проверкой sha256`.

### Task 8: Установка, обновление и удаление без перезапуска

**Files:**
- Modify: `src/quantis/plugins/installer.py`, `src/quantis/plugins/loader.py`, `src/quantis/plugins/registry.py`
- Test: `tests/test_plugin_install_update.py`

**Interfaces:**
- Produces (installer): `install_plugin_from_zip(zip_path, *, overwrite: bool = True, plugin_id: str | None = None) -> str` — при `plugin_id` папка называется им, а `id` в `manifest.json` обязан совпасть (иначе `PluginInstallError("id в архиве (…) не совпадает с магазином (…)")`); замена атомарная: распаковка рядом во временную папку, старая → `<id>.bak`, новая → `<id>`, `.bak` удаляется только после успеха; `restore_backup(plugin_id: str) -> bool`, `drop_backup(plugin_id: str) -> None`.
- Produces (loader): `PluginLoader.read_meta(plugin_dir: Path) -> PluginMeta` (публичная обёртка `_read_meta`); `PluginLoader.forget_modules(plugin_id: str, plugin_dir: Path) -> None` — убирает `quantis_plugins.<id>`, `quantis_plugins.<id>.*` и все модули с origin внутри `plugin_dir`.
- Produces (registry): `async install(zip_path: Path, plugin_id: str) -> bool` (был активен → disable; установить; forget_modules; перечитать meta в `_infos`; enable (новый или был активен); при неудаче enable после обновления — `restore_backup`, forget, перечитать, enable старой, вернуть False; при успехе `drop_backup`); `async uninstall(plugin_id: str) -> None` (disable, удалить папку, убрать из `_infos`, `plugin_changed`); `is_bundled(plugin_id: str) -> bool` (папка плагина не в `resolve_plugins_dir()`); `installed_version(plugin_id: str) -> str | None`.

- [ ] **Step 1: Тесты** (`tmp_path` как пользовательская папка через monkeypatch `resolve_plugins_dir` и `plugin_search_dirs`; фейковый host; плагин-образец пишет в `on_load` маркер версии в модульную переменную/файл):
  - `test_install_new_plugin_enables_it`.
  - `test_install_rejects_id_mismatch` — zip с `id: "other"` при `plugin_id="demo"` → `PluginInstallError`, папки нет.
  - `test_update_active_plugin_reloads_new_code` — v1 активен → install v2 → активен, загружен код v2 (маркер «2»), `.bak` нет, настройки QSettings плагина не тронуты.
  - `test_update_rolls_back_when_new_version_fails` — v2 бросает в `on_load`/импорте → `install` False, файлы v1 на месте, активна v1.
  - `test_uninstall_removes_folder_and_info`; `test_bundled_plugin_cannot_be_uninstalled` (`is_bundled` True для папки из второй search dir).
  - `test_user_copy_shadows_bundled` — одинаковое имя папки в обеих search dirs → `discover()` берёт пользовательскую.
- [ ] **Step 2:** FAIL → **Step 3:** реализовать → **Step 4:** PASS + весь pytest.
- [ ] **Step 5: Commit** `feat(plugins): установка и обновление без перезапуска, откат, удаление`.

### Task 9: Проверка обновлений

**Files:**
- Create: `src/quantis/plugins/updates.py`
- Modify: `src/quantis/ui/main_window.py` (создание и запуск)
- Test: `tests/test_plugin_updates.py`

**Interfaces:**
- Consumes: `fetch_store`, `is_newer`, `StorePlugin` (Task 7); `PluginRegistry.installed_version` (Task 8); `QuantisAccount.changed`.
- Produces: `class PluginUpdates(QObject)`: `changed = Signal()`; `store: list[StorePlugin]`; `updates: dict[str, StorePlugin]` (только установленные с более новой версией); `error: str` (последняя ошибка, «» при успехе); `logged_out: bool`; `async refresh() -> None`. Создаётся в `main_window` с аккаунтом и реестром; `refresh` — при старте после `verify`, при `account.changed`, при показе менеджера.

- [ ] **Step 1: Тесты:** `test_refresh_counts_only_newer_installed` (store: a 1.1 при установленной 1.0, b 1.0 при 1.0, c не установлен → `updates == {"a"}`); `test_refresh_logged_out_clears` (`StoreAuthError` → `logged_out` True, `updates` пуст, `changed`); `test_refresh_error_keeps_previous_store` (`StoreError` → `error` заполнен, прежний `store` не стёрт).
- [ ] **Step 2:** FAIL → **Step 3:** реализовать → **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(plugins): проверка обновлений из магазина`.

### Task 10: Левая панель без плейлистов, раздел «Плагины»

**Files:**
- Modify: `src/quantis/ui/views/widgets/side_nav.py`, `src/quantis/ui/main_window.py` (строки ~120–130 `_PAGE_META`, ~224–228 плейлисты), `src/quantis/ui/shortcuts.py:33`
- Test: `tests/test_side_nav.py` (создать, если нет; иначе дополнить)

**Interfaces:**
- Consumes: `PluginUpdates.changed`, `len(updates.updates)` (Task 9).
- Produces: `SideNav.CORE_TOP` без «Плагины»; секция: разделитель, подпись `navSectionLabel` «Плагины», кнопки `nav_items()`, затем кнопка «Менеджер плагинов» (`plugins.svg`, page_id 4); `SideNav.set_updates_count(count: int) -> None` — бейдж числа на кнопке менеджера (0 — скрыт; в свёрнутой панели — точка или число поверх иконки). Удалить `playlist_activated`, `set_playlists`, `_rebuild_playlists`, `_fit_playlists`, `_PlaylistItem`, если не используются в другом месте (grep). `_PAGE_META[PAGE_PLUGINS]` → «Менеджер плагинов»; шорткат Alt+5 — подпись «Менеджер плагинов».

- [ ] **Step 1: Тесты:** `test_no_playlists_section` (нет виджетов с текстом «Плейлисты»); `test_plugins_section_order` (порядок текстов: разделы…, «Плагины», страницы плагинов, «Менеджер плагинов», «Аккаунты», «Настройки» — фейковые `nav_items`); `test_updates_badge` (`set_updates_count(2)` → бейдж «2» видим; `0` → скрыт); `test_plugin_page_removed_from_nav_on_disable` (повторная сборка после изменения `nav_items`).
- [ ] **Step 2:** FAIL → **Step 3:** реализовать; в `main_window` подключить `PluginUpdates.changed` → `set_updates_count` → **Step 4:** PASS + весь pytest.
- [ ] **Step 5:** запустить приложение (`uv run quantis` или как в README) и глазами проверить панель в развёрнутом и свёрнутом виде; скриншот приложить к отчёту.
- [ ] **Step 6: Commit** `feat(nav): раздел «Плагины» вместо плейлистов, менеджер с бейджем обновлений`.

### Task 11: Менеджер плагинов — вкладки «Установленные» и «Магазин»

**Files:**
- Modify: `src/quantis/ui/views/plugins_page.py` (`PluginsPage(bridge, account, updates)`), `src/quantis/ui/main_window.py:691-695`
- Test: `tests/test_plugins_page.py`

**Interfaces:**
- Consumes: `PluginUpdates` (Task 9), `download_plugin`, `store_action` (Task 7), `PluginRegistry.install/uninstall/is_bundled/installed_version` (Task 8), `QuantisAccount`, `PluginHost.open_accounts` / `event_bus.accounts_requested`.
- Produces: страница с `QTabBar`/`QStackedWidget`: «Установленные» (карточки как сейчас + «Обновить до vX», если есть в `updates.updates`; «Удалить» для не-bundled с `QMessageBox.question`; кнопки «Импорт из архива», «Открыть папку»; «Скачать по URL» удалить вместе с `install_plugin_from_url`/`download_plugin_zip`, если больше не используются). «Магазин»: при `logged_out`/не вошли — «Войдите в аккаунт Quantis» + кнопка «Открыть аккаунты»; иначе карточки (обложка через существующую загрузку картинок или `QNetworkAccessManager`, название, автор, версия, описание, кнопка по `store_action`); при `updates.error` — строка ошибки и «Повторить». Во время установки кнопка неактивна с текстом «Установка…»; итог — уведомление «Плагин «X» установлен» / «обновлён до vY» / текст ошибки (`kind="error"`). `showEvent` → `updates.refresh()`.

- [ ] **Step 1: Тесты** (фейки updates/account/registry): `test_store_tab_prompts_login_when_logged_out`; `test_store_buttons_follow_store_action` (три карточки: «Установить», «Обновить», «Установлено»); `test_install_click_downloads_and_installs` (фейковый `download_plugin` + `registry.install` вызваны с id, по завершении уведомление через event_bus `notification_requested`); `test_update_button_on_installed_tab`; `test_bundled_has_no_delete_button`; `test_install_error_notifies` (`StoreError("Сервер недоступен")` → уведомление `kind="error"`, кнопка снова активна).
- [ ] **Step 2:** FAIL → **Step 3:** реализовать → **Step 4:** PASS + весь pytest + ruff.
- [ ] **Step 5:** запустить приложение против локального сайта (`DEBUG=1 ../.venv/bin/python manage.py runserver` + загрузить тестовый zip в админке; адрес сервера в «Дополнительно» — `http://127.0.0.1:8000`) и пройти: вход → магазин → установка → обновление (перезалить zip с новой версией) → удаление. Отчёт со скриншотами.
- [ ] **Step 6: Commit** `feat(plugins): менеджер плагинов — вкладки «Установленные» и «Магазин»`.

---

## Часть 3. Together

### Task 12: Together на общем аккаунте (вне git)

**Files:**
- Modify: `plugins_dir/together/client.py`, `page.py`, `plugin.py`
- Test: `plugins_dir/together/tests/test_account.py`; обновить `test_queue.py`, `test_notices.py`

**Interfaces:**
- Consumes: `host.account` (`server_url`, `token`, `username`, `is_logged_in`, `auth_headers()`, `handle_unauthorized()`, `changed`), `host.open_accounts()`; API сайта Task 1, 3, 4.
- Produces: `TogetherClient.use_account(base_url: str, token: str, username: str) -> None` (вместо `login`); HTTP и WebSocket с `Authorization: Token …`; `unlock_room(room, password)` → `POST /api/rooms/<id>/unlock/`; 401 от API → колбэк `on_unauthorized` (плагин зовёт `account.handle_unauthorized()`); код закрытия WS 4401 — то же. Удалить: `login`, `_extract_csrf`, CSRF-регэксп, keyring-хелперы, `_migrate_settings`, форму входа, поле адреса, «Запомнить пароль». Страница: экран «Войдите в аккаунт Quantis» + кнопка «Открыть аккаунты» вместо экрана входа. При первом запуске — удалить старые записи keyring Together (`KEYRING_SERVICE`) и ключи `base_url/username/remember` из настроек плагина. `account.changed` → `leave_room()` и экран комнат/входа заново.

- [ ] **Step 1: Тесты:** `test_requests_carry_token` (фейковый aiohttp-сервер: `/api/rooms/` получает заголовок); `test_ws_headers_carry_token` (подмена `websockets.connect` — проверка `additional_headers`); `test_unlock_posts_password`; `test_401_calls_on_unauthorized`; `test_account_change_leaves_room`; `test_page_shows_login_prompt_without_account`; `test_old_keyring_entries_removed` (monkeypatch keyring).
- [ ] **Step 2:** FAIL → **Step 3:** реализовать; обновить существующие тесты под новый клиент → **Step 4:** все тесты Together PASS, весь pytest программы PASS.
- [ ] **Step 5:** ручная проверка против локального сайта: вход в аккаунт → «Вместе» → комнаты → запароленная комната (пароль один раз) → чат, уведомления. Коммита нет (папка вне git) — отметить в отчёте.

---

## Финал

- [ ] Весь `uv run pytest -q`, `ruff check src tests`, тесты Together, `manage.py test` на сайте — зелёные; приложить вывод.
- [ ] Сводка владельцу: что выкладывать на VPS (из README сайта), что перезалить в админке, ветки в обоих репозиториях. Ничего не пушить и не выкладывать без явной просьбы.
