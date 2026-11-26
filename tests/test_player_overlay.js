// Tests for the media-overlay fixes: floating drag handle, iframe controls
// (filters for YT/Twitch embeds), stream loading indicator, web search
// link cards, and external-browser opening (Electron IPC + preload).
//
// Uses the same plain-Node source-check pattern as test_stream_cards.js —
// the player-browser.js functions live inside an IIFE, so we assert on
// source content rather than executing them with a DOM mock.
'use strict';
const assert = require('assert');
const fs = require('node:fs');
const path = require('node:path');

const read = (rel) => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');

// main.js was split: core definitions in core/main.js, the media IIFE in
// media/media-overlay.js, bootstrap IIFEs in core/bootstrap.js, and the
// DOMContentLoaded handler in core/init.js. Combine the pieces that carry
// the assertions below (core defs + media overlay) so source checks keep working.
const mainSrc = read('frontend/js/core/main.js') + '\n' + read('frontend/js/media/media-overlay.js');
const playerSrc = read('frontend/js/media/player-browser.js');
const ipcSrc = read('electron/ipc.js');
const preloadSrc = read('electron/preload.js');
const homeSrc = read('frontend/home.html');
const cssSrc = read('frontend/css/style.css');

let passed = 0;
const t = (name, fn) => {
  try { fn(); console.log('  PASS ' + name); passed++; }
  catch (e) {
    console.log('  FAIL ' + name + ': ' + e.message);
    console.log('    ' + (e.stack || '').split('\n').find(l => l.trim().startsWith('at')) || '');
    process.exitCode = 1;
  }
};

