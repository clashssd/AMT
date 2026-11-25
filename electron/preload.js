/**
 * electron/preload.js — runs in the renderer's isolated context.
 * Exposes a minimal `window.api` surface to the frontend.
 *
 * The frontend checks `window.api` to decide whether it's running
 * inside Electron (use IPC) or in a browser (use fetch to localhost).
 */
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  /**
   * Proxy a fetch to the Python backend.
   * @param {string} urlPath - e.g. "/api/chat"
   * @param {object} opts - { method, headers, body }
   * @returns {Promise<{status:number, ok:boolean, json:any, text:string}>}
   */
  fetch: (urlPath, opts) => ipcRenderer.invoke('backend:fetch', urlPath, opts || {}),

  /** List projects */
  projects: {
    list: () => ipcRenderer.invoke('project:list'),
    create: (name, root) => ipcRenderer.invoke('project:create', name, root),
    select: (id) => ipcRenderer.invoke('project:select', id),
  },

  /** Execute a tool via the backend */
  tools: {
    execute: (tool, args, approved) => ipcRenderer.invoke('tools:execute', tool, args, approved),
  },

  /** Open a directory picker */
  dialog: {
    openDirectory: (defaultPath) => ipcRenderer.invoke('dialog:openDirectory', defaultPath),
  },

  /** Open a URL in the user's default external browser */
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),

  /** Toggle native window fullscreen (⛶ button in the media player) */
  toggleFullscreen: () => ipcRenderer.invoke('window:toggleFullscreen'),

  /** Управление frameless-окном: 'minimize' | 'maximize' | 'close' (свой HTML-тайтлбар) */
  windowControl: (action) => ipcRenderer.invoke('window:control', action),

  /** Реальный скриншот внешней страницы (Electron capturePage) */
  screenshot: (url) => ipcRenderer.invoke('web:screenshot', url),

  /** Открыть URL в frameless Electron-окне (встроенный браузер, обходит X-Frame-Options) */
  openBrowserWindow: (url, opts) => ipcRenderer.invoke('web:openBrowserWindow', url, opts),

  /** Закрыть встроенное browser-окно */
  closeBrowserWindow: (windowId) => ipcRenderer.invoke('web:closeBrowserWindow', windowId),

  /** Открыть URL системным браузером (Firefox/Chrome/Edge или пользовательский путь) */
  openExternalBrowser: (url) => ipcRenderer.invoke('web:openExternalBrowser', url),

  /** Secrets (safeStorage-backed API key store) */
  secrets: {
    set: (opts) => ipcRenderer.invoke('secrets:set', opts),
    clear: (opts) => ipcRenderer.invoke('secrets:clear', opts),
    status: () => ipcRenderer.invoke('secrets:status'),
  },
});
