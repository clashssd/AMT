# Архитектура — AMT Chat

Техническое описание устройства приложения: какие процессы, как они связаны
и где что лежит. Для общего понимания и для тех, кто будет менять код.

---

## Компоненты и процессы

AMT Chat — desktop-приложение из трёх компонентов, которые живут в отдельных
процессах:

1. **Electron (главный процесс)** — `main.js` на корне. Создаёт frameless-окно,
   управляет жизненным циклом sidecar-бэкенда, реализует IPC и preload.
   Оболочка не знает о логике приложения — только про запуск/остановку
   бэкенда и прокси событий.

2. **Python-бэкенд (sidecar)** — `backend/main.py` на FastAPI/uvicorn.
   Поднимается Electron-ом как дочерний процесс (в dev — `backend/.venv`/
   системный Python, в сборке — PyInstaller-бандл `amt-backend.exe`).
   Слушает `127.0.0.1:8000`. Сам раздаёт фронтенд через `StaticFiles` —
   поэтому в dev достаточно запустить бэкенд и открыть браузер.

3. **Фронтенд (renderer)** — vanilla JS + HTML + CSS из `frontend/`, без
   фреймворков. Загружается Electron-ом с `http://127.0.0.1:8000`, общается
   с бэкендом через `fetch` (REST) и WebSocket.

### Связь renderer ↔ бэкенд

Все HTTP-запросы идут на `127.0.0.1:8000` (REST) или `ws://127.0.0.1:8000/ws`
(WebSocket). В Electron-сборке это localhost, и CORS не нужен; в dev-браузере
то же самое. Никакого внешнего облака: весь трафик остаётся на машине.

### Внешние MCP-серверы

При подключении внешнего MCP-сервера (STDIO-процесс или HTTP-эндпоинт) бэкенд
запускает дочерний процесс (`ai_engine/mcp_manager.py`). Инструменты такого
сервера получают префикс `mcp__<server>__<tool>` и появляются в доступных
инструментах модели. Env-переменные сервера шифруются Fernet (`mcp_key.key`).

---

## Дерево каталогов (основное)

```
main.js                     Electron-главный процесс (окно, sidecar, IPC)
electron/
  sidecar.js                запуск/остановка Python-бэкенда, копирование
                            dev-конфигов, env-инжекция (AMT_DATA_DIR и др.)
  ipc.js / preload.js       IPC-мост renderer ↔ main
  secrets.js                шифрование API-ключей (Electron safeStorage/DPAPI)

backend/
  main.py                   FastAPI: REST-эндпоинты, WebSocket, StaticFiles;
                            entrypoint со входом в разные режимы
                            (AMT_BACKEND_MODE=rag|media|writer|coding)
  ai_engine/                агенты, оркестратор, память, media, tools,
                            tool_registry, mcp_manager, web_scraper, keymanager,
                            extensions, filegen, desktop_tools, browser_cdp,
                            coding_tools, async_utils
  stt_local.py              локальный Vosk-STT (wake-word, batch, авто-загрузка)
  command_engine.py         парсинг и выполнение slash-команд
  command_registry.json     реестр slash-команд
  logging_structured.py     JSONL-логирование с trace_id
  coding_mcp_server.py      кодинг-MCP (read-only диагностика проекта)
  rag_server/               локальная база знаний (индекс + BM25-поиск)
  media_server/             медиа-генерация как MCP-сервер
  writer_server/            генерация файлов как MCP-сервер
  keys.json                 шаблон API-ключей (не коммитится)
  settings.json             конфиг оркестратора
  agents.json               seed-ядро агентов/скиллов (создаётся при старте)
  mcp_servers.json          внешние MCP-серверы (создаётся при добавлении)
  changelog.json            история версий (автообновление + «Справка → Апдейты»)

frontend/
  home.html                 основной UI (SPA)
  js/                       main.js, voice.js, mcp/mcp.js, theme-editor.js,
                            theme-schema.js, themes.js
    core/                   ядро: main.js, init.js, bootstrap.js, themes.js
    media/                  media-overlay.js
    mcp/                    mcp.js
    components/ pages/      переиспользуемые блоки и страницы
  css/                    style.css, tokens.css, components-v2.css,
                          commands.css, voice.css, motion-v2.css
  themes.json               готовые темы
  assets/                   иконки, изображения

extensions/                 папки расширений (manifest.json + index.js +
                            backend.py), без перекомпиляции
docs/                       BUILD.md, SETUP.md, EXTENSIONS.md, SECURITY.md,
                          COMMANDS_SYSTEM_DETAILED.md, CHANGELOG.md,
                          ARCHITECTURE.md, CONTRIBUTING.md
tests/                      pytest (бэкенд) + node (фронтенд-модули)
scripts/                    build.js, bootstrap_and_build.ps1, patch-скрипты
package.json                версия, scripts, electron-builder config
requirements.txt            Python-зависимости
```

