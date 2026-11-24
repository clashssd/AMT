// Tests for stream-card rendering, media-in-text rendering, and setBotContent
// — the fixes that make YouTube/Twitch links render as clickable preview cards.
//
// Uses a minimal DOM mock so we can run in plain Node without jsdom.
'use strict';
const assert = require('assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'main.js'), 'utf8');

// ---- Minimal DOM mock ----
function makeTextNode(value) {
  return { nodeType: 3, nodeValue: value, parentNode: null };
}

function makeElement(tag) {
  const el = {
    nodeType: 1,
    tagName: tag.toUpperCase(),
    children: [],
    childNodes: [],
    _classes: new Set(),
    dataset: {},
    _textContent: '',
    _innerHTML: '',
    style: {},
    parentNode: null,
    listeners: {},
    classList: {
      add(...c) { c.forEach(x => el._classes.add(x)); },
      remove(...c) { c.forEach(x => el._classes.delete(x)); },
      contains(c) { return el._classes.has(c); },
      get length() { return el._classes.size; },
      [Symbol.iterator]() { return el._classes[Symbol.iterator](); },
    },
    addEventListener(type, fn) {
      if (!el.listeners[type]) el.listeners[type] = [];
      el.listeners[type].push(fn);
    },
    appendChild(child) {
      // If child is a DocumentFragment, flatten its children into this element
      if (child.nodeType === 11) {
        for (const c of child.children) {
          el.children.push(c);
          el.childNodes.push(c);
          c.parentNode = el;
        }
        return child;
      }
      // Remove from current parent if re-appending (move semantics)
      if (child.parentNode) {
        const pc = child.parentNode.children.indexOf(child);
        if (pc >= 0) child.parentNode.children.splice(pc, 1);
        const pn = child.parentNode.childNodes.indexOf(child);
        if (pn >= 0) child.parentNode.childNodes.splice(pn, 1);
      }
      el.children.push(child);
      el.childNodes.push(child);
      child.parentNode = el;
      return child;
    },
    removeChild(child) {
      const ci = el.children.indexOf(child);
      if (ci >= 0) el.children.splice(ci, 1);
      const ni = el.childNodes.indexOf(child);
      if (ni >= 0) el.childNodes.splice(ni, 1);
      return child;
    },
    querySelector(sel) {
      const cls = sel.startsWith('.') ? sel.slice(1) : null;
      let found = null;
      const walk = (node) => {
        if (found) return;
        for (const c of (node.children || [])) {
          if (c.nodeType !== 1) continue;
          if (cls && c._classes && c._classes.has(cls)) { found = c; return; }
          walk(c);
        }
      };
      walk(el);
      return found;
    },
    querySelectorAll(sel) {
      const cls = sel.startsWith('.') ? sel.slice(1) : null;
      const results = [];
      const walk = (node) => {
        for (const c of (node.children || [])) {
          if (c.nodeType !== 1) continue;
          if (cls && c._classes && c._classes.has(cls)) results.push(c);
          walk(c);
        }
      };
      walk(el);
      return results;
    },
    get textContent() {
      let result = '';
      for (const node of el.childNodes) {
        if (node.nodeType === 3) result += node.nodeValue;
        else if (node.nodeType === 1) result += node.textContent;
      }
      return result;
    },
    set textContent(v) {
      if (v === '') { el.children = []; el.childNodes = []; }
      el._textContent = v;
    },
    get className() { return [...el._classes].join(' '); },
    set className(v) {
      el._classes.clear();
      if (v) v.split(/\s+/).forEach(c => el._classes.add(c));
    },
    get innerHTML() { return el._innerHTML; },
    set innerHTML(v) {
      el._innerHTML = v;
      el.children = [];
      el.childNodes = [];
      el._textContent = '';
      if (v) {
        // For mock simplicity: treat innerHTML content as a text node
        // so textContent getter can read it
        const tn = makeTextNode(String(v));
        el.children.push(tn);
        el.childNodes.push(tn);
        tn.parentNode = el;
      }
    },
    remove() {
      if (el.parentNode) {
        const ci = el.parentNode.children.indexOf(el);
        if (ci >= 0) el.parentNode.children.splice(ci, 1);
        const ni = el.parentNode.childNodes.indexOf(el);
        if (ni >= 0) el.parentNode.childNodes.splice(ni, 1);
      }
    },
  };
  return el;
}

function makeDocumentFragment() {
  return {
    nodeType: 11, // DOCUMENT_FRAGMENT_NODE
    children: [],
    childNodes: [],
    appendChild(child) { this.children.push(child); this.childNodes.push(child); return child; },
  };
}

function makeDocument() {
  return {
    createElement: (tag) => makeElement(tag),
    createTextNode: (text) => makeTextNode(text),
    createDocumentFragment: () => makeDocumentFragment(),
  };
}

// ---- Extract functions from main.js ----
function extractFn(name) {
  const start = src.indexOf('function ' + name + '(');
  assert.ok(start > 0, name + ' not found in main.js');
  let i = src.indexOf('{', start), depth = 0, end = -1;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
  }
  return src.slice(start, end);
}

