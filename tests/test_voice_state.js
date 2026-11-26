// Tests for the voice state machine in frontend/js/voice.js.
// voice.js is an IIFE that exposes window.voice._test = { transition, LEGAL, STATES }.
// We load it in a sandbox with mocked globals, then test transitions directly.
'use strict';
const assert = require('assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'media', 'voice.js'), 'utf8');

// ── Build a sandbox with all the browser globals voice.js needs ─────────────
function makeSandbox() {
    const listeners = {};
    const sandbox = {
        window: {},
        document: {
            getElementById: () => ({ classList: { add(){}, remove(){} }, addEventListener(){}, click(){} }),
            querySelector: () => null,
            addEventListener(){},
        },
        navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop(){} }, { stop(){} }] }) } },
        AudioContext: class { constructor(){ this.sampleRate = 48000; } close(){} suspend(){} resume(){} createAnalyser(){ return { fftSize: 512, getFloatTimeDomainData(){} }; } createMediaStreamSource(){ return { connect(){} }; } },
        webkitAudioContext: null,
        AudioWorkletNode: class { constructor(){ this.port = { postMessage(){}, close(){} }; } disconnect(){} },
        MediaRecorder: class { constructor(){ this.ondataavailable = null; this.onstop = null; } start(){} stop(){} },
        Blob: class { constructor(parts, opts){ this.parts = parts || []; this.type = (opts && opts.type) || ''; this.size = this.parts.reduce((s,p) => s + (p.size||0), 0); } },
        WebSocket: class { constructor(){ this.readyState = 0; this.onmessage = null; this.onclose = null; this.onerror = null; } send(){} close(){} },
        FileReader: class { readAsDataURL(){ this.onload && this.onload(); } },
        SpeechSynthesisUtterance: class { constructor(t){ this.text = t; this.onend = null; this.onerror = null; } },
        speechSynthesis: { speak(){}, cancel(){}, getVoices: () => [] },
        Audio: class { constructor(){ this.onended = null; this.onerror = null; } play(){ return Promise.resolve(); } pause(){} },
        URL: { createObjectURL: () => 'blob:x', revokeObjectURL(){} },
        performance: { now: () => Date.now() },
        console,
        setTimeout, clearTimeout, setInterval, clearInterval,
        fetch: async () => ({ json: async () => ({}) }),
        atob: s => Buffer.from(s, 'base64').toString('binary'),
        Int16Array, Float32Array, ArrayBuffer, Uint8Array, DataView,
        Object, Array, Promise, Error,
    };
    sandbox.window.location = { origin: 'http://127.0.0.1:8000' };
    sandbox.window.addEventListener = () => {};
    sandbox.window.AudioContext = sandbox.AudioContext;
    sandbox.window.webkitAudioContext = null;
    return sandbox;
}

// Load voice.js into the sandbox
function loadVoice() {
    const sb = makeSandbox();
    const fn = new Function(
        'window', 'document', 'navigator', 'AudioContext', 'webkitAudioContext',
        'AudioWorkletNode', 'MediaRecorder', 'Blob', 'WebSocket', 'FileReader',
        'SpeechSynthesisUtterance', 'speechSynthesis', 'Audio', 'URL',
        'performance', 'console', 'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
        'fetch', 'atob', 'Int16Array', 'Float32Array', 'ArrayBuffer', 'Uint8Array', 'DataView',
        'Object', 'Array', 'Promise', 'Error',
        src + '\nreturn window.voice;'
    );
    return fn(
        sb.window, sb.document, sb.navigator, sb.AudioContext, sb.webkitAudioContext,
        sb.AudioWorkletNode, sb.MediaRecorder, sb.Blob, sb.WebSocket, sb.FileReader,
        sb.SpeechSynthesisUtterance, sb.speechSynthesis, sb.Audio, sb.URL,
        sb.performance, sb.console, sb.setTimeout, sb.clearTimeout, sb.setInterval, sb.clearInterval,
        sb.fetch, sb.atob, sb.Int16Array, sb.Float32Array, sb.ArrayBuffer, sb.Uint8Array, sb.DataView,
        Object, Array, Promise, Error,
    );
}

let voice;
try {
    voice = loadVoice();
} catch (e) {
    console.error('Failed to load voice.js:', e.message);
    process.exit(1);
}

let passed = 0;
const t = (name, fn) => { fn(); console.log(`  PASS ${name}`); passed++; };
const LEGAL = voice._test.LEGAL;

// ── LEGAL transition table tests ────────────────────────────────────────────

t('off → listening is legal', () => {
    assert.ok(LEGAL.off.includes('listening'));
});

t('listening → recording is legal', () => {
    assert.ok(LEGAL.listening.includes('recording'));
});

t('listening → off is legal (user-initiated stop)', () => {
    assert.ok(LEGAL.listening.includes('off'));
});

t('recording → processing is legal', () => {
    assert.ok(LEGAL.recording.includes('processing'));
});

t('processing → responding is legal', () => {
    assert.ok(LEGAL.processing.includes('responding'));
});

t('processing → listening is legal (STT error/timeout)', () => {
    assert.ok(LEGAL.processing.includes('listening'));
});

t('processing → off is legal (stopAll)', () => {
    assert.ok(LEGAL.processing.includes('off'));
});

t('responding → speaking is legal', () => {
    assert.ok(LEGAL.responding.includes('speaking'));
});

t('responding → listening is legal (mic click aborts LLM)', () => {
    assert.ok(LEGAL.responding.includes('listening'));
});

t('responding → off is legal (stopAll)', () => {
    assert.ok(LEGAL.responding.includes('off'));
});

t('speaking → listening is legal (TTS complete)', () => {
    assert.ok(LEGAL.speaking.includes('listening'));
});

t('speaking → off is legal (mic click cancels TTS)', () => {
    assert.ok(LEGAL.speaking.includes('off'));
});

t('off is terminal (no outgoing from off except listening)', () => {
    assert.strictEqual(LEGAL.off.length, 1);
});

t('recording → listening is legal (force-stop VAD)', () => {
    assert.ok(LEGAL.recording.includes('listening'));
});

// ── States list ──────────────────────────────────────────────────────────────

t('STATES has 6 entries', () => {
    assert.strictEqual(voice._test.STATES.length, 6);
});

t('STATES order is correct', () => {
    assert.deepStrictEqual(voice._test.STATES, ['off', 'listening', 'recording', 'processing', 'responding', 'speaking']);
});

// ── transition() function exists and is callable ────────────────────────────

t('transition is a function', () => {
    assert.strictEqual(typeof voice._test.transition, 'function');
});

// ── getState returns off initially ───────────────────────────────────────────

t('initial state is off', () => {
    assert.strictEqual(voice.getState(), 'off');
});

// ── onStateChange works ──────────────────────────────────────────────────────

t('onStateChange subscribes and returns unsubscribe', () => {
    let called = 0;
    const unsub = voice.onStateChange(() => { called++; });
    assert.strictEqual(typeof unsub, 'function');
    unsub(); // should not throw
});

// ── Public API surface ───────────────────────────────────────────────────────

t('public API has all 5 methods', () => {
    assert.strictEqual(typeof voice.init, 'function');
    assert.strictEqual(typeof voice.startListening, 'function');
    assert.strictEqual(typeof voice.stopAll, 'function');
    assert.strictEqual(typeof voice.getState, 'function');
    assert.strictEqual(typeof voice.onStateChange, 'function');
});

console.log(`\n${passed} tests passed`);
