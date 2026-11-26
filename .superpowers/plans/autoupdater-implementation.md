# Система автообновлений AMT Chat (Electron + GitHub Releases)

## Цель
Автоматическая проверка, загрузка и установка обновлений через GitHub Releases (repo: `clashssd/AMT`).
Приоритет — Windows (NSIS + AutoUpdater). Linux/macOS — фолбэк: ссылка на GitHub Releases.

## Архитектура

### 1. Зависимости (package.json)
- `electron-updater` (runtime dep)
- `electron-builder` уже есть (devDep)

### 2. Конфигурация electron-builder (package.json → build)
Добавить в `build`:
```json
"publish": {
  "provider": "github",
  "owner": "clashssd",
  "repo": "AMT",
  "draft": false,
  "prerelease": false
}
```
- `signAndEditExecutable: false` уже есть (ок, т.к. без кода-сига)
- Для NSIS: `oneClick: false` + `allowToChangeInstallationDirectory: true` — ок
- Файлы в release: `AMT-Chat-Setup-<ver>.exe`, `AMT-Chat-<ver>-win.zip`, `latest.yml`
- `publishOnUpdate` не используем — релиз публикуется вручную через `npx electron-builder --win --publish always`

### 3. UpdateManager (electron/update-manager.js)
```js
'use strict';

const { autoUpdater } = require('electron-updater');
const { app, shell } = require('electron');
const path = require('path');

// Конфигурация
const UPDATE_SOURCE = {
  provider: 'github',
  owner: 'clashssd',
  repo: 'AMT',
};

let isInitialized = false;
let _timer = null;
const _timers = new Set();

/**
 * Инициализация после app.ready.
 * @param {number} delayMs - задержка первой проверки (мс)
 * @param {number} intervalMs - интервал повторных проверок (0 = выкл)
 */
function init({ delayMs = 5000, intervalMs = 24 * 60 * 60 * 1000 } = {}) {
  if (isInitialized) return;
  isInitialized = true;

  autoUpdater.autoDownload = false; // пользователь контролирует
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.channel = 'latest';

  // Логирование
  autoUpdater.on('checking-for-update', () => log('checking-for-update'));
  autoUpdater.on('update-available', (info) => log('update-available', info));
  autoUpdater.on('update-not-available', (info) => log('update-not-available', info));
  autoUpdater.on('download-progress', (p) => log('download-progress', p));
  autoUpdater.on('update-downloaded', (info) => log('update-downloaded', info));
  autoUpdater.on('error', (e) => log('error', e));

  // Первая проверка
  if (delayMs > 0) {
    const t = setTimeout(() => checkForUpdates().catch(() => {}), delayMs);
    _timers.add(t);
  }

  // Периодическая проверка
  if (intervalMs > 0) {
    const t = setInterval(() => checkForUpdates().catch(() => {}), intervalMs);
    _timers.add(t);
  }
}

/**
 * Проверка обновлений.
 * @returns {Promise<object>} - { ok, version?, error? }
 */
async function checkForUpdates() {
  try {
    const result = await autoUpdater.checkForUpdates();
    return { ok: true, ...(result || {}) };
  } catch (e) {
    log('checkForUpdates error:', e.message);
    return { ok: false, error: e.message };
  }
}

/**
 * Скачать обновление (только после подтверждения).
 * @returns {Promise<object>}
 */
async function downloadUpdate() {
  try {
    await autoUpdater.downloadUpdate();
    return { ok: true };
  } catch (e) {
    log('downloadUpdate error:', e.message);
    return { ok: false, error: e.message };
  }
}

/**
 * Установить и перезапустить.
 */
function quitAndInstall() {
  try {
    autoUpdater.quitAndInstall();
    return { ok: true };
  } catch (e) {
    log('quitAndInstall error:', e.message);
    return { ok: false, error: e.message };
  }
}

/**
 * Текущий статус для IPC.
 * @returns {object}
 */
function getStatus() {
  return {
    version: app.getVersion(),
    source: UPDATE_SOURCE,
    isInitialized,
  };
}

/**
 * Логирование в %APPDATA%/AMT Chat/debug.log
 */
function log(msg, data) {
  try {
    const fs = require('fs');
    const dbPath = path.join(process.env.APPDATA || '.', 'AMT Chat', 'debug.log');
    const line = `[${new Date().toISOString()}] [update] ${msg} ${data ? JSON.stringify(data) : ''}\n`;
    fs.appendFileSync(dbPath, line);
  } catch {}
}

/**
 * Открыть GitHub Releases (фолбэк для Linux/macOS или при ошибке).
 */
function openReleasesPage() {
  const url = `https://github.com/${UPDATE_SOURCE.owner}/${UPDATE_SOURCE.repo}/releases`;
  shell.openExternal(url);
}

module.exports = { init, checkForUpdates, downloadUpdate, quitAndInstall, getStatus, openReleasesPage, UPDATE_SOURCE };
```

### 4. IPC (electron/update-ipc.js)
```js
'use strict';

const { ipcMain } = require('electron');
const {
  init,
  checkForUpdates,
  downloadUpdate,
  quitAndInstall,
  getStatus,
  openReleasesPage,
} = require('./update-manager');

function registerUpdateIpc() {
  ipcMain.handle('updates:status', async () => getStatus());
  ipcMain.handle('updates:check', async () => checkForUpdates());
  ipcMain.handle('updates:download', async () => downloadUpdate());
  ipcMain.handle('updates:install', async () => {
    quitAndInstall();
  });
  ipcMain.handle('updates:openReleases', async () => {
    openReleasesPage();
  });
}

