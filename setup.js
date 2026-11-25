#!/usr/bin/env node
/**
 * AMT Chat — unified setup script (Python + Node).
 *
 * Usage: node setup.js
 *
 * What it does:
 *   1. Checks Node.js version (18+)
 *   2. Checks Python 3.12+ (py launcher / PATH / per-user install)
 *   3. Runs python setup.py  → creates backend/.venv + installs requirements
 *   4. Runs npm install       → installs Electron + electron-builder
 *   5. Prints next steps (build:py, build:win)
 *
 * Idempotent: safe to re-run. Skips steps that already succeeded.
 */
'use strict';

const { execSync, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = path.resolve(__dirname);

// ---------- helpers ----------
function log(msg) {
  console.log(msg);
}

function step(label) {
  console.log(`\n==> ${label}`);
}

function fail(msg) {
  console.error(`\n[ОШИБКА] ${msg}`);
  process.exit(1);
}

function run(cmd, args = [], opts = {}) {
  const r = spawnSync(cmd, args, {
    cwd: opts.cwd || ROOT,
    stdio: "inherit",
    shell: process.platform === "win32",
    env: { ...process.env, ...(opts.env || {}) },
  });
  if (r.error && r.error.code !== "ENOENT") {
    throw r.error;
  }
  return r.status === 0;
}

/**
 * Find a Python 3.12+ interpreter.
 * Tries: py -3 launcher, python on PATH, per-user install location.
 * @returns {string|null} command to run python (e.g. "py -3" or path to python.exe)
 */
function findPython() {
  const candidates = [];

  // 1) py launcher (Windows)
  if (process.platform === "win32") {
    candidates.push(["py", "-3"]);
    candidates.push(["python", "-3"]);
  }
  // 2) python on PATH
  candidates.push(["python"]);
  candidates.push(["python3"]);

  for (const cmd of candidates) {
    try {
      const r = spawnSync(cmd[0], [...cmd.slice(1), "-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"], {
        cwd: ROOT,
        encoding: "utf8",
        shell: process.platform === "win32",
      });
      if (r.status === 0) {
        const ver = (r.stdout || "").trim();
        const parts = ver.split(".");
        if (parts.length >= 2) {
          const major = parseInt(parts[0], 10);
          const minor = parseInt(parts[1], 10);
          if (major === 3 && minor >= 12) {
            return cmd.join(" ");
          }
        }
      }
    } catch {
      // candidate not found
    }
  }

  // 3) Per-user install location (Windows, after winget without PATH refresh)
  if (process.platform === "win32" && process.env.LOCALAPPDATA) {
    const localPy = path.join(process.env.LOCALAPPDATA, "Programs", "Python", "Python312", "python.exe");
    if (fs.existsSync(localPy)) {
      try {
        const r = spawnSync(localPy, ["-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"], {
          cwd: ROOT,
          encoding: "utf8",
        });
        if (r.status === 0) {
          const ver = (r.stdout || "").trim();
          const parts = ver.split(".");
          if (parts.length >= 2 && parseInt(parts[0]) === 3 && parseInt(parts[1]) >= 12) {
            return localPy;
          }
        }
      } catch {
        // ignore
      }
    }
  }

  return null;
}

/**
 * Check Node.js version.
 * @returns {boolean}
 */
function checkNode() {
  const nodeVer = process.versions.node;
  const major = parseInt(nodeVer.split(".")[0], 10);
  log(`Node.js ${nodeVer}`);
  if (major < 18) {
    fail("Node.js 18+ required. Install from https://nodejs.org");
  }
  return true;
}

/**
 * Find and verify Python 3.12+.
 * @returns {string} python command
 */
function checkPython() {
  const py = findPython();
  if (!py) {
    fail(
      "Python 3.12+ not found. Install from https://www.python.org/downloads/ " +
        "(or on Windows: winget install Python.Python.3.12) and re-run."
    );
  }
  log(`Python found: ${py}`);
  return py;
}

function main() {
  log("AMT Chat — setup\n");

  // Step 1: Node.js
  step("1/3 — Node.js check");
  checkNode();

  // Step 2: Python + venv
  step("2/3 — Python 3.12+ + venv");
  const py = checkPython();

  const setupPy = path.join(ROOT, "setup.py");
  if (!fs.existsSync(setupPy)) {
    fail(`setup.py not found at ${setupPy}`);
  }

  // Run: python setup.py  (creates backend/.venv, installs requirements)
  // Parse the command: could be "py -3" (2 args) or a full path (1 arg)
  const pyParts = py.split(" ");
  const ok = run(pyParts[0], [...pyParts.slice(1), setupPy]);
  if (!ok) {
    fail("python setup.py failed. Check that Python 3.12+ is installed and re-run.");
  }
  log("✓ Python venv + requirements installed");

  // Step 3: npm install
  step("3/3 — npm install (Electron + electron-builder)");
  const okNpm = run("npm", ["install"]);
  if (!okNpm) {
    fail("npm install failed. Check network / npm registry and re-run.");
  }
  log("✓ Node dependencies installed");

  // Done
  console.log(`
─────────────────────────────────────────────────────────────
AMT Chat setup complete

What was done:
  • Python venv:   backend/.venv  (requirements.txt installed)
  • Node modules:  node_modules/  (Electron + electron-builder)

Next steps:
  dev:   npm start                     (runs electron . — dev mode)
  build: npm run build:py             (PyInstaller → dist/amt-backend/)
        npm run build:win             (electron-builder → release/ NSIS)
        node scripts/build.js all    (both, one command)

Or run the full pipeline:
        powershell scripts\\bootstrap_and_build.ps1
─────────────────────────────────────────────────────────────`);
}

main();
