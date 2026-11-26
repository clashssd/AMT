/**
 * electron/update-manager.js — wraps electron-updater for the AMT Chat app.
 *
 * Auto-checks for updates on GitHub Releases (clashssd/AMT) at startup
 * (after a short delay) and on a 24-hour schedule. The user controls
 * the download and install steps; nothing is downloaded automatically.
 *
 * Logs to %APPDATA%\AMT Chat\debug.log.
 */
'use strict';

const { autoUpdater } = require('electron-updater');
const { app, shell } = require('electron');
const path = require('path');
const fs = require('fs');

// Where updates come from
const UPDATE_SOURCE = {
  provider: 'github',
  owner: 'clashssd',
  repo: 'AMT',
};

let isInitialized = false;
let _getWindows = null; // set via init({ getWindows })

// --- logging ---------------------------------------------------------------

function _logPath() {
  // Windows: %APPDATA%\AMT Chat\debug.log
  // Fallback (Linux/macOS dev): <userData>/debug.log
  const appData = process.env.APPDATA;
  if (appData) return path.join(appData, 'AMT Chat', 'debug.log');
  try {
    return path.join(app.getPath('userData'), 'debug.log');
  } catch {
    return path.join(process.cwd(), 'debug.log');
  }
}

function log(msg, data) {
  try {
    const p = _logPath();
    fs.mkdirSync(path.dirname(p), { recursive: true });
    const line = `[${new Date().toISOString()}] [update] ${msg}` + (data ? ' ' + JSON.stringify(data) : '') + '\n';
    fs.appendFileSync(p, line);
  } catch {
    // never crash the app over a log write
  }
}

// --- renderer notification -------------------------------------------------

function _notifyRenderer(payload) {
  if (!_getWindows) return;
  let windows;
  try { windows = _getWindows(); } catch { return; }
  if (!windows) return;
  for (const w of windows) {
    try {
      if (!w.isDestroyed()) w.webContents.send('updates:status-changed', payload);
    } catch {}
  }
}

// --- autoUpdater event listeners (registered ONCE in init) -----------------

function _wireEvents() {
  autoUpdater.on('checking-for-update', () => {
    log('checking-for-update');
    _notifyRenderer({ event: 'checking' });
  });

  autoUpdater.on('update-available', (info) => {
    log('update-available', info);
    _notifyRenderer({ event: 'available', data: info });
  });

  autoUpdater.on('update-not-available', (info) => {
    log('update-not-available', info);
    _notifyRenderer({ event: 'not-available', data: info });
  });

  autoUpdater.on('download-progress', (p) => {
    log('download-progress', p);
    _notifyRenderer({ event: 'downloading', data: p });
  });

  autoUpdater.on('update-downloaded', (info) => {
    log('update-downloaded', info);
    _notifyRenderer({ event: 'downloaded', data: info });
  });

  autoUpdater.on('error', (e) => {
    log('error', { message: e && e.message ? e.message : String(e) });
    _notifyRenderer({ event: 'error', data: { message: e && e.message ? e.message : String(e) } });
  });
}

// --- public API ------------------------------------------------------------

/**
 * Initialize the updater. Safe to call multiple times — subsequent calls are no-ops.
 *
 * @param {object} opts
 * @param {number} [opts.delayMs]    - delay before the first auto-check (ms), 0 = check immediately
 * @param {number} [opts.intervalMs] - interval between periodic checks (ms), 0 = no periodic check
 * @param {Function} [opts.getWindows] - returns an array of BrowserWindows to notify
 */
function init({ delayMs = 5000, intervalMs = 24 * 60 * 60 * 1000, getWindows = null } = {}) {
  if (isInitialized) return;
  isInitialized = true;
  _getWindows = getWindows;

  autoUpdater.autoDownload = false; // the user decides when to download
  autoUpdater.autoInstallOnAppQuit = false; // the user decides when to install
  autoUpdater.channel = 'latest';

  _wireEvents();

  // First check after a short delay (lets the sidecar and UI settle)
  if (delayMs > 0) {
    setTimeout(() => { checkForUpdates().catch(() => {}); }, delayMs);
  } else {
    checkForUpdates().catch(() => {});
  }

  // Periodic checks
  if (intervalMs > 0) {
    setInterval(() => { checkForUpdates().catch(() => {}); }, intervalMs);
  }

  log('init', { delayMs, intervalMs });
}

/**
 * Check for updates.
 * @returns {Promise<object>} { ok, version?, error? }
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
 * Download the update (call only after the user confirms).
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
 * Quit the app and install the downloaded update.
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
 * Current status snapshot for IPC.
 * @returns {object}
 */
function getStatus() {
  return {
    version: app.getVersion(),
    source: UPDATE_SOURCE,
    isInitialized,
    platform: process.platform,
  };
}

/**
 * Open the GitHub Releases page (fallback for Linux/macOS or on error).
 */
function openReleasesPage() {
  const url = `https://github.com/${UPDATE_SOURCE.owner}/${UPDATE_SOURCE.repo}/releases`;
  log('openReleasesPage', { url });
  shell.openExternal(url);
}

module.exports = {
  init,
  checkForUpdates,
  downloadUpdate,
  quitAndInstall,
  getStatus,
  openReleasesPage,
  UPDATE_SOURCE,
};
