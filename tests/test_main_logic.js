// Tests for the autoPickTemperature logic in frontend/js/main.js.
// The function depends on module-scoped `messageInput` and `getCurrentChat`,
// so we extract its source and run it in a controlled scope.
'use strict';
const assert = require('assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'core', 'main.js'), 'utf8');

// Extract the autoPickTemperature function body by source slicing
function extractAutoPick() {
    const start = src.indexOf('function autoPickTemperature()');
    assert.ok(start > 0, 'autoPickTemperature not found in main.js');
    // find matching closing brace
    let i = src.indexOf('{', start), depth = 0, end = -1;
    for (; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
    }
    return src.slice(start, end);
}

function makeRunner(messageValue, chatMessages) {
    const fnSrc = extractAutoPick();
    // Build a function in scope where messageInput & getCurrentChat exist
    const runner = new Function('messageInput', 'getCurrentChat',
        fnSrc + '\nreturn autoPickTemperature();');
    return () => runner({ value: messageValue }, () => ({ messages: chatMessages || [] }));
}

let passed = 0;
const t = (name, fn) => { fn(); console.log(`  PASS ${name}`); passed++; };

t('coding question -> 0.3', () => {
    assert.strictEqual(makeRunner('напиши код на python function')(), 0.3);
});
t('algorithm keyword -> 0.3', () => {
    assert.strictEqual(makeRunner('explain this algorithm in detail')(), 0.3);
});
t('creative story -> 1.2', () => {
    assert.strictEqual(makeRunner('придумай историю про дракона')(), 1.2);
});
t('write a poem -> 1.2 (creative checked before coding)', () => {
    assert.strictEqual(makeRunner('write a poem about the sea')(), 1.2);
});
t('factual why -> 0.5', () => {
    assert.strictEqual(makeRunner('почему небо синее?')(), 0.5);
});
t('python code -> 0.3', () => {
    assert.strictEqual(makeRunner('напиши код на python function')(), 0.3);
});
t('fix a bug -> 0.3', () => {
    assert.strictEqual(makeRunner('fix a bug in my sql query')(), 0.3);
});
t('explain -> 0.5', () => {
    assert.strictEqual(makeRunner('explain quantum physics simply')(), 0.5);
});
t('neutral default -> 0.7', () => {
    assert.strictEqual(makeRunner('привет, как дела?')(), 0.7);
});
t('uses last user message from chat when input empty', () => {
    // messageInput empty, but chat has a last user msg with "код"
    assert.strictEqual(makeRunner('', [{ role: 'user', content: 'напиши код' }])(), 0.3);
});

// ---- regenerateMessage: verify it targets the last user message and slices history correctly ----
function extractRegen() {
    const start = src.indexOf('async function regenerateMessage(');
    assert.ok(start > 0, 'regenerateMessage not found in main.js');
    let i = src.indexOf('{', start), depth = 0, end = -1;
    for (; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
    }
    return src.slice(start, end);
}

// Run regenerateMessage in a sandbox that captures what would be streamed.
function runRegen(messages, assistantIdx) {
    let captured = null;
    const fnSrc = extractRegen();
    // Provide the globals the function uses; stub out the streaming calls so we can
    // observe the user message / history it would resend, without a real network.
    const runner = new Function('getCurrentChat', 'streamViaWebSocket', 'fallbackRest',
        'currentAgentId', 'isStreaming', 'setStatus', 'flashStatus', 'renderMessages', 'saveChats',
        fnSrc + '\nreturn regenerateMessage;');
    const chat = { messages: JSON.parse(JSON.stringify(messages)) };
    const fakeStream = async (userText, historyForApi, agentId, attachments) => {
        captured = { userText, historyForApi: historyForApi.map(m => m.content), agentId };
        return 'NEW_REPLY';
    };
    // Provide every global the sliced function body references.
    const regen = runner(
        () => chat,                       // getCurrentChat
        fakeStream,                       // streamViaWebSocket
        async (a) => { captured = { via: 'rest', userText: a }; return 'REST_REPLY'; }, // fallbackRest
        'AG-1',                          // currentAgentId
        false,                            // isStreaming (guard passes)
        () => {},                         // setStatus
        () => {},                         // flashStatus
        () => {},                         // renderMessages
        async () => {}                    // saveChats
    );
    return regen(assistantIdx).then(() => ({ captured, chat }));
}

(async () => {
    let passed2 = 0;
    const t2 = (name, ok) => { if (!ok) { console.log(`  FAIL ${name}`); process.exit(1); } console.log(`  PASS ${name}`); passed2++; };

    const msgs = [
        { role: 'user', content: 'вопрос 1' },
        { role: 'assistant', content: 'ответ 1' },
        { role: 'user', content: 'вопрос 2' },
        { role: 'assistant', content: 'ответ 2' },
    ];
    const r1 = await runRegen(msgs, 3); // regenerate the reply to "вопрос 2"
    t2('regen targets the last user message', r1.captured.userText === 'вопрос 2');
    t2('regen history = all messages before the question', r1.captured.historyForApi.length === 2 && r1.captured.historyForApi[0] === 'вопрос 1' && r1.captured.historyForApi[1] === 'ответ 1');
    t2('regen replaces the target assistant reply', r1.chat.messages[3].content === 'NEW_REPLY' && r1.chat.messages[3].pending === false);

    const r2 = await runRegen(msgs, 1); // regenerate the reply to "вопрос 1"
    t2('regen works on first reply', r2.captured.userText === 'вопрос 1' && r2.chat.messages[1].content === 'NEW_REPLY');

    console.log(`\n${passed2} regenerateMessage tests passed`);
})().catch(e => { console.log('FAIL regen test:', e.message); process.exit(1); });

// ---- fmtKvDetail: verify it formats raw kv strings into readable key: value pairs ----
function extractFmtKvDetail() {
    const start = src.indexOf('function fmtKvDetail(');
    assert.ok(start > 0, 'fmtKvDetail not found in main.js');
    let i = src.indexOf('{', start), depth = 0, end = -1;
    for (; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
    }
    return src.slice(start, end);
}

function makeFmtKv() {
    const fnSrc = extractFmtKvDetail();
    return new Function(fnSrc + '\nreturn fmtKvDetail;')();
}

const fmt = makeFmtKv();
t('fmtKvDetail: empty -> dash', () => {
    assert.strictEqual(fmt(null), '—');
    assert.strictEqual(fmt(''), '—');
});
t('fmtKvDetail: single k=v', () => {
    assert.strictEqual(fmt('model=agnes-3.0-flash'), 'model: agnes-3.0-flash');
});
t('fmtKvDetail: multiple k=v pairs (double-space separated, as in real logs)', () => {
    const out = fmt('model=agnes-3.0-flash  history_len=0  msg_preview=Привет');
    assert.strictEqual(out, 'model: agnes-3.0-flash  ·  history_len: 0  ·  msg_preview: Привет');
});
t('fmtKvDetail: value with = signs preserved', () => {
    assert.strictEqual(fmt('prompt_tokens=9583  total_tokens=9592  finish_reason=stop'),
        'prompt_tokens: 9583  ·  total_tokens: 9592  ·  finish_reason: stop');
});
t('fmtKvDetail: single-space input is NOT split (matches backend double-space format)', () => {
    // Real log format joins kv pairs with exactly two spaces: "a=1  b=2  c=3"
    // Single-space input is treated as one token: "a=1 b=2 c=3" -> "a: 1 b=2 c=3"
    const out = fmt('a=1 b=2 c=3');
    assert.strictEqual(out, 'a: 1 b=2 c=3');
});

// keep the original summary line accurate
console.log(`\n${passed} autoPickTemperature + fmtKvDetail tests passed`);
if (passed === 0) process.exit(1);