function extractMediaUrlRe() {
  const idx = src.indexOf('const MEDIA_URL_RE =');
  assert.ok(idx > 0, 'MEDIA_URL_RE not found');
  const end = src.indexOf(';', idx);
  return eval(src.slice(idx + 'const MEDIA_URL_RE ='.length, end).trim());
}

const MEDIA_URL_RE = extractMediaUrlRe();

// ---- Build a test scope ----
function buildScope() {
  const doc = makeDocument();
  const scope = {
    document: doc,
    Node: { ELEMENT_NODE: 1, TEXT_NODE: 3 },
    escapeHtml(s) {
      return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },
    addMediaOpenBtn(wrap, label, onclick) {
      const btn = doc.createElement('button');
      btn.className = 'media-open-btn';
      btn.textContent = label;
      wrap.appendChild(btn);
      return btn;
    },
    addMediaDownload() {},
    markdownToHtml(text) {
      // Minimal markdown-to-HTML for testing
      return String(text)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
    },
    overlayCalls: [],
    MEDIA_URL_RE,
    b64ToDataUrl(b64, mime) { return 'data:' + mime + ';base64,' + b64; },
    scrollToBottom() {},
    scrollToBottomIfNear() {},
    flashStatus() {},
  };
  const winObj = {
    openMediaOverlay: (type, srcUrl) => { scope.overlayCalls.push({ type, src: srcUrl }); },
  };
  scope.window = winObj;
  return scope;
}

function runInScope(fnSource, scope, fnNames) {
  const names = Array.isArray(fnNames) ? fnNames : [fnNames];
  const params = [
    'document', 'escapeHtml', 'addMediaOpenBtn', 'addMediaDownload',
    'MEDIA_URL_RE', 'b64ToDataUrl', 'window', 'Node', 'scrollToBottom', 'scrollToBottomIfNear', 'flashStatus',
    'markdownToHtml',
  ];
  const args = [
    scope.document, scope.escapeHtml, scope.addMediaOpenBtn, scope.addMediaDownload,
    scope.MEDIA_URL_RE, scope.b64ToDataUrl, scope.window, scope.Node,
    scope.scrollToBottom, scope.scrollToBottomIfNear, scope.flashStatus, scope.markdownToHtml,
  ];
  return new Function(...params, fnSource + '\nreturn { ' + names.join(', ') + ' };')(...args);
}

// ---- Helper ----
function makeContentEl(text, extraElements) {
  const contentEl = makeElement('div');
  contentEl.classList.add('message-content');
  contentEl.appendChild(makeTextNode(text));
  if (extraElements) for (const el of extraElements) contentEl.appendChild(el);
  const root = makeElement('div');
  root.appendChild(contentEl);
  return { contentEl, root };
}

// ================================================================
// Tests
// ================================================================
let passed = 0;
const t = (name, fn) => {
  try {
    fn();
    console.log('  PASS ' + name);
    passed++;
  } catch (e) {
    console.log('  FAIL ' + name + ': ' + e.message);
    console.log('    ' + (e.stack || '').split('\n').find(l => l.trim().startsWith('at')) || '');
    process.exitCode = 1;
  }
};

const enhanceStreamCardsSrc = extractFn('enhanceStreamCards');
const renderMediaInTextSrc = extractFn('renderMediaInText');
const setBotContentSrc = extractFn('setBotContent');

