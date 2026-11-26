/**
 * electron/update-ipc.js — IPC handlers for the auto-update system.
 *
 * Register with: registerUpdateIpc() in main.js after app.whenReady.
 * Channels:
 *   updates:status       → getStatus()
 *   updates:check       → checkForUpdates()
 *   updates:download    → downloadUpdate()
 *   updates:install     → quitAndInstall()
 *   updates:openReleases → openReleasesPage()
 */
'use strict';

const { ipcMain } = require('electron');
const {
  checkForUpdates,
  downloadUpdate,
  quitAndInstall,
  getStatus,
  openReleasesPage,
} = require('./update-manager');

function registerUpdateIpc() {
  ipcMain.handle('updates:status', async () => {
    return getStatus();
  });

  ipcMain.handle('updates:check', async () => {
    return checkForUpdates();
  });

  ipcMain.handle('updates:download', async () => {
    return downloadUpdate();
  });

  ipcMain.handle('updates:install', async () => {
    // quitAndInstall() will terminate the app — no return value expected
    quitAndInstall();
  });

  ipcMain.handle('updates:openReleases', async () => {
    openReleasesPage();
  });
}

module.exports = { registerUpdateIpc };
