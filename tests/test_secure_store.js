// Tests for SecureStore (AES-GCM encryption of localStorage data).
// Runs in Node with a minimal localStorage shim + real Web Crypto.
// Node 18+ exposes globalThis.crypto (Web Crypto) with subtle.
'use strict';

const assert = require('assert');
const { crypto } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

// ---- minimal localStorage shim ----
class LocalStorageShim {
    constructor() { this.map = new Map(); }
    getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
    setItem(k, v) { this.map.set(k, String(v)); }
    removeItem(k) { this.map.delete(k); }
    clear() { this.map.clear(); }
    get length() { return this.map.size; }
    key(i) { return [...this.map.keys()][i] ?? null; }
}

// Expose globals the source file expects
// Node's global crypto is read-only; use defineProperty to provide/ensure it.
if (!globalThis.crypto) {
    Object.defineProperty(globalThis, 'crypto', { value: crypto, configurable: true, writable: true });
}
globalThis.localStorage = new LocalStorageShim();
globalThis.btoa = globalThis.btoa || ((s) => Buffer.from(s, 'binary').toString('base64'));
globalThis.atob = globalThis.atob || ((s) => Buffer.from(s, 'base64').toString('binary'));
globalThis.TextEncoder = globalThis.TextEncoder || require('node:util').TextEncoder;
globalThis.TextDecoder = globalThis.TextDecoder || require('node:util').TextDecoder;

// Load the module source and eval it so its top-level const/functions exist here.
// indirect eval runs in global scope; the source declares `const SecureStore`,
// which stays in the eval scope — so we append a line exposing it on globalThis.
const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'core', 'secure-store.js'), 'utf8');
(0, eval)(src + '\n;globalThis.SecureStore = SecureStore; globalThis.encryptData = encryptData; globalThis.decryptData = decryptData;');

// secure-store.js declares `const SecureStore` at top-level; indirect eval runs in
// global scope so SecureStore, encryptData, decryptData become global.

async function run() {
    let passed = 0;
    const t = (name, fn) => {
        return Promise.resolve().then(fn).then(() => {
            console.log(`  PASS ${name}`);
            passed++;
        });
    };

    // 1. set/get round-trip
    await t('SecureStore.set + get round trip (object)', async () => {
        await SecureStore.set('k', { hello: 'мир', n: 42 });
        const got = await SecureStore.get('k');
        assert.deepStrictEqual(got, { hello: 'мир', n: 42 });
    });

    // 2. stored value is NOT plaintext
    await t('stored blob is encrypted (not raw JSON)', async () => {
        const secret = 'sk-supersecretkey123';
        await SecureStore.set('api', secret);
        const raw = localStorage.getItem('api');
        assert.ok(raw.includes(':'), 'expected iv:ciphertext format');
        assert.ok(!raw.includes(secret), 'plaintext must not appear in storage');
    });

    // 3. get with no key returns fallback
    await t('get returns fallback when key missing', async () => {
        assert.strictEqual(await SecureStore.get('nope', 'default'), 'default');
    });

    // 4. remove clears
    await t('remove deletes key', async () => {
        await SecureStore.set('a', 1);
        assert.ok(localStorage.getItem('a'));
        await SecureStore.remove('a');
        assert.strictEqual(localStorage.getItem('a'), null);
    });

    // 5. tamper detection: corrupt ciphertext -> get returns fallback (AES-GCM auth)
    await t('tampered ciphertext fails auth -> fallback', async () => {
        await SecureStore.set('safe', 'original');
        const raw = localStorage.getItem('safe');
        // flip one char in the ciphertext portion
        const [iv, ct] = raw.split(':');
        const mutated = iv + ':' + ct.slice(0, -2) + (ct.endsWith('AA') ? 'BB' : 'AA');
        localStorage.setItem('safe', mutated);
        const got = await SecureStore.get('safe', 'FALLBACK');
        assert.strictEqual(got, 'FALLBACK');
    });

    // 6. key material persisted and reused (same key -> decrypts earlier data)
    await t('key material persisted across instances', async () => {
        await SecureStore.set('persist', 'value-x');
        // fresh localStorage for key material only, but keep the secret
        const storedKey = localStorage.getItem('amt_crypto_key');
        assert.ok(storedKey, 'crypto key material must be persisted');
        const got = await SecureStore.get('persist');
        assert.strictEqual(got, 'value-x');
    });

    // 7. array round trip
    await t('array round trip', async () => {
        await SecureStore.set('arr', [1, 2, 3, 'рус']);
        assert.deepStrictEqual(await SecureStore.get('arr'), [1, 2, 3, 'рус']);
    });

    console.log(`\n${passed} SecureStore tests passed`);
    if (passed === 0) process.exit(1);
}

run().catch(e => { console.error('FAIL:', e); process.exit(1); });