---

## Жизненный цикл

### Dev (в браузере)

1. `python -m venv backend/.venv` + `pip install -r requirements.txt`.
2. `uvicorn main:app --port 8000` из `backend/`.
3. Открыть `http://127.0.0.1:8000`. Бэкенд раздаёт `frontend/` через
   `StaticFiles`.

### Dev (Electron)

`npm start` — Electron поднимает бэкенд (`backend/.venv` или `AMT_PYTHON`) на
`8000` и открывает frameless-окно. Окно рисует собственный тайтлбар в HTML;
нативная серая полоса Windows-заголовка не показывается.

### Сборка

`npm run build:all` = `node scripts/build.js all`:

1. **PyInstaller** (`backend/amt-backend.spec`) → `dist/amt-backend/` —
   бандл бэкенда (onedir: `amt-backend.exe` + `_internal/`), включая
   `media_server`, `writer_server`, `coding_mcp_server`, `rag_server`.
2. **sync-frontend** — копирует `frontend/` в
   `dist/amt-backend/_internal/frontend`.
3. **electron-builder** (`--win`) → NSIS-инсталлятор
   `release/AMT Chat Setup <версия>.exe` и портативный
   `release/win-unpacked/AMT Chat.exe`.

В frozen-бандле entrypoint `main.py` читает `AMT_BACKEND_MODE` из env и
запускает соответствующий сервер (rag / media / writer / coding) или основной
HTTP API. Это позволяет использовать один `amt-backend.exe` и как основной
бэкенд, и как STDIO-сервер для любого из MCP-пресетов.

---

## Ключевые решения

- **Три процесса, один порт.** Renderer не ходит в интернет напрямую к API
  провайдера — только к своему локальному бэкенду. Бэкенд — единственная
  точка, которая знает API-ключ. Это упрощает модель безопасности: ключи
  шифруются локально (DPAPI/secrets.bin), наружу уходят только с
  аутентификацией.

- **Бэкенд раздаёт фронтенд.** В dev достаточно одного `uvicorn` — не нужен
  отдельный dev-сервер. В сборке `StaticFiles` отдаёт `frontend/` из
  `_internal`.

- **Один frozen-exe на несколько ролей.** `AMT_BACKEND_MODE` + env-параметры
  определяют, каким сервером запустится `amt-backend.exe` (HTTP API, RAG,
  media, writer, coding). Это исключает отдельные бинарники на каждый
  MCP-пресет и упрощает PyInstaller-спец.

- **Расширения без перекомпиляции.** Папки в `extensions/` с
  `manifest.json` загружаются бэкендом (`ai_engine/extensions.py`) и
  фронтендом — можно менять поведение, не трогая бинарник.

- **Модельный код читается.** Vanilla JS + FastAPI без слоёв абстракции —
  любой, кто понимает оба языка, может менять проект под себя.

---

## Где лежит пользовательские данные

- `settings.json`, `keys.json`, `agents.json`, `sessions.json`, `chats/`,
  `files/` — в каталоге данных бэкенда (dev: `backend/`; сборка:
  `%APPDATA%\AMT Chat\`).
- `secrets.bin` — зашифрованные API-ключи (Electron safeStorage/DPAPI).
- `mcp_key.key` — ключ Fernet для env-переменных MCP-серверов.
- `media_creds.json` — креды медиа-провайдера для MCP-сервера media/writer.
- `.amt_rag/` (или `AMT_RAG_DATA_DIR`) — индексы RAG-базы.
- `logs/` — JSONL-структурированные логи.

Полный список и что в каждом — `docs/SETUP.md` и `docs/SECURITY.md`.
