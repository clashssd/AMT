# Сборка дистрибутива AMT Chat

> Для полного setup-процесса (включая venv + npm install) см. `docs/SETUP.md`.

Цель: один NSIS-инсталлятор `.exe`, внутри которого Electron + Python-бэкенд
(собранный PyInstaller) + фронтенд + расширения. Пользователю не нужен Python.

## Требования
- Node.js 18+ (для electron-builder)
- Python 3.12+ (для PyInstaller)
- Windows (целевая платформа)
- В `venv/` установлены зависимости из `requirements.txt` + `pyinstaller`

## Шаги

### 1. Соберите Python-бэкенд (sidecar)
```bash
pip install pyinstaller
npm run build:py
```
Использует `backend/amt-backend.spec` (см. ниже). Результат — один каталог
`dist/amt-backend/`, внутри бинарник `amt-backend` и зависимости.

> Sidecar: в dev Electron запускает `venv\Scripts\python.exe -m uvicorn
> backend.main:app`. В production — PyInstaller-бинарник. `electron/sidecar.js`
> определяет, что использовать (см. `getSidecarCommand()`).

### 2. Соберите Electron + NSIS
```bash
npm install
npm run build:win
```
Результат: `release/AMT Chat Setup <версия>.exe` (каталог `release/` из
`build.directories.output` в `package.json`).

### 3. Проверьте инсталлятор
- Запустите `.exe` → установится → запустится.
- Приложение поднимает бэкенд, открывает окно, chat работает.

## PyInstaller spec
См. `backend/amt-backend.spec`. Ключевое:
- `--onefile` нет (one-dir быстрее по старту), entry `backend/main.py`.
- Include: `ai_engine/**` + все зависимости из `requirements.txt`.
- В бэкенд не входит uvicorn как точка входа — мы запускаем
  `amt-backend`-бинарник, который сам стартует uvicorn на порту из env `PORT`.

##electron-builder
Настройка в `package.json` → поле `build`:
- `appId: com.amt.chat`, `target: nsis`.
- `files`: `main.js`, `electron/**`, `frontend/**`, `backend/**`,
  `extensions/**`, `requirements.txt`, `dist/amt-backend/**`.
- `directories.output`: `release` (исполняемый инсталлятор попадает сюда).
- `oneClick: false`, каталог установки можно выбрать.

## Переменные окружения (runtime)
| Var | Назначение | Дефолт |
|-----|-----------|--------|
| `PORT` | порт бэкенда | 8000 |
| `AMT_PYTHON` | путь к python.exe (dev sidecar) | `venv/Scripts/python.exe` |
| `AMT_LOG_DIR` | каталог логов | `backend/logs` |
| `AMT_EXTENSIONS_DIR` | каталог расширений | `extensions` |

## Устранение неполадок (Windows)

### `spawn UNKNOWN` на шаге NSIS (electron-builder)
Симптом — сборка падает именно при компиляции NSIS, в логе:
```
x spawn UNKNOWN  failedTask=build  stackTrace=Error: spawn UNKNOWN
    at ChildProcess.spawn (node:internal/child_process:...)
    at execFile (...node_modules\builder-util\src\util.ts:99:13)
```
`spawn UNKNOWN` = Windows не смог запустить `makensis.exe`. Три типичные
причины (все устранимы, скрипт `node scripts/build.js` учитывает все три):

