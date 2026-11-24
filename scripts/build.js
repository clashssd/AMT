#!/usr/bin/env node
/**
 * scripts/build.js — собирает полный дистрибутив AMT Chat.
 *
 * 1. PyInstaller: backend -> dist/amt-backend/ (sidecar-бандл)
 * 2. electron-builder: NSIS-инсталлятор -> release/
 *
 * Запуск: node scripts/build.js [py|win|all]
 *   py   — только PyInstaller
 *   win  — только electron-builder
 *   all  — оба (дефолт)
 */
'use strict';

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.join(__dirname, '..');

function run(cmd, args, opts = {}) {
  console.log(`\n$ ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, {
    cwd: ROOT,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...opts,
  });
  if (r.status !== 0) {
    console.error(`Command failed (exit ${r.status}): ${cmd} ${args.join(' ')}`);
    process.exit(r.status || 1);
  }
}

function buildPy() {
  // PyInstaller через venv python. Каноническая локация — backend/.venv (создаёт setup.py);
  // для обратной совместимости пробуем и корневой venv/.
  const candidates = process.platform === 'win32'
    ? [
        path.join(ROOT, 'backend', '.venv', 'Scripts', 'python.exe'),
        path.join(ROOT, 'venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.join(ROOT, 'backend', '.venv', 'bin', 'python'),
        path.join(ROOT, 'venv', 'bin', 'python'),
      ];
  const py = candidates.find(p => fs.existsSync(p));
  if (!py) {
    console.error('venv python not found. Looked for:', candidates.join(', '));
    console.error('Create it: python setup.py   (создаёт backend/.venv и ставит requirements + pyinstaller)');
    process.exit(1);
  }
  run(py, ['-m', 'PyInstaller', path.join('backend', 'amt-backend.spec'), '--noconfirm', '--clean']);
  console.log('PyInstaller build OK -> dist/amt-backend/');
}

function buildWin() {
  run('npm', ['run', 'build:win']);
  console.log('electron-builder OK -> release/');
}

const target = process.argv[2] || 'all';
if (target === 'py' || target === 'all') buildPy();
if (target === 'win' || target === 'all') buildWin();
console.log('\nBuild complete.');
