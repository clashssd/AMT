/**
 * main.js — Electron main process entry point.
 *
 * Spawns the Python sidecar, creates the BrowserWindow,
 * wires IPC handlers, and manages the app lifecycle.
 */
'use strict';

const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');
const { startSidecar, stopSidecar } = require('./electron/sidecar');
const { registerIpc } = require('./electron/ipc');
const { registerSecretsIpc, injectAllSecrets, setToken } = require('./electron/secrets');

const PORT = parseInt(process.env.AMT_PORT || '8000', 10);
let win = null;
let sidecar = { port: PORT };

// Prevent multiple instances
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {

app.whenReady().then(async () => {
  try {
    const fs = require('fs');
    const dbg = path.join(process.env.APPDATA || '', 'AMT Chat', 'debug.log');
    fs.mkdirSync(path.dirname(dbg), { recursive: true });
    const log = (msg) => fs.appendFileSync(dbg, `[${new Date().toISOString()}] ${msg}\n`);
    log('starting sidecar on port ' + PORT);
    log('resourcesPath: ' + process.resourcesPath);
    log('appPath: ' + app.getAppPath());
    log('isPackaged: ' + app.isPackaged);
    log('APPDATA: ' + process.env.APPDATA);
    await startSidecar(PORT);
    log('sidecar started OK');
    sidecar.port = PORT;

    // Generate internal token for the secrets channel and inject stored secrets
    const crypto = require('crypto');
    const internalToken = crypto.randomUUID();
    setToken(internalToken);
    process.env.AMT_INTERNAL_TOKEN = internalToken;
    try {
      await injectAllSecrets(PORT);
      log('secrets injected into sidecar');
    } catch (e) {
      log('secrets injection failed: ' + e.message);
    }
  } catch (err) {
    try { fs.appendFileSync(path.join(process.env.APPDATA || '', 'AMT Chat', 'debug.log'), 'ERROR: ' + err.message + '\n'); } catch {}
    // Continue anyway — frontend will show connection errors
  }

  registerIpc(sidecar);
  registerSecretsIpc(() => sidecar.port);

  // Убираем стандартное светлое меню (File/Edit/View/Window) — оставляем только
  // тёмный заголовок окна, без серой полоски.
  Menu.setApplicationMenu(null);

  win = createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

function createWindow() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 600,
    title: 'AMT Chat',
    frame: false,           // Свой HTML-тайтлбар в контенте (см. frontend/home.html #winTitlebar) — без нативной серой полоски
    titleBarStyle: 'hidden', // страховка: даже если frame ложное поведение на какой-то ОС, заголовок не дублируется
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'electron', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Load the frontend from the backend URL so that window.location.origin
  // points to the Python server and all existing fetch() calls work unchanged.
  win.loadURL(`http://127.0.0.1:${PORT}/`);

  // Security (audit fix 6.4): block navigation away from our origin.
  // External links must go through the built-in browser window or
  // shell.openExternal — never through the main window.
  win.webContents.on('will-navigate', (e, url) => {
    const allowed = `http://127.0.0.1:${PORT}`;
    if (!url.startsWith(allowed) && !url.startsWith('file://')) {
      e.preventDefault();
    }
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    const allowed = `http://127.0.0.1:${PORT}`;
    if (url.startsWith(allowed) || url.startsWith('file://')) {
      // Allow same-origin popups (rare, but e.g. devtools)
      return { action: 'allow' };
    }
    // Route everything else to the external browser
    const { shell } = require('electron');
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  win.on('closed', () => { win = null; });
  return win;
}

} // gotLock

app.on('before-quit', () => {
  process.appQuitting = true;
  stopSidecar();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
