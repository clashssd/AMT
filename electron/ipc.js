/**
 * electron/ipc.js — registers all IPC handlers for the frontend.
 *
 * The frontend talks to the Python backend through these handlers,
 * so the BrowserWindow can load local files (no CORS issues) and
 * all network calls are proxied through the main process.
 */
'use strict';

const { ipcMain, app, BrowserWindow } = require('electron');
const path = require('path');

/**
 * Register all IPC handlers.
 * @param {object} sidecar - { port } current sidecar info
 */
function registerIpc(sidecar) {
  const port = () => sidecar.port;

  /**
   * Proxy a fetch request to the Python backend.
   * @param {any} event - IPC event
   * @param {string} urlPath - e.g. "/api/chat"
   * @param {object} opts - { method, headers, body } (body is a string)
   */
  ipcMain.handle('backend:fetch', async (event, urlPath, opts = {}) => {
    const target = `http://127.0.0.1:${port()}${urlPath}`;
    const res = await fetch(target, {
      method: opts.method || 'GET',
      headers: opts.headers || {},
      body: opts.body || undefined,
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch {}
    return { status: res.status, ok: res.ok, json, text };
  });

  /**
   * List/inspect the current project root + allowed dirs.
   * Proxies to GET /api/projects -> { project, allowed_dirs }.
   */
  ipcMain.handle('project:list', async () => {
    const res = await fetch(`http://127.0.0.1:${port()}/api/projects`);
    const json = await res.json();
    return json; // { project: {...}, allowed_dirs: [...] }
  });

  /**
   * Create/select a project root (the AI's working folder).
   * Proxies to POST /api/projects/select with { root: path }.
   */
  ipcMain.handle('project:create', async (event, name, root) => {
    const res = await fetch(`http://127.0.0.1:${port()}/api/projects/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root: (root || name || '') }),
    });
    const json = await res.json();
    return json; // { ok, project, allowed_dirs, error? }
  });

  /**
   * Select a project root (applies it as the AI tool sandbox root).
   * Proxies to POST /api/projects/select with { root: path }.
   */
  ipcMain.handle('project:select', async (event, id) => {
    const res = await fetch(`http://127.0.0.1:${port()}/api/projects/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root: (id || '') }),
    });
    const json = await res.json();
    return json; // { ok, project, allowed_dirs, error? }
  });

  /**
   * Execute a tool via the backend.
   * Proxies to POST /api/tools/execute.
   */
  ipcMain.handle('tools:execute', async (event, tool, args, approved) => {
    const res = await fetch(`http://127.0.0.1:${port()}/api/tools/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool, args, approved: !!approved }),
    });
    return res.json();
  });

  /**
   * Open a URL in the user's default external browser.
   * Used for web search results / external links that can't be iframed
   * (most sites send X-Frame-Options: DENY).
   */
  ipcMain.handle('shell:openExternal', async (event, url) => {
    const { shell } = require('electron');
    if (typeof url === 'string' && /^https?:\/\//i.test(url)) {
      await shell.openExternal(url);
      return { ok: true };
    }
    return { ok: false, error: 'Некорректный URL' };
  });

  /**
   * Toggle native window fullscreen for the media overlay (⛶ button).
   * overlay.requestFullscreen() is often no-op for <div> in packaged Electron,
   * so we toggle the whole BrowserWindow instead.
   * ВАЖНО: фильтры/качество применяются к DOM-контейнеру playerMain — они
   * сохраняются и при fullscreen (CSS filter не сбрасывается).
   */
  ipcMain.handle('window:toggleFullscreen', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) {
      win.setFullScreen(!win.isFullScreen());
      return { ok: true, fullscreen: win.isFullScreen() };
    }
    return { ok: false };
  });

  /**
   * Управление рамкой frameless-окна (свой HTML-тайтлбар): minimize / maximize /
   * restore / close. Используется кнопками #winTitlebar в frontend/home.html.
   */
  ipcMain.handle('window:control', async (event, action) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return { ok: false };
    switch (action) {
      case 'minimize': win.minimize(); break;
      case 'maximize':
        if (win.isMaximized()) win.unmaximize(); else win.maximize();
        break;
      case 'close': win.close(); break;
      default: return { ok: false };
    }
    return { ok: true };
  });

  /**
   * Скриншот внешней страницы через Electron WebContents (реальный, JS-отрисованный).
   * Открываем скрытое окно, ждём load + 1.5s для отрисовки, делаем capturePage().
   * Возвращает { ok, b64 } или { ok: false, reason }.
   */
  const _shotWindows = new Map();
  ipcMain.handle('web:screenshot', async (event, url) => {
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) {
      return { ok: false, reason: 'Некорректный URL' };
    }
    const shotWin = new BrowserWindow({
      width: 1280, height: 800,
      show: false,
      webPreferences: { contextIsolation: true, nodeIntegration: false },
    });
    _shotWindows.set(shotWin.id, shotWin);
    try {
      // Ждём load + отрисовку
      await Promise.race([
        shotWin.loadURL(url),
        new Promise(r => setTimeout(r, 12000)),
      ]);
      // Даем 1.5s на JS-отрисовку
      await new Promise(r => setTimeout(r, 1500));
      const image = await shotWin.webContents.capturePage();
      return { ok: true, b64: image.toPNG().toString('base64') };
    } catch (e) {
      return { ok: false, reason: String(e && e.message || e).slice(0, 200) };
    } finally {
      try { shotWin.close(); } catch {}
      _shotWindows.delete(shotWin.id);
    }
  });

  /**
  /**
   * «Режим браузера ВНУТРИ ПЛЕЕРА»: frameless Electron-окно без заголовка ОС.
   * Выглядит как часть приложения, обходит X-Frame-Options.
   * Панель: ← → ⟳ [адрес] ✕ (авто-скрытие через 5 сек бездействия).
   */
  const _browserWindows = new Map();
  ipcMain.handle('web:openBrowserWindow', async (event, url, opts = {}) => {
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) {
      return { ok: false, reason: 'Некорректный URL' };
    }
    for (const [id, win] of _browserWindows) {
      try { if (!win.isDestroyed()) win.close(); } catch {}
      _browserWindows.delete(id);
    }
    // Get the main window bounds to position the browser on top of the player overlay
    const mainWin = BrowserWindow.getAllWindows().find(w => !w.isDestroyed() && !w.parent);
    const b = mainWin ? mainWin.getBounds() : { x: 100, y: 100, width: 1280, height: 800 };
    // Position: slightly inset from main window, centered
    const bw = Math.min(1280, b.width - 20);
    const bh = Math.min(800, b.height - 20);
    const bx = b.x + Math.max(0, (b.width - bw) / 2);
    const by = b.y + Math.max(0, (b.height - bh) / 2);
    const browserWin = new BrowserWindow({
      width: bw,
      height: bh,
      x: bx,
      y: by,
      frame: false,
      resizable: true,
      title: 'AMT — Встроенный браузер',
      parent: mainWin || undefined,
      webPreferences: { contextIsolation: true, nodeIntegration: false },
    });
    _browserWindows.set(browserWin.id, browserWin);
    browserWin.on('closed', () => _browserWindows.delete(browserWin.id));
    await browserWin.loadURL(url);
    browserWin.webContents.executeJavaScript(`
      (function(){
        const bar = document.createElement('div');
        bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:44px;background:rgba(10,10,18,0.97);display:flex;align-items:center;gap:6px;padding:0 10px;z-index:2147483647;font-family:system-ui,sans-serif;box-sizing:border-box;border-bottom:1px solid rgba(255,255,255,0.08);transition:opacity 0.4s;';
        const mkBtn = (t, title, extra) => {
          const b = document.createElement('button');
          b.textContent = t; b.title = title;
          b.style.cssText = 'background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);color:#c0c0d8;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:13px;' + (extra||'');
          return b;
        };
        const back = mkBtn('\u2190','Назад');
        const fwd = mkBtn('\u2192','Вперёд');
        const rel = mkBtn('\u27F3','Обновить');
        const ad = document.createElement('input');
        ad.style.cssText = 'flex:1;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:#e8e6f5;border-radius:6px;padding:5px 10px;font-size:13px;outline:none;box-sizing:border-box;';
        ad.value = window.location.href;
        const close = mkBtn('\u2715','Закрыть (Esc)','margin-left:auto;background:rgba(239,73,73,0.25);border-color:rgba(239,73,73,0.4);');
        bar.appendChild(back); bar.appendChild(fwd); bar.appendChild(rel); bar.appendChild(ad); bar.appendChild(close);
        back.onclick = () => history.back();
        fwd.onclick = () => history.forward();
        rel.onclick = () => location.reload();
        ad.onkeydown = (e) => { if (e.key === 'Enter') location.href = ad.value; };
        document.documentElement.style.paddingTop = '44px';
        document.body.prepend(bar);
        let idleT = null;
        function resetIdle() {
          bar.style.opacity = '1';
          if (idleT) clearTimeout(idleT);
          idleT = setTimeout(() => { bar.style.opacity = '0.3'; }, 5000);
        }
        document.addEventListener('mousemove', resetIdle);
        document.addEventListener('mousedown', resetIdle);
        resetIdle();
      })();
    `).catch(() => {});
    return { ok: true, windowId: browserWin.id };
  });

  /**
   * «Внешний браузер в плеере»: открывает URL системным браузером
   * (Firefox/Chrome/Edge или пользовательский путь из настроек).
   * Не создаёт отдельное ОС-окно — использует shell.openExternal.
   */
  ipcMain.handle('web:openExternalBrowser', async (event, url) => {
    if (typeof url !== 'string' || !/^https?:\/\//i.test(url)) {
      return { ok: false, reason: 'Некорректный URL' };
    }
    try {
      const { shell } = require('electron');
      await shell.openExternal(url);
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: String(e) };
    }
  });

  /** Закрыть встроенное browser-окно. */
  ipcMain.handle('web:closeBrowserWindow', async (event, windowId) => {
    if (windowId !== undefined) {
      const win = _browserWindows.get(windowId);
      if (win) { try { if (!win.isDestroyed()) win.close(); } catch {} _browserWindows.delete(windowId); }
    } else {
      for (const [id, win] of _browserWindows) {
        try { if (!win.isDestroyed()) win.close(); } catch {}
      }
      _browserWindows.clear();
    }
    return { ok: true };
  });


  /**
   * Фоновый поллинг: Electron main process каждые 0.5s проверяет
   * /api/screenshots/pending. Если есть ожидающие скриншоты — делает
   * capturePage() в скрытом окне и POST-ит результат на /api/screenshots/bridge.
   */
  let _screenshotPollTimer = null;
  function startScreenshotPolling() {
    if (_screenshotPollTimer) return;
    _screenshotPollTimer = setInterval(async () => {
      try {
        const r = await fetch(`http://127.0.0.1:${port()}/api/screenshots/pending`);
        const d = await r.json();
        if (!d.pending || d.pending.length === 0) return;
        // Обрабатываем каждый ожидающий скриншот
        for (const item of d.pending) {
          try {
            const shotWin = new BrowserWindow({
              width: 1280, height: 800,
              show: false,
              webPreferences: { contextIsolation: true, nodeIntegration: false },
            });
            await Promise.race([
              shotWin.loadURL(item.url),
              new Promise(res => setTimeout(res, 12000)),
            ]);
            await new Promise(res => setTimeout(res, 1500));
            const image = await shotWin.webContents.capturePage();
            const b64 = image.toPNG().toString('base64');
            await fetch(`http://127.0.0.1:${port()}/api/screenshots/bridge`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ url: item.url, b64, request_id: item.id }),
            });
            shotWin.close();
          } catch (e) {
            try { /* окно может быть уже закрыто */ } catch {}
          }
        }
      } catch (e) {
        // Бэкенд не запущен — тихо пропускаем
      }
    }, 500);
  }
  startScreenshotPolling();

  /**
   * Open a directory picker (for project selection).
   */
  ipcMain.handle('dialog:openDirectory', async (event, defaultPath) => {
    const { dialog } = require('electron');
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      defaultPath: defaultPath || app.getPath('home'),
    });
    return { canceled: result.canceled, path: result.canceled ? null : result.filePaths[0] };
  });
}

module.exports = { registerIpc };