1. **Не-ASCII путь кэша** (напр. профиль с кириллицей: `C:\Users\юляещека`).
   electron-builder скачивает/извлекает NSIS в кэш под этим путём, а
   `child_process.spawn` на кириллическом пути падает с `UNKNOWN`.
   **Автоматически (с этой версии):** `scripts/build.js` ВСЕГДА на Windows
   переопределяет `ELECTRON_BUILDER_CACHE` в чистый ASCII-каталог
   (`C:\amt-builder-cache\<user>\`) и pre-загружает NSIS туда, так что
   `makensis.exe` извлекается и запускается по ASCII-пути. После сборки
   скрипт печатает диагностическую строку `✓ NSIS-компилятор работал из:
   <путь> (non-ASCII=false)` — если видите `(non-ASCII=true)`, обход не
   сработал. Если запускаете `npm run build:win` руками (НЕ через
   `scripts/build.js`), задайте кэш сами:
   ```powershell
   $env:ELECTRON_BUILDER_CACHE = "C:\amt-builder-cache\user"
   New-Item -ItemType Directory -Force $env:ELECTRON_BUILDER_CACHE | Out-Null
   npm run build:win
   ```
2. **Нет `7za` в PATH — `app-builder.exe` не может распаковать NSIS-архив.**
   electron-builder скачивает NSIS как `.7z` (например
   `nsis-3.0.4.1.7z`), затем `app-builder.exe` пытается распаковать его
   через `7za` (из PATH). На корпоративных машинах (WDAC/SmartScreen)
   `7za` часто отсутствует → `executable file not in %PATH%` → NSIS не
   извлекается → `makensis.exe` не на месте → `spawn UNKNOWN`.
   **Автоматически (с этой версии):** `scripts/build.js` после
   `app-builder.exe download-artifact` ищет скачанный `.7z` в кэше и
   распаковывает его через `7z.exe` из стандартной локации
   `C:\Program Files\7-Zip\` (или PATH, если 7za там). Если 7-Zip не
   установлен — поставьте: `winget install 7zip.7zip` (или
   `choco install 7zip`) и перезапустите `node scripts/build.js win`.
3. **Антивирус/SmartScreen заблокировал только что извлечённый
   `makensis.exe`.** Скрипт делает 1 retry через 2 сек. Если не помогло —
   временно отключите антивирус на время сборки (кэш NSIS — ~13 МБ, быстро
   переживает), затем `node scripts/build.js win`.

### `Cannot create symbolic link` при сборке winCodeSign
7-Zip не может создать symlinks macOS-файлов в кэше winCodeSign. `build:win` уже передаёт `--config.win.signAndEditExecutable=false --config.win.sign=false` (без подписи), что в большинстве случаев обходит подготовку winCodeSign. Если сборка всё равно падает на этом:
```powershell
# Удалить кэш winCodeSign и повторить (без подписи rcedit не нужен)
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign" -ErrorAction SilentlyContinue
npm run build:win
```
Если нужно **с подписью**: задайте `WIN_CSC_LINK` (pfx) и `WIN_CSC_PASSWORD` — тогда rcedit/winCodeSign реально используются, и symlinks-ошибка решается запуском PowerShell с правами администратора (для создания symlinks).

## Подпись (signing) и SmartScreen
Опционально: добавьте `win.certificateFile` / `win.certificatePassword` в
`build` блока `package.json`. Без подписи — Windows SmartScreen предупредит
при первом запуске инсталлятора: «"Интеллектуальное управление
приложениями" заблокировало приложение… не удалось проверить издателя».

Это **ожидаемо**: AMT Chat не подписан (code-signing сертификат —
платный, DigiCert/GlobalSign). Способы для конечного пользователя:
- **Обойти SmartScreen (безопасно):** в окне предупреждения нажмите
  «Подробнее» → в раскрытом списке появится «Выполнить в любом случае» →
  подтвердите. Приложение при этом то же самое, что без предупреждения.
- **Запустить портативную копию без NSIS:** `release\win-unpacked\AMT
  Chat.exe` не устанавливается через NSIS-инсталлятор, поэтому SmartScreen
  его, как правило, не блокирует.

Для **корпоративного развёртывания** подпишите `AMT Chat Setup.exe` и
uninstaller сертификатом организации (выдайте доменное/корпоративное
доверие через GPO или добавьте издателя в «Надоверенные»). Тогда
SmartScreen предупреждать не будет.
