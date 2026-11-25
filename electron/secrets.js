/**
 * electron/secrets.js — safeStorage-backed secret store for AMT Chat.
 *
 * API keys are encrypted with Electron's safeStorage (DPAPI on Windows)
 * and persisted to userData/secrets.bin. The renderer never sees
 * decrypted values — it only gets provider names via `secrets:status`.
 *
 * At startup the main process reads secrets.bin and injects keys into
 * the sidecar via POST /internal/secrets (token-protected, 127.0.0.1 only).
 */
'use strict';

const { app, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

let _token = '';

function getToken() {
  return _token;
}

function setToken(t) {
  _token = t;
}

function secretsFile() {
  return path.join(app.getPath('userData'), 'secrets.bin');
}

/**
 * Read all secrets from disk. Returns a plain object (decrypted).
 * On any error (missing file, bad JSON, decrypt failure) returns {}.
 */
function readSecrets() {
  try {
    const raw = fs.readFileSync(secretsFile(), 'utf8');
    const obj = JSON.parse(raw);
    const out = {};
    const { safeStorage } = require('electron');
    for (const [provider, enc] of Object.entries(obj)) {
      try {
        out[provider] = safeStorage.decryptString(Buffer.from(enc, 'base64'));
      } catch {
        // skip undecryptable entry
      }
    }
    return out;
  } catch {
    return {};
  }
}

/**
 * Write all secrets to disk (encrypted). Creates parent dir if needed.
 */
function writeSecrets(obj) {
  const file = secretsFile();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const { safeStorage } = require('electron');
  const out = {};
  for (const [provider, plain] of Object.entries(obj)) {
    out[provider] = safeStorage.encryptString(plain).toString('base64');
  }
  fs.writeFileSync(file, JSON.stringify(out, null, 2));
}

/**
 * Push a single secret to the running sidecar via /internal/secrets.
 * Returns true on success, false on failure.
 */
async function pushSecretToSidecar(port, provider, key) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/internal/secrets`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Token': _token,
      },
      body: JSON.stringify({ provider, key }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Remove a single secret from the running sidecar via DELETE /internal/secrets.
 */
async function clearSecretFromSidecar(port, provider) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/internal/secrets`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Token': _token,
      },
      body: JSON.stringify({ provider }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Inject all secrets into the sidecar (called once after sidecar starts).
 */
async function injectAllSecrets(port) {
  const secrets = readSecrets();
  for (const [provider, key] of Object.entries(secrets)) {
    await pushSecretToSidecar(port, provider, key);
  }
}

/**
 * Register the three secrets:* IPC handlers.
 * @param {object} getPort - () => number, returns the current sidecar port
 */
function registerSecretsIpc(getPort) {
  ipcMain.handle('secrets:set', async (_event, { provider, key }) => {
    if (!provider || typeof provider !== 'string') {
      return { ok: false, error: 'provider required' };
    }
    const secrets = readSecrets();
    secrets[provider] = key || '';
    if (!key) {
      // empty key = clear
      delete secrets[provider];
    }
    writeSecrets(secrets);
    if (key) {
      await pushSecretToSidecar(getPort(), provider, key);
    } else {
      await clearSecretFromSidecar(getPort(), provider);
    }
    return { ok: true };
  });

  ipcMain.handle('secrets:clear', async (_event, { provider }) => {
    if (!provider || typeof provider !== 'string') {
      return { ok: false, error: 'provider required' };
    }
    const secrets = readSecrets();
    delete secrets[provider];
    writeSecrets(secrets);
    await clearSecretFromSidecar(getPort(), provider);
    return { ok: true };
  });

  ipcMain.handle('secrets:status', async () => {
    const secrets = readSecrets();
    return { providers: Object.keys(secrets) };
  });
}

module.exports = {
  getToken,
  setToken,
  readSecrets,
  writeSecrets,
  pushSecretToSidecar,
  clearSecretFromSidecar,
  injectAllSecrets,
  registerSecretsIpc,
  secretsFile,
};
