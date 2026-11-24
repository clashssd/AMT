/**
 * electron/sidecar.js — spawns the Python FastAPI backend as a child process.
 *
 * In dev mode it uses the project venv; in packaged mode it would use a
 * PyInstaller-built binary (future work).
 */
'use strict';

const { spawn } = require('child_process');
const path = require('path');
const net = require('net');
const fs = require('fs');

let child = null;
let healthTimer = null;

/**
 * Resolve the Python executable path.
 * Dev: use the project venv.
 * Packaged: use the bundled binary (TODO: PyInstaller).
 * @returns {string}
 */
function getPythonPath() {
  if (process.env.AMT_PYTHON) return process.env.AMT_PYTHON;
  const pyName = process.platform === 'win32' ? 'python.exe' : 'python';
  // Canonical location: setup.py creates backend/.venv.
  const venvPy = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', pyName);
  if (fs.existsSync(venvPy)) return venvPy;
  // Legacy fallback: older layouts kept the venv at project root venv/.
  const legacyPy = path.join(__dirname, '..', 'venv', 'Scripts', pyName);
  if (fs.existsSync(legacyPy)) return legacyPy;
  return 'python';
}

/**
 * Build the [command, args] that starts the backend.
 * Production: PyInstaller one-dir binary at dist/backend/amt-backend.
 * Dev: venv python + uvicorn module.
 * @param {number} port
 * @returns {[string, string[]]}
 */
function getSidecarCommand(port) {
  const exeName = process.platform === 'win32' ? 'amt-backend.exe' : 'amt-backend';
  // PyInstaller one-dir output lands in dist/amt-backend/ (dev, project root).
  // In a packaged app, electron-builder ships it under resources/amt-backend/.
  let binDir;
  if (process.env.AMT_SIDECAR_DIR) {
    binDir = process.env.AMT_SIDECAR_DIR;
  } else if (process.resourcesPath) {
    // Packaged: electron-builder ships dist/amt-backend/** under resources/
    binDir = path.join(process.resourcesPath, 'amt-backend');
  } else {
    // Dev: project-root dist/amt-backend (see amt-backend.spec output)
    binDir = path.join(__dirname, '..', 'dist', 'amt-backend');
  }
  const binExe = path.join(binDir, exeName);
  if (fs.existsSync(binExe)) {
    return [binExe, []];
  }
  // dev fallback: python -m uvicorn backend.main:app
  const py = getPythonPath();
  return [py, [
    '-m', 'uvicorn', 'backend.main:app',
    '--host', '127.0.0.1', '--port', String(port), '--log-level', 'warning',
  ]];
}

/**
 * Start the Python sidecar.
 * @param {number} port - Port for FastAPI (default 8000)
 * @returns {Promise<void>} Resolves when /health returns 200
 */
function startSidecar(port = 8000) {
  return new Promise((resolve, reject) => {
    if (child) {
      // already running
      if (child.exitCode === null) return resolve();
      child = null;
    }

    const [cmd, args] = getSidecarCommand(port);
    const dbg = path.join(process.env.APPDATA || '.', 'AMT Chat', 'debug.log');
    try { fs.appendFileSync(dbg, `[sidecar] cmd: ${cmd} args: ${JSON.stringify(args)}\n`); } catch {}
    try { fs.appendFileSync(dbg, `[sidecar] APPDATA: ${process.env.APPDATA} HOME: ${process.env.HOME}\n`); } catch {}
    // For a bundled PyInstaller binary, set cwd to its own directory so that
    // _internal/ and any relative paths resolve correctly.
    const isBundledBin = cmd.endsWith('.exe') || cmd.endsWith('amt-backend');
    const cwd = isBundledBin ? path.dirname(cmd) : path.join(__dirname, '..');
    // In packaged mode, redirect writable dirs to the user's app-data location
    // so the PyInstaller binary doesn't try to write inside its own bundle.
    const appDataDir = isBundledBin
      ? path.join(process.env.APPDATA || path.join(process.env.HOME || '.', 'AMT'), 'AMT Chat')
      : null;
    const spawnEnv = { ...process.env, PORT: String(port) };
    if (appDataDir) {
      spawnEnv.AMT_LOG_DIR = path.join(appDataDir, 'logs');
      spawnEnv.AMT_CHATS_DIR = path.join(appDataDir, 'chats');
      try {
        fs.mkdirSync(path.join(appDataDir, 'logs'), { recursive: true });
        fs.mkdirSync(path.join(appDataDir, 'chats'), { recursive: true });
      } catch { /* non-fatal */ }
    }

    child = spawn(cmd, args, {
      cwd,
      env: spawnEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let stderr = '';
    child.stdout.on('data', d => process.stdout.write('[backend] ' + d));
    child.stderr.on('data', d => {
      const s = d.toString();
      stderr += s;
      process.stderr.write('[backend] ' + s);
    });

    child.on('error', err => {
      try { fs.appendFileSync(dbg, `[sidecar] ERROR: ${err.message} stderr: ${stderr.slice(0,500)}\n`); } catch {}
      reject(new Error('Failed to start sidecar: ' + err.message + ' (stderr: ' + stderr.slice(0, 500) + ')'));
    });

    child.on('exit', (code, signal) => {
      try { fs.appendFileSync(dbg, `[sidecar] EXIT code=${code} signal=${signal}\n`); } catch {}
      child = null;
      if (healthTimer) { clearInterval(healthTimer); healthTimer = null; }
      if (code !== 0 && code !== null && !process.appQuitting) {
        process.stderr.write(`[sidecar] backend exited code=${code} signal=${signal}\n`);
      }
    });

    // Poll /health until ready (max 15s)
    let attempts = 0;
    healthTimer = setInterval(() => {
      attempts++;
      healthCheck(port).then(ok => {
        if (ok) {
          if (healthTimer) { clearInterval(healthTimer); healthTimer = null; }
          resolve();
        } else if (attempts >= 30) {
          if (healthTimer) { clearInterval(healthTimer); healthTimer = null; }
          reject(new Error('Backend did not become healthy within 15s'));
        }
      });
    }, 500);
  });
}

/**
 * TCP-connect to port to check if the backend is listening.
 * @param {number} port
 * @returns {Promise<boolean>}
 */
function healthCheck(port) {
  return new Promise(resolve => {
    const sock = net.connect(port, '127.0.0.1');
    sock.on('connect', () => { sock.destroy(); resolve(true); });
    sock.on('error', () => { sock.destroy(); resolve(false); });
    sock.setTimeout(1000, () => { sock.destroy(); resolve(false); });
  });
}

/**
 * Stop the sidecar process.
 */
function stopSidecar() {
  if (child) {
    const c = child;
    child = null;
    c.kill('SIGTERM');
    // Give it 3s, then force
    setTimeout(() => { try { c.kill('SIGKILL'); } catch {} }, 3000);
  }
}

module.exports = { startSidecar, stopSidecar, healthCheck, getPythonPath, getSidecarCommand };