module.exports = { registerUpdateIpc };
```

### 5. Preload (electron/preload.js)
Добавить:
```js
/** Обновления */
updates: {
  status: () => ipcRenderer.invoke('updates:status'),
  check: () => ipcRenderer.invoke('updates:check'),
  download: () => ipcRenderer.invoke('updates:download'),
  install: () => ipcRenderer.invoke('updates:install'),
  openReleases: () => ipcRenderer.invoke('updates:openReleases'),
  onStatus: (cb) => {
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on('updates:status-changed', handler);
    return () => ipcRenderer.removeListener('updates:status-changed', handler);
  },
},
```

### 6. Frontend (frontend/js/update-ui.js)
```js
// ===== Обновления (UpdateManager) =====
// Состояние: { status, newVersion, changelog, downloadProgress, error }
let _updateState = { status: 'idle', newVersion: null, changelog: null, downloadProgress: 0, error: null };

function _updateBanner() { /* создать/скрыть баннер */ }
function _updateDialog() { /* создать диалог */ }
function _updateDialogContent() { /* версия, changelog, прогресс, кнопки */ }

async function loadUpdateChangelog() {
  try {
    const r = await fetch(`${API_BASE}/api/changelog`);
    const data = await r.json();
    return data;
  } catch {
    return { releases: [] };
  }
}

function initUpdateUI() {
  // Баннер + диалог + кнопки в «Справка → Апдейты»
}

window.AMTUpdates = {
  init: initUpdateUI,
  check: () => window.api.updates.check(),
  download: () => window.api.updates.download(),
  install: () => window.api.updates.install(),
  openReleases: () => window.api.updates.openReleases(),
};
```

### 7. CSS (frontend/css/style.css)
Добавить:
- `.update-banner` — тонкая полоса вверху (под тайтлбаром), цвет акцент, закрывается
- `.update-dialog` — модалка с версией, changelog (scroll), прогресс-бар, кнопки
- `.update-progress` — полоска прогресса с % и скоростью

### 8. Интеграция в main.js
```js
const { registerUpdateIpc } = require('./electron/update-ipc');
const updateManager = require('./electron/update-manager');

// После registerIpc:
registerUpdateIpc();
updateManager.init({ delayMs: 5000, intervalMs: 24 * 60 * 60 * 1000 });
```

### 9. Интеграция в preload.js
Добавить `updates` API в `contextBridge.exposeInMainWorld`.

### 10. Интеграция в home.html
Добавить:
- Скрипт `./js/update-ui.js` перед `./js/main.js`
- Баннер в DOM (скрыт)
- Диалог (скрыт)
- Кнопка «Проверить обновления» на странице `docs-updates` (уже есть `changelogRefreshBtn` — расширить)

### 11. Changelog (backend/changelog.json)
Добавить версию 1.0.7:
```json
{
  "version": "1.0.7",
  "date": "2026-11-26",
  "title": "Система автообновлений (electron-updater + GitHub Releases)",
  "changes": [
    "Автоматическая проверка обновлений при старте (через 5 сек) и раз в сутки.",
    "Ручная проверка: «Справка → Апдейты → Проверить обновления».",
    "Баннер о доступном обновлении + диалог с changelog и прогрессом загрузки.",
    "Скачивание только после подтверждения. Установка: «Перезапустить и обновить» / «Позже».",
    "Кроссплатформенность: Windows (NSIS + AutoUpdater), Linux/macOS — ссылка на GitHub Releases.",
    "Хэш-проверка, откат при неудачной установке, логирование в %APPDATA%\\AMT Chat\\debug.log.",
    "electron-builder: publish provider=github, owner=clashssd, repo=AMT."
  ]
}
```

### 12. Инструкция по релизу (README / docs)
1. Обновить `package.json` → `version: "1.0.7"`
2. Добавить в `changelog.json` запись 1.0.7
3. `npm run build:win` → создаст `release/AMT-Chat-Setup-1.0.7.exe`
4. `git tag v1.0.7`
5. `git push --tags`
6. В GitHub: создать Release `v1.0.7`, загрузить `.exe` и `.yml`
   Либо: `npx electron-builder --win --publish always` (автоматически создаст release)

### 13. Обработка ошибок
- При ошибке проверки/скачивания — баннер с текстом ошибки, не блокирует
- electron-updater поддерживает откат (NSIS-тул держит backup)
- Все ошибки логируются в `%APPDATA%\AMT Chat\debug.log`

## Файлы для создания/изменения

### Новые файлы
1. `electron/update-manager.js` — UpdateManager
2. `electron/update-ipc.js` — IPC handlers
3. `frontend/js/update-ui.js` — UI (баннер + диалог)

### Изменения
1. `package.json` — добавить `electron-updater` в deps, `publish` в build
2. `main.js` — инициализация UpdateManager + registerUpdateIpc
3. `electron/preload.js` — `updates` API
4. `frontend/home.html` — баннер, диалог, скрипт update-ui.js
5. `frontend/css/style.css` — стили
6. `backend/changelog.json` — версия 1.0.7
7. `README.md` / `docs` — инструкция по релизу

## Риски
- GitHub Releases должны быть публичными (repo clashssd/AMT — публичный, ок)
- electron-updater требует `latest.yml` в release (создаётся автоматически при build)
- Для NSIS: `oneClick: false` — пользователь выбирает каталог установки
- Без кода-сига: `signAndEditExecutable: false` — предупреждение SmartScreen (допустимо для локального проекта)
- Перекрестная проверка: `autoUpdater.autoDownload = false` — пользователь всегда контролирует
