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

### `Cannot create symbolic link` при сборке winCodeSign
7-Zip не может создать symlinks macOS-файлов в кэше winCodeSign. `build:win` уже передаёт `--config.win.signAndEditExecutable=false --config.win.sign=false` (без подписи), что в большинстве случаев обходит подготовку winCodeSign. Если сборка всё равно падает на этом:
```powershell
# Удалить кэш winCodeSign и повторить (без подписи rcedit не нужен)
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\electron-builder\Cache\winCodeSign" -ErrorAction SilentlyContinue
npm run build:win
```
Если нужно **с подписью**: задайте `WIN_CSC_LINK` (pfx) и `WIN_CSC_PASSWORD` — тогда rcedit/winCodeSign реально используются, и symlinks-ошибка решается запуском PowerShell с правами администратора (для создания symlinks).

## Подпись (signing)
Опционально: добавьте `win.certificateFile` / `win.certificatePassword` в
`build` блока `package.json`. Без подписи — Windows SmartScreen предупредит.