// ---- Test 1: YouTube watch URL -> stream card ----
t('enhanceStreamCards converts YouTube watch URL to stream card', () => {
  const scope = buildScope();
  const { contentEl, root } = makeContentEl('Watch this: https://www.youtube.com/watch?v=dQw4w9WgXcQ enjoy');
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  const cards = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card'));
  assert.strictEqual(cards.length, 1, 'Expected 1 stream-card, got ' + cards.length);
  assert.strictEqual(cards[0].dataset.url, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ');
});

// ---- Test 2: youtu.be short URL ----
t('enhanceStreamCards converts youtu.be short URL', () => {
  const scope = buildScope();
  const { contentEl, root } = makeContentEl('https://youtu.be/abc123');
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  const cards = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card'));
  assert.strictEqual(cards.length, 1);
  assert.strictEqual(cards[0].dataset.url, 'https://youtu.be/abc123');
});

// ---- Test 3: Twitch URL -> LIVE card ----
t('enhanceStreamCards converts Twitch URL to LIVE card', () => {
  const scope = buildScope();
  const { contentEl, root } = makeContentEl('Live: https://twitch.tv/somechannel now');
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  const cards = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card'));
  assert.strictEqual(cards.length, 1);
  assert.ok(cards[0]._classes.has('live'), 'Twitch card should have .live class');
});

// ---- Test 4: non-stream URL becomes web-link card ----
t('enhanceStreamCards converts non-stream URLs to web-link cards', () => {
  const scope = buildScope();
  const { contentEl, root } = makeContentEl('https://lordfilm.xyz/movie/hateful-eight');
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  const cards = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card'));
  assert.strictEqual(cards.length, 1, 'Should create 1 web-link card');
  assert.ok(cards[0]._classes.has('web-link'), 'Card should have .web-link class');
});

// ---- Test 5: skip already-processed ----
t('enhanceStreamCards skips content that already has stream-card', () => {
  const scope = buildScope();
  const contentEl = makeElement('div');
  contentEl.classList.add('message-content');
  const existingCard = makeElement('div');
  existingCard._classes.add('stream-card');
  contentEl.appendChild(existingCard);
  contentEl.appendChild(makeTextNode('https://www.youtube.com/watch?v=xyz'));
  const root = makeElement('div');
  root.appendChild(contentEl);

  const before = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card')).length;
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  const after = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card')).length;
  assert.strictEqual(after, before, 'Should not add more cards to already-processed content');
});

// ---- Test 6: preserves video element ----
t('enhanceStreamCards preserves video element from renderMediaInText', () => {
  const scope = buildScope();
  const videoEl = makeElement('video');
  videoEl.src = 'https://example.com/test.mp4';
  const { contentEl, root } = makeContentEl('Here is a video:  and a stream: https://www.youtube.com/watch?v=abc123', [videoEl]);
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  const videos = contentEl.children.filter(c => c.nodeType === 1 && c.tagName === 'VIDEO');
  assert.strictEqual(videos.length, 1, 'Video element should be preserved');
  const cards = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card'));
  assert.strictEqual(cards.length, 1, 'Stream card should be created');
});

// ---- Test 7: preserves audio and img ----
t('enhanceStreamCards preserves audio and img elements', () => {
  const scope = buildScope();
  const audioEl = makeElement('audio'); audioEl.src = 'https://example.com/song.mp3';
  const imgEl = makeElement('img'); imgEl.src = 'https://example.com/pic.png';
  const { contentEl, root } = makeContentEl('Audio:  Image:  Stream: https://www.youtube.com/watch?v=abc123', [audioEl, imgEl]);
  const { enhanceStreamCards } = runInScope(enhanceStreamCardsSrc, scope, ['enhanceStreamCards']);
  enhanceStreamCards(root);
  assert.strictEqual(contentEl.children.filter(c => c.nodeType === 1 && c.tagName === 'AUDIO').length, 1);
  assert.strictEqual(contentEl.children.filter(c => c.nodeType === 1 && c.tagName === 'IMG').length, 1);
});

// ---- Test 8: setBotContent triggers stream card ----
t('setBotContent triggers stream card enhancement', () => {
  const scope = buildScope();
  const allSrc = renderMediaInTextSrc + '\n' + enhanceStreamCardsSrc + '\n' + setBotContentSrc;
  const { setBotContent } = runInScope(allSrc, scope, ['setBotContent']);

  const msgEl = makeElement('div');
  const contentEl = makeElement('div');
  contentEl.classList.add('message-content');
  msgEl.appendChild(contentEl);

  setBotContent(msgEl, 'Watch: https://www.youtube.com/watch?v=dQw4w9WgXcQ');

  const cards = contentEl.children.filter(c => c.nodeType === 1 && c._classes.has('stream-card'));
  assert.strictEqual(cards.length, 1, 'setBotContent should create a stream card');
});

// ---- Test 9: setBotContent renders .mp4 video ----
t('setBotContent renders inline video for .mp4 URLs', () => {
  const scope = buildScope();
  const allSrc = renderMediaInTextSrc + '\n' + enhanceStreamCardsSrc + '\n' + setBotContentSrc;
  const { setBotContent } = runInScope(allSrc, scope, ['setBotContent']);

  const msgEl = makeElement('div');
  const contentEl = makeElement('div');
  contentEl.classList.add('message-content');
  msgEl.appendChild(contentEl);

  setBotContent(msgEl, 'Video: https://cdn.example.com/video.mp4 done');

  const videos = contentEl.children.filter(c => c.nodeType === 1 && c.tagName === 'VIDEO');
  assert.strictEqual(videos.length, 1, 'Should create inline video element');
  assert.strictEqual(videos[0].src, 'https://cdn.example.com/video.mp4');
});

// ---- Test 10: setBotContent renders .mp3 audio ----
t('setBotContent renders inline audio for .mp3 URLs', () => {
  const scope = buildScope();
  const allSrc = renderMediaInTextSrc + '\n' + enhanceStreamCardsSrc + '\n' + setBotContentSrc;
  const { setBotContent } = runInScope(allSrc, scope, ['setBotContent']);

  const msgEl = makeElement('div');
  const contentEl = makeElement('div');
  contentEl.classList.add('message-content');
  msgEl.appendChild(contentEl);

  setBotContent(msgEl, 'Audio: https://cdn.example.com/song.mp3 end');

  const audios = contentEl.children.filter(c => c.nodeType === 1 && c.tagName === 'AUDIO');
  assert.strictEqual(audios.length, 1, 'Should create inline audio element');
});

// ---- Test 11: setBotContent renders .png image ----
t('setBotContent renders inline image for .png URLs', () => {
  const scope = buildScope();
  const allSrc = renderMediaInTextSrc + '\n' + enhanceStreamCardsSrc + '\n' + setBotContentSrc;
  const { setBotContent } = runInScope(allSrc, scope, ['setBotContent']);

  const msgEl = makeElement('div');
  const contentEl = makeElement('div');
  contentEl.classList.add('message-content');
  msgEl.appendChild(contentEl);

  setBotContent(msgEl, 'Image: https://cdn.example.com/pic.png');

  const imgs = contentEl.children.filter(c => c.nodeType === 1 && c.tagName === 'IMG');
  assert.strictEqual(imgs.length, 1, 'Should create inline img element');
  assert.strictEqual(imgs[0].src, 'https://cdn.example.com/pic.png');
});

// ---- Test 12: source check — streamViaWebSocket done handler ----
t('streamViaWebSocket done handler calls enhanceStreamCards', () => {
  const doneBlockStart = src.indexOf("data.type === 'done'");
  assert.ok(doneBlockStart > 0, "done handler not found");
  const slice = src.slice(doneBlockStart, doneBlockStart + 4000);
  assert.ok(slice.includes('renderMediaInText'), 'done handler should call renderMediaInText');
  assert.ok(slice.includes('enhanceStreamCards'), 'done handler should call enhanceStreamCards');
});

// ---- Test 13: source check — setBotContent ----
t('setBotContent source calls enhanceStreamCards', () => {
  const setBotIdx = src.indexOf('function setBotContent(');
  assert.ok(setBotIdx > 0, 'setBotContent not found');
  const slice = src.slice(setBotIdx, setBotIdx + 400);
  assert.ok(slice.includes('enhanceStreamCards'), 'setBotContent should call enhanceStreamCards');
});

// ---- Test 14: source check — direct video URL handler ----
t('renderGenInChat video handler handles res.url without task_id', () => {
  const videoBlockStart = src.indexOf("if (res.ok && res.url && !res.task_id)");
  assert.ok(videoBlockStart > 0, 'Direct URL video handler not found in renderGenInChat');
  const slice = src.slice(videoBlockStart, videoBlockStart + 500);
  assert.ok(slice.includes('video'), 'Direct URL handler should create video element');
  assert.ok(slice.includes('openMediaOverlay'), 'Direct URL handler should have overlay button');
});

// ---- Test 15: source check — task_id polling still works ----
t('renderGenInChat video handler still handles task_id polling', () => {
  const taskBlockStart = src.indexOf("else if (res.ok && res.task_id)");
  assert.ok(taskBlockStart > 0, 'task_id handler not found in renderGenInChat');
  const slice = src.slice(taskBlockStart, taskBlockStart + 800);
  assert.ok(slice.includes('pollVideoTaskChat'), 'task_id handler should call pollVideoTaskChat');
});

console.log('\n' + passed + ' stream-card/media tests passed');
if (passed === 0) process.exit(1);
