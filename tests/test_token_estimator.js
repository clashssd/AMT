// Tests for token-estimator.js
'use strict';
const assert = require('assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'token-estimator.js'), 'utf8');
// The file defines plain functions; eval to expose them
(0, eval)(src);
const { estimateTokens, estimateTokensForMessages } = globalThis;

let passed = 0;
const t = (name, fn) => { fn(); console.log(`  PASS ${name}`); passed++; };

t('empty string -> 0', () => assert.strictEqual(estimateTokens(''), 0));
t('null/undefined -> 0', () => {
    assert.strictEqual(estimateTokens(null), 0);
    assert.strictEqual(estimateTokens(undefined), 0);
});
t('latin english approx 4 chars/token', () => {
    // 80 latin chars ~= 20 tokens
    const tok = estimateTokens('a'.repeat(80));
    assert.ok(tok >= 15 && tok <= 25, `got ${tok}`);
});
t('cyrillic fewer tokens per char', () => {
    const cyr = estimateTokens('м'.repeat(80));
    const lat = estimateTokens('a'.repeat(80));
    assert.ok(cyr > lat, `cyrillic ${cyr} should be > latin ${lat}`);
});
t('mixed + punctuation counted as other', () => {
    const tok = estimateTokens('hi 123 !@#');
    assert.ok(tok > 0);
});
t('monotonic: longer text -> more tokens', () => {
    assert.ok(estimateTokens('x'.repeat(400)) >= estimateTokens('x'.repeat(100)));
});
t('estimateTokensForMessages sums', () => {
    const msgs = [
        { role: 'user', content: 'hello' },
        { role: 'assistant', content: 'привет' },
    ];
    const sum = estimateTokensForMessages(msgs);
    assert.ok(sum >= estimateTokens('hello') + estimateTokens('привет') - 1);
});
t('estimateTokensForMessages empty -> 0', () => {
    assert.strictEqual(estimateTokensForMessages([]), 0);
});

console.log(`\n${passed} token-estimator tests passed`);
if (passed === 0) process.exit(1);
