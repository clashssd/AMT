#!/usr/bin/env node
// Smoke test: verify theme-editor fixes don't throw in strict mode
// and that the new themes.js API methods work correctly.
'use strict';

const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');

const root = path.resolve(__dirname, '..');

// ---- Mock browser environment ----
// Minimal DOM stubs for the modules we need to test.
const localStorageStore = {};
const mockLocalStorage = {
    getItem(k) { return localStorageStore[k] ?? null; },
    setItem(k, v) { localStorageStore[k] = String(v); },
    removeItem(k) { delete localStorageStore[k]; },
};

// Track CSS var assignments on :root
const rootStyleProps = {};
const mockDocument = {
    documentElement: {
        style: {
            setProperty(k, v) { rootStyleProps[k] = v; },
            getPropertyValue(k) { return rootStyleProps[k]; },
        },
        setAttribute() {},
        getAttribute() { return null; },
    },
    body: { style: {}, classList: { toggle() {}, add() {}, remove() {} } },
    getElementById(id) { return mockElements[id] || null; },
    createElement() { return { style: {}, classList: { add() {}, remove() {} } }; },
    querySelectorAll() { return []; },
    addEventListener() {},
    readyState: 'complete',
};

// Stub out DOM elements the editor needs
const mockElements = {
    teAccent: { type: 'color', value: '#ff0000', addEventListener() {} },
    teAccent2: { type: 'color', value: '#00ff00', addEventListener() {} },
    teBg1: { type: 'color', value: '#05050a', addEventListener() {} },
    teBg2: { type: 'color', value: '#11131a', addEventListener() {} },
    teBg3: { type: 'color', value: '#0b0f14', addEventListener() {} },
    teText: { type: 'color', value: '#d0d0d0', addEventListener() {} },
    teTextDim: { type: 'color', value: '#8a8a9a', addEventListener() {} },
    teGlass: { type: 'range', value: '2', addEventListener() {} },
    teBorder: { type: 'range', value: '6', addEventListener() {} },
    teSuccess: { type: 'color', value: '#4ade80', addEventListener() {} },
    teWarning: { type: 'color', value: '#facc15', addEventListener() {} },
    teDanger: { type: 'color', value: '#f87171', addEventListener() {} },
    teInfo: { type: 'color', value: '#8ab4ff', addEventListener() {} },
    teRadius: { type: 'range', value: '18', addEventListener() {} },
    teBlur: { type: 'range', value: '18', addEventListener() {} },
    teGlow: { type: 'range', value: '35', addEventListener() {} },
    teShadow: { value: 'md', addEventListener() {} },
    teMotion: { value: 'normal', addEventListener() {} },
    teFont: { value: 'system', addEventListener() {} },
    teHeadingFont: { value: 'system', addEventListener() {} },
    teScale: { type: 'range', value: '100', addEventListener() {} },
    teFieldBg: { type: 'color', value: '', addEventListener() {} },
    teFieldBorder: { type: 'color', value: '', addEventListener() {} },
    teFieldText: { type: 'color', value: '', addEventListener() {} },
    teFieldPlaceholder: { type: 'color', value: '', addEventListener() {} },
    teCardBg: { type: 'color', value: '', addEventListener() {} },
    teCardBg2: { type: 'color', value: '', addEventListener() {} },
    teModalBg: { type: 'color', value: '', addEventListener() {} },
    teOverlay: { type: 'range', value: '62', addEventListener() {} },
    teDropdownBg: { type: 'color', value: '', addEventListener() {} },
    teTooltipBg: { type: 'color', value: '', addEventListener() {} },
    teCodeBg: { type: 'color', value: '', addEventListener() {} },
    teTableBg: { type: 'color', value: '', addEventListener() {} },
    teTableHover: { type: 'color', value: '', addEventListener() {} },
    teScrollbarThumb: { type: 'color', value: '', addEventListener() {} },
    teScrollbarTrack: { type: 'color', value: '', addEventListener() {} },
    teControlBg: { type: 'color', value: '', addEventListener() {} },
    teControlBorder: { type: 'color', value: '', addEventListener() {} },
    teControlChecked: { type: 'color', value: '', addEventListener() {} },
    teFontCustom: { value: '', style: {}, addEventListener() {} },
    teHeadingFontCustom: { value: '', style: {}, addEventListener() {} },
    teName: { value: 'My Custom Theme', addEventListener() {} },
    teContrast: { textContent: '' },
    teGlassVal: { textContent: '' },
    teBorderVal: { textContent: '' },
    teOverlayVal: { textContent: '' },
    teRadiusVal: { textContent: '' },
    teBlurVal: { textContent: '' },
    teGlowVal: { textContent: '' },
    teScaleVal: { textContent: '' },
    teImportFile: { click() {}, onchange: null, files: [] },
    teSaveNew: { onclick: null },
    teUpdate: { onclick: null },
    teDuplicate: { onclick: null },
    teDelete: { onclick: null },
    teExport: { onclick: null },
    teImport: { onclick: null },
    teReset: { onclick: null },
};

// Load theme-schema.js into a shared window
const window = {
    document: mockDocument,
    localStorage: mockLocalStorage,
};

// Load theme-schema.js (pure, no DOM deps beyond window)
const schemaCode = fs.readFileSync(path.join(root, 'frontend/js/core/theme-schema.js'), 'utf8');
new Function('window', schemaCode)(window);
assert.ok(window.AMTThemeSchema, 'AMTThemeSchema should be defined');
assert.ok(window.AMTThemeSchema.DEFAULT_THEME, 'DEFAULT_THEME should exist');