// ===================== 1. Native confirm() removal =====================
t('main.js: no native confirm() calls outside amtConfirm fallback', () => {
  // Remove // comments first so the descriptive comment line doesn't count.
  const code = mainSrc.replace(/\/\/[^\n]*/g, '');
  const matches = code.match(/(?<!amt)(?<!\.)\bconfirm\s*\(/g) || [];
  assert.strictEqual(matches.length, 1,
    'Expected exactly 1 native confirm( (the fallback inside amtConfirm), got ' + matches.length);
});

t('main.js: amtConfirm fallback remains', () => {
  assert.ok(mainSrc.includes('if (!modal) return Promise.resolve(confirm(text))'));
});

t('main.js: clearHistory uses amtConfirm with app-UI modal', () => {
  const idx = mainSrc.indexOf('function clearHistory');
  assert.ok(idx > 0, 'clearHistory not found');
  const fn = mainSrc.slice(idx, idx + 400);
  assert.ok(fn.includes('amtConfirm'), 'clearHistory should use amtConfirm');
});

// ===================== 2. Floating mini-window drag =====================
t('home.html: media overlay has drag handle element', () => {
  assert.ok(homeSrc.includes('id="mediaOverlayDrag"'), 'drag handle element missing');
  assert.ok(homeSrc.includes('class="media-overlay-drag"'));
});

t('main.js: floating entry clears inline styles so CSS .floating applies', () => {
  const idx = mainSrc.indexOf('Вход в floating');
  assert.ok(idx > 0, 'floating entry branch marker not found');
  const slice = mainSrc.slice(idx, idx + 400);
  assert.ok(slice.includes("overlay.style.left = ''"), 'inline left must be cleared');
  assert.ok(slice.includes("overlay.style.width = ''"), 'inline width must be cleared');
  assert.ok(slice.includes("overlay.classList.add('floating')"), 'must add .floating class');
});

t('main.js: drag attached to drag handle, not overlay body', () => {
  assert.ok(mainSrc.includes("const dragSource = dragHandle || overlay"),
    'drag must prefer the handle element');
  assert.ok(mainSrc.includes("dragSource.addEventListener('mousedown'"),
    'mousedown listener must be on dragSource');
  assert.ok(mainSrc.includes("overlay.classList.add('dragging')"));
});

t('main.js: drag only in floating mode and clamped to viewport', () => {
  assert.ok(mainSrc.includes("if (!overlay.classList.contains('floating')) return;"),
    'drag must be no-op when not floating');
  assert.ok(mainSrc.includes('window.innerWidth - ow'), 'x must be clamped');
  assert.ok(mainSrc.includes('window.innerHeight - oh'), 'y must be clamped');
});

t('css: .media-overlay.floating sets fixed top-right position', () => {
  const idx = cssSrc.indexOf('.media-overlay.floating');
  assert.ok(idx > 0, '.media-overlay.floating rule missing');
  const rule = cssSrc.slice(idx, idx + 400);
  assert.ok(/top\s*:\s*\d+px/.test(rule), 'floating should have top offset');
  assert.ok(/right\s*:\s*\d+px/.test(rule), 'floating should have right offset');
  assert.ok(/width\s*:\s*\d+px/.test(rule), 'floating should have a width');
});

t('css: drag handle visible only in floating mode', () => {
  assert.ok(cssSrc.includes('.media-overlay.floating .media-overlay-drag'),
    'floating must reveal the drag handle');
});

// ===================== 3. Iframe controls + filters button =====================
t('main.js: showIframeControls adds .iframe-mode and shows controls', () => {
  assert.ok(mainSrc.includes("controls.classList.add('iframe-mode')"),
    'iframe mode must be marked on the controls bar');
});

t('main.js: video-iframe and stream branches enable controls', () => {
  const count = mainSrc.split('showIframeControls();').length - 1;
  assert.ok(count >= 2, 'expected showIframeControls called in both video-iframe and stream branches, got ' + count);
});

t('main.js: native video branch clears iframe-mode', () => {
  assert.ok(mainSrc.includes("controls.classList.remove('iframe-mode')"),
    'native <video> must reset iframe-mode');
});

t('css: .iframe-mode hides video-only buttons, keeps filters', () => {
  assert.ok(cssSrc.includes('.media-player-controls.iframe-mode #playerPlayPause'),
    'play/pause hidden in iframe mode');
  assert.ok(cssSrc.includes('.media-player-controls.iframe-mode .player-timeline'),
    'timeline hidden in iframe mode');
  // filters button must NOT be hidden
  const ruleBlock = cssSrc.slice(cssSrc.indexOf('.media-player-controls.iframe-mode'));
  assert.ok(!/iframe-mode\s+#playerFiltersToggle/.test(cssSrc),
    'filters toggle must stay visible in iframe mode');
});

t('main.js: stream loading indicator present', () => {
  assert.ok(mainSrc.includes("loader.className = 'stream-loading'"),
    'iframe embeds should show a loading spinner');
  assert.ok(mainSrc.includes('Не удаётся загрузить'), 'timeout message expected');
  assert.ok(cssSrc.includes('.stream-loading::before'), 'spinner animation css missing');
});

// ===================== 4. Web search: link cards + external browser =====================
t('player-browser.js: 3-way kind toggle (auto/video/web)', () => {
  assert.ok(playerSrc.includes("key: 'auto'"), 'auto kind missing');
  assert.ok(playerSrc.includes("key: 'video'"), 'video kind missing');
  assert.ok(playerSrc.includes("key: 'web'"), 'web kind missing');
  assert.ok(playerSrc.includes("kind === 'video' ? 'youtube'"), 'video→youtube mapping missing');
});

t('player-browser.js: web results render as link cards, not iframes', () => {
  assert.ok(playerSrc.includes('function makeWebLinkCard'), 'web link card factory missing');
  assert.ok(playerSrc.includes('sidebar-video-card web-link'));
  assert.ok(playerSrc.includes('Открыть в браузере'), 'open-in-browser button missing');
});

t('player-browser.js: web result in main area shows link card', () => {
  // round-5: web link now loads INTO the player (iframe attempt + fallback card inside mainEl)
  assert.ok(playerSrc.includes("vid.platform === 'web' || (!vid.id && vid.url)"),
    'web branch in loadVideoIntoMain missing');
  assert.ok(playerSrc.includes('web-link-main'), 'main-area link card missing');
  assert.ok(playerSrc.includes('X-Frame-Options'), 'explanatory note expected');
  assert.ok(playerSrc.includes('setTimeout(showBlocked, 4000)'), '4s blocked-timeout expected');
});

t('player-browser.js: youtube thumbnail fallback for video results', () => {
  assert.ok(playerSrc.includes('i.ytimg.com'), 'ytimg thumbnail fallback missing');
});

t('player-browser.js: channel fallback opens channel in browser', () => {
  assert.ok(playerSrc.includes('function openChannelInBrowser'), 'channel fallback missing');
  assert.ok(playerSrc.includes('Открыть канал в браузере'), 'channel open button missing');
});

// ===================== 5. Electron IPC: open external browser =====================
t('ipc.js: shell:openExternal handler validates URL', () => {
  assert.ok(ipcSrc.includes("ipcMain.handle('shell:openExternal'"), 'IPC handler missing');
  assert.ok(ipcSrc.includes('shell.openExternal'), 'shell.openExternal not used');
  assert.ok(/https?\?:/.test(ipcSrc), 'URL scheme validation missing');
});

t('preload.js: exposes api.openExternal', () => {
  assert.ok(preloadSrc.includes('openExternal:'), 'api.openExternal not exposed');
  assert.ok(preloadSrc.includes("'shell:openExternal'"), 'channel name mismatch');
});

t('player-browser.js: openInBrowser prefers api.openExternal, falls back to window.open', () => {
  assert.ok(playerSrc.includes('window.api.openExternal'), 'IPC preferred path missing');
  assert.ok(playerSrc.includes("window.open(url, '_blank'"), 'window.open fallback missing');
});

console.log('\n' + passed + ' player-overlay tests passed');
if (passed === 0) process.exit(1);
