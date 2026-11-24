// ===== Безопасность: локальный ключ в Web Crypto (AES-GCM) =====
// API Key и чаты не хранятся в открытом виде в localStorage.
// Корень шифрования выводится из случайного 256-битного ключа,
// который тоже хранится в localStorage. Это защищает данные от
// простого копирования из DevTools, но не от доступа к браузеру
// тем же пользователем (для этого нужен password — можно добавить позже).
//
// Если Web Crypto недоступен (не secure context, например http без
// localhost) — данные сохраняются как JSON с пометкой "insecure".
const CRYPTO_SALT_KEY = 'amt_crypto_salt';
const CRYPTO_KEY_MATERIAL_KEY = 'amt_crypto_key';
const CRYPTO_AVAILABLE = typeof crypto !== 'undefined'
    && typeof crypto.subtle !== 'undefined'
    && typeof crypto.getRandomValues === 'function';

async function getOrCreateKeyMaterial() {
    let material = null;
    try {
        const saved = localStorage.getItem(CRYPTO_KEY_MATERIAL_KEY);
        if (saved) material = Uint8Array.from(JSON.parse(saved));
    } catch (e) { /* ignore */ }

    if (!material) {
        material = crypto.getRandomValues(new Uint8Array(32));
        localStorage.setItem(CRYPTO_KEY_MATERIAL_KEY, JSON.stringify(Array.from(material)));
    }

    // HKDF: выводим AES-GCM 256 ключ из материла
    const baseKey = await crypto.subtle.importKey('raw', material, 'HKDF', false, ['deriveKey']);
    const salt = new Uint8Array(16);
    return crypto.subtle.deriveKey(
        { name: 'HKDF', hash: 'SHA-256', salt: salt, info: new TextEncoder().encode('amt-chat-v1') },
        baseKey,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
    );
}

function toBase64(bytes) {
    let bin = '';
    bytes.forEach(b => bin += String.fromCharCode(b));
    return btoa(bin);
}

function fromBase64(str) {
    const bin = atob(str);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes;
}

async function encryptData(data) {
    if (!CRYPTO_AVAILABLE) {
        return 'insecure:' + btoa(unescape(encodeURIComponent(JSON.stringify(data))));
    }
    const key = await getOrCreateKeyMaterial();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(JSON.stringify(data));
    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, key, encoded);
    return toBase64(iv) + ':' + toBase64(new Uint8Array(ciphertext));
}

async function decryptData(payload) {
    if (payload.startsWith('insecure:')) {
        return JSON.parse(decodeURIComponent(escape(atob(payload.slice(9)))));
    }
    if (!CRYPTO_AVAILABLE) throw new Error('crypto unavailable');
    const key = await getOrCreateKeyMaterial();
    const [ivB64, dataB64] = payload.split(':');
    const iv = fromBase64(ivB64);
    const ciphertext = fromBase64(dataB64);
    const decoded = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: iv }, key, ciphertext);
    return JSON.parse(new TextDecoder().decode(decoded));
}

// ===== Публичные функции хранения =====
const SecureStore = {
    async get(key, fallback = null) {
        try {
            const raw = localStorage.getItem(key);
            if (!raw) return fallback;
            return await decryptData(raw);
        } catch (e) {
            return fallback;
        }
    },
    async set(key, value) {
        localStorage.setItem(key, await encryptData(value));
    },
    async remove(key) {
        localStorage.removeItem(key);
    }
};