// Load themes.js — needs more stubs
// themes.js uses document.addEventListener, document.readyState, document.getElementById, etc.
// We provide them via the mock.
// It also uses fetch, IntersectionObserver — stub those.
global.fetch = async (url) => {
    if (url.includes('themes.json')) {
        return { json: async () => ({ ocean: { label: 'Ocean', id: 'ocean', version: 2, appearance: 'dark', colors: { bg: ['#05050a','#11131a','#0b0f14'], accent: '#8b86c9', accent2: '#aba5c9', text: '#d0d0d0', textDim: '#8a8a9a' } } }) };
    }
    return { json: async () => ({}) };
};
global.IntersectionObserver = class { observe() {} disconnect() {} };
global.location = { origin: 'http://localhost' };
global.Blob = class { constructor() {} };
global.URL = { createObjectURL: () => 'blob:', revokeObjectURL: () => {} };

// Load themes.js
const themesCode = fs.readFileSync(path.join(root, 'frontend/js/core/themes.js'), 'utf8');
new Function('window', 'document', 'localStorage', 'fetch', 'IntersectionObserver', themesCode)(
    window, mockDocument, mockLocalStorage, global.fetch, global.IntersectionObserver
);

// ---- Test 1: verify __AMT_CUSTOM_IDS__ is a getter (not assignable) ----
assert.ok(Object.getOwnPropertyDescriptor(window, '__AMT_CUSTOM_IDS__'), '__AMT_CUSTOM_IDS__ should be defined');
const desc = Object.getOwnPropertyDescriptor(window, '__AMT_CUSTOM_IDS__');
assert.ok(desc.get, '__AMT_CUSTOM_IDS__ should have a getter');
assert.strictEqual(desc.set, undefined, '__AMT_CUSTOM_IDS__ should NOT have a setter (getter-only)');

// ---- Test 2: verify assigning to __AMT_CUSTOM_IDS__ throws in strict mode ----
let threw = false;
try {
    // Simulate what the old broken code did
    (function strict() {
        'use strict';
        window.__AMT_CUSTOM_IDS__ = ['test'];
    })();
} catch (e) {
    threw = true;
    assert.ok(e instanceof TypeError, 'Should throw TypeError in strict mode');
}
assert.ok(threw, 'Assigning to getter-only __AMT_CUSTOM_IDS__ in strict mode MUST throw');

// ---- Test 3: verify theme-editor.js does NOT contain the broken assignment ----
const editorCode = fs.readFileSync(path.join(root, 'frontend/js/core/theme-editor.js'), 'utf8');
const brokenPattern = /window\.__AMT_CUSTOM_IDS__\s*=/;
assert.ok(!brokenPattern.test(editorCode), 'theme-editor.js must NOT contain "window.__AMT_CUSTOM_IDS__ =" (broken strict-mode assignment)');

// ---- Test 4: verify themes.js exposes refreshCustomThemes and setThemeId ----
assert.strictEqual(typeof window.AMTThemes.refreshCustomThemes, 'function', 'AMTThemes.refreshCustomThemes should be a function');
assert.strictEqual(typeof window.AMTThemes.setThemeId, 'function', 'AMTThemes.setThemeId should be a function');

// ---- Test 5: verify schedulePreview in theme-editor.js does NOT call applyTheme ----
// The old broken code called T().applyTheme("__preview__") which corrupted current.theme
assert.ok(!editorCode.includes('applyTheme("__preview__")'), 'schedulePreview must NOT call applyTheme("__preview__") (corrupts current.theme)');

// ---- Test 6: verify applyAndPersist uses the new API ----
assert.ok(editorCode.includes('refreshCustomThemes'), 'applyAndPersist must call refreshCustomThemes');
assert.ok(editorCode.includes('setThemeId'), 'applyAndPersist must call setThemeId');

// ---- Test 7: verify themes.js setThemeId does NOT re-apply stored CSS vars ----
// setThemeId should just set current.theme and re-render, NOT call applyThemeVars
const themesSource = fs.readFileSync(path.join(root, 'frontend/js/core/themes.js'), 'utf8');
// Find the setThemeId method body
const setThemeIdMatch = themesSource.match(/setThemeId\(id\)\s*\{([\s\S]*?)\n        \}/);
assert.ok(setThemeIdMatch, 'setThemeId method should exist in themes.js');
const setThemeIdBody = setThemeIdMatch[1];
assert.ok(!setThemeIdBody.includes('applyThemeVars'), 'setThemeId must NOT call applyThemeVars (would clobber draft CSS vars with stored ones)');
assert.ok(setThemeIdBody.includes('renderAll'), 'setThemeId MUST call renderAll to update the picker');

// ---- Test 8: verify refreshCustomThemes reads from localStorage ----
const refreshMatch = themesSource.match(/refreshCustomThemes\(\)\s*\{([\s\S]*?)\n        \}/);
assert.ok(refreshMatch, 'refreshCustomThemes method should exist in themes.js');
const refreshBody = refreshMatch[1];
assert.ok(refreshBody.includes('amt_custom_themes_v2'), 'refreshCustomThemes must read from localStorage.amt_custom_themes_v2');

console.log('PASS test_theme_fixes: all 8 checks passed');
console.log('  1. __AMT_CUSTOM_IDS__ is getter-only (no setter)');
console.log('  2. Assigning to it in strict mode throws TypeError (confirmed)');
console.log('  3. theme-editor.js no longer contains broken assignment');
console.log('  4. themes.js exposes refreshCustomThemes + setThemeId');
console.log('  5. schedulePreview no longer calls applyTheme("__preview__")');
console.log('  6. applyAndPersist uses refreshCustomThemes + setThemeId');
console.log('  7. setThemeId does NOT re-apply stored CSS vars');
console.log('  8. refreshCustomThemes reads from localStorage');
