# Вклад в AMT Chat — CONTRIBUTING

Как собрать, протестировать и внести изменения. Для разработчиков.

---

## Требования

- **Windows 10/11** (проект целенаправленно собирается под Windows; NSIS-
  инсталлятор и PyInstaller-бандл). Linux/macOS — можно запустить в dev-режиме
  (бэкенд + браузер), но полная сборка дистрибутива настроена под Windows.
- **Python 3.12+** (в сборке бандлится своя, в dev — системная).
- **Node.js 18+** (для Electron и сборочных скриптов).

## Сборка (один шаг)

```powershell
git clone https://github.com/clashssd/AMT.git
cd AMT
powershell -ExecutionPolicy Bypass -File scripts\bootstrap_and_build.ps1
```

Скрипт сам:

1. Проверит Python 3.12+ и Node.js; чего нет — поставит через `winget`.
2. Создаст `backend/.venv` и поставит Python-зависимости.
3. Поставит Node-зависимости.
4. Соберёт `release\win-unpacked\AMT Chat.exe` (портативный) и
   `release\AMT Chat Setup <версия>.exe` (NSIS-инсталлятор).
5. Применит патч иконки в `.exe` (обход бага electron-builder 25.1.8).

Результат через ~5–10 минут: два артефакта в `release/`.

### Ручная сборка (без скрипта)

```bash
python setup.py        # создаст backend/.venv + поставит зависимости
node setup.js          # npm install
npm run build:all      # PyInstaller -> dist/, затем electron-builder -> release/
node scripts/patch_exe_icon.js   # обход бага с иконкой
```

Подробнее — `docs/BUILD.md` и `docs/SETUP.md`.

## Запуск в dev

```bash
npm start              # Electron + бэкенд (нужен backend/.venv или AMT_PYTHON)
# или в браузере:
cd backend && ..\.venv\Scripts\uvicorn main:app --port 8000
```

Открыть `http://127.0.0.1:8000`. Включить API-ключ в «Настройки → Подключение».

## Тесты

```bash
npm test               # pytest + node (всё)
# по частям:
backend\.venv\Scripts\python.exe -m pytest tests/
node tests/run_js_tests.js
```

Регрессионные тесты кладутся рядом с проверяемым модулем (см. `tests/`).
При исправлении бага — сначала добавьте тест, который падает на старом коде и
проходит на новом (см. `add-regression-test`).

## Как внести изменения

1. **Разветвитесь.** Для новой фичи/фикса — отдельная ветка `feature/x`
   или `fix/y`. Не коммитьте прямо в `main`.
2. **Соблюдайте стиль.** Конventional commits: `feat: …`, `fix: …`,
   `docs: …`, `chore: …`, `refactor: …`. Одна группа правок — один
   логический коммит.
3. **Не трогайте сгенерированное.** `dist/`, `release/`, `build/`,
   `node_modules/`, `*.pyc` — в `.gitignore`. Не коммитьте бинарники.
4. **Не коммитьте секреты.** `keys.json`, `mcp_key.key`, `secrets.bin`,
   `.env*` — только шаблоны и пустые файлы.
5. **Обновите changelog.** Для пользовательских изменений добавьте запись в
   `docs/CHANGELOG.md` и (для автообновления) в `backend/changelog.json`.
6. **Проверьте.** Прогоните `npm test` и визуально проверьте UI (Ctrl+Shift+R
   для сброса кэша Chromium в dev-окне).
7. **Откройте PR.** Короткое описание: что, почему, как проверено.

## Версионирование

- Формат `MAJOR.MINOR.PATCH` (SemVer).
- `MAJOR` — несовместимые изменения API/поведения.
- `MINOR` — новые фичи без ломки.
- `PATCH` — баг-фиксы, улучшения.

Перед релизом:

1. Бамп `version` в `package.json`.
2. Новая запись в `backend/changelog.json` (топ-уровневый `version` и
   `latest_at` обновить).
3. Новая запись в `docs/CHANGELOG.md`.
4. Сборка + тег + GitHub-релиз (см. `docs/BUILD.md`).

## Лицензия

MIT. Расширения, ключи и данные, которые вы добавляете сами, лицензируются
вами. См. `LICENSE`.

## Что НЕ делать

- Не добавляйте фреймворки на фронтенде (vanilla JS — осознанное решение).
- Не меняйте `main.py` в сторону глобальных `import *`.
- Не коммитьте `.env*`, `*.key`, `secrets.bin`, `dist/`, `release/`.
- Не добавляйте телеметрию/аналитику — проект принципиально локальный.
- Не пишите `console.log` в production-коде (используйте `logging_structured`).
