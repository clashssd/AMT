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
 *
 * ВАЖНО (почему этот скрипт не просто `npm run build:win`):
 *
 * На машинах, где путь к профилю пользователя содержит не-Latin-символы
 * (кириллица, напр. C:\Users\юляещека), electron-builder скачивает NSIS
 * (makensis.exe) в кэш под этим же путём, а затем НЕЛЬЗЯ запустить сам
 * makensis.exe через Node child_process: Windows возвращает `spawn UNKNOWN`,
 * сборка падает на шаге NSIS. Это воспроизводится на 100% при кирилличном
 * кэше, независимо от версии Node.
 *
 * Исправление: если обнаружен не-Latin путь (HOME / APPDATA / LOCALAPPDATA /
 * TEMP / кэш electron-builder), мы переопределяем ELECTRON_BUILDER_CACHE в
 * чистый ASCII-каталог (C:\amt-builder-cache\... или ProgramData), так что
 * makensis.exe извлекается и запускается по ASCII-пути — и сборка проходит.
 *
 * Дополнительно скрипт:
 *   - автоматически делает 1 retry при `spawn UNKNOWN` (антивирус мог
 *     заблокировать только что извлечённый makensis.exe);
 *   - в конце печатает инструкцию по SmartScreen («не удалось проверить
 *     издателя») — инсталлятор не подписан, это ожидаемо без code-signing
 *     сертификата.
 */
'use strict';

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.join(__dirname, '..');

/**
 * @typedef {Object} BuildEnv
 * @property {Record<string,string>} env   — дополненный env для subprocess
 * @property {string} reason               — человекочитаемое, ПОЧЕМУ env менялся
 * @property {boolean} asciiCache         — был ли принудительно переключён кэш
 */

/**
 * Обнаруживает, содержит ли строка хотя бы один символ вне ASCII-7bit.
 * Это ядро диагностики кириллического пути.
 *
 * @param {string} s
 * @returns {boolean}
 */
function hasNonAscii(s) {
  if (!s) return false;
  for (let i = 0; i < s.length; i++) {
    if (s.charCodeAt(i) > 0x7f) return true;
  }
  return false;
}

/**
 * Выбирает ASCII-безопасную локацию для кэша electron-builder.
 *
 * Порядок:
 *   1. C:\amt-builder-cache\<user>\ — если C: существует (стандарт Windows)
 *   2. %ProgramData%\amt-builder-cache\<user>\
 *   3. ASCII-падение в temp (напр. C:\Temp)
 *
 * Возвращает null, если текущий кэш уже ASCII-безопасен (тогда менять ничего
 * не надо).
 *
 * @param {{userHome?:string, localAppData?:string, temp?:string}} ctx
 * @returns {string|null}
 */
function pickAsciiCacheDir(ctx = {}) {
  // Короткий ASCII-токен пользователя: берём только имя (USER/USERNAME),
  // а не весь home-путь — чтобы каталог читался (C:\amt-builder-cache\bob).
  let user = (process.env.USER || process.env.USERNAME || ctx.userHome || 'user');
  user = user.replace(/[^\w.-]/g, '_').slice(0, 32) || 'user';
  // Если весь токен — только underscores (например, кириллическое имя),
  // не получаем "________" — падаем на фиксированный безопасный токен.
  if (/^[_]+$/.test(user)) user = 'user';
  const candidates = [];
  if (process.platform === 'win32') {
    candidates.push(`C:\\amt-builder-cache\\${user}`);
    if (process.env.ProgramData) candidates.push(path.join(process.env.ProgramData, 'amt-builder-cache', user));
  } else {
    candidates.push(`/opt/amt-builder-cache/${user}`);
    if (process.env.HOME) candidates.push(`${process.env.HOME}/.amt-builder-cache`);
  }
  // Любая candidate — уже ASCII по построению, но проверим на всякий случай
  // (например, ProgramData сам мог оказаться в не-ASCII).
  for (const c of candidates) {
    if (!hasNonAscii(c)) return c;
  }
  return null;
}

/**
 * Решает, нужно ли переопределять ELECTRON_BUILDER_CACHE, и почему.
 *
 * @returns {BuildEnv}
 */
function resolveBuildEnv() {
  const home = process.env.HOME || process.env.USERPROFILE || '';
  const local = process.env.LOCALAPPDATA || '';
  const appdata = process.env.APPDATA || '';
  const temp = process.env.TEMP || process.env.TMP || '';

  const sources = {
    'HOME': home,
    'LOCALAPPDATA': local,
    'APPDATA': appdata,
    'TEMP': temp,
  };
  const offending = Object.entries(sources).filter(([, v]) => hasNonAscii(v));

  if (offending.length === 0) {
    // Все пути ASCII — кэш менять не нужно.
    return { env: {}, reason: 'все пути ASCII — ELECTRON_BUILDER_CACHE не трогаем', asciiCache: false };
  }

  const target = pickAsciiCacheDir({ userHome: home });
  if (!target) {
    // Не нашли ASCII-каталог — вернём причину, но не меняем env (let it fail
    // с понятным сообщением, не с тихим fallback в тот же кириллический кэш).
    const names = offending.map(([k]) => k).join(', ');
    return {
      env: {},
      reason: `не-ASCII пути: ${names}. Не удалось подобрать ASCII-каталог кэша — сборка может упасть с spawn UNKNOWN.`,
      asciiCache: false,
    };
  }

  const reason = `переопределяю ELECTRON_BUILDER_CACHE=${target}, потому что не-ASCII пути: ${offending.map(([k, v]) => `${k}=${v}`).join(', ')}`;
  return { env: { ELECTRON_BUILDER_CACHE: target }, reason, asciiCache: true };
}

/**
 * Проверяет, существует ли и запускается ли makensis.exe в заданном кэше.
 * Используется для pre-warm диагностики.
 *
 * @param {string} cacheDir
 * @returns {string|null} — путь к makensis.exe или null
 */
function findMakensis(cacheDir) {
  if (!cacheDir) return null;
  const rel = process.platform === 'win32' ? path.join('nsis', 'nsis-3.0.4.1', 'Bin', 'makensis.exe')
    : process.platform === 'darwin' ? 'nsis/macos/nsis-3.0.4.1/mac/makensis'
    : 'nsis/linux/nsis-3.0.4.1/linux/makensis';
  const p = path.join(cacheDir, rel);
  return fs.existsSync(p) ? p : null;
}

function run(cmd, args, opts = {}) {
  console.log(`\n$ ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, {
    cwd: ROOT,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...opts,
  });
  return r;
}

function runOrThrow(cmd, args, opts = {}) {
  const r = run(cmd, args, opts);
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
  runOrThrow(py, ['-m', 'PyInstaller', path.join('backend', 'amt-backend.spec'), '--noconfirm', '--clean']);
  console.log('PyInstaller build OK -> dist/amt-backend/');
}

/**
 * Запускает electron-builder, при `spawn UNKNOWN` (антивирус / блокировка)
 * делает 1 retry. Возвращает true, если сборка успешна.
 */
function buildWin(envOverride) {
  const spawnOpts = envOverride ? { env: { ...process.env, ...envOverride } } : {};
  let attempt = 0;
  for (;;) {
    attempt++;
    const r = run('npm', ['run', 'build:win'], spawnOpts);
    if (r.status === 0) return true;

    const stdoutStr = r.stdout && r.stdout.toString ? r.stdout.toString() : '';
    const stderrStr = r.stderr && r.stderr.toString ? r.stderr.toString() : '';
    const out = stdoutStr + '\n' + stderrStr;
    const isSpawnUnknown = isSpawnUnknownOutput(out);

    if (isSpawnUnknown && attempt === 1) {
      console.warn('\n[build.js] spawn UNKNOWN (антивирус мог заблокировать только что скачанный makensis.exe). Жду 2 сек. и повторяю…');
      run(process.platform === 'win32' ? 'cmd' : 'sh',
        process.platform === 'win32' ? ['/c', 'timeout', '/t', '2', '/nobreak'] : ['-c', 'sleep 2']);
      continue;
    }
    if (isSpawnUnknown) {
      console.error('\n[build.js] spawn UNKNOWN повторился даже после retry.');
      console.error('Скорее всего, антивирус/SmartScreen заблокировал makensis.exe, либо путь к кэшу не-ASCII.');
      console.error('Попробуйте:');
      console.error('  1) временно отключить антивирус и перезапустить:  node scripts/build.js win');
      if (envOverride) {
        console.error('  2) переопределить кэш в ASCII-путь вручную:');
        console.error(`       ${Object.entries(envOverride).map(([k, v]) => `${k}=${v}`).join(' ')}`);
        console.error(`       node scripts/build.js win`);
      }
      console.error('  3) см. docs/BUILD.md — раздел "spawn UNKNOWN" / "SmartScreen".');
    }
    return false;
  }
}

/**
 * Обнаруживает `spawn UNKNOWN` в выводе electron-builder / npm.
 * Это чистая функция — вынесена для тестовости (в build.js она определяет,
 * делать ли retry).
 *
 * @param {string} output — stdout+stderr собранной команды
 * @returns {boolean}
 */
function isSpawnUnknownOutput(output) {
  if (!output) return false;
  // electron-builder (через cross-spawn) пишет "spawn UNKNOWN" в stderr.
  // Показываемый в логах стек: "Error: spawn UNKNOWN" + "failedTask=build".
  return /spawn UNKNOWN/i.test(output) || /failedTask=build.*spawn/i.test(output);
}

function printSmartScreenNote() {
  console.log('\n─────────────────────────────────────────────────────────────');
  console.log('SmartScreen: "не удалось проверить издателя" — это НОРМА');
  console.log('─────────────────────────────────────────────────────────────');
  console.log('AMT Chat не подписан code-signing сертификатом (для этого нужен платный сертификат от DigiCert/GlobalSign и CI-секрет).');
  console.log('Windows SmartScreen поэтому показывает предупреждение при первом запуске инсталлятора.');
  console.log('Как обойти (безопасно):');
  console.log('  • В окне SmartScreen нажмите «Подробнее» → «Выполнить в любом случае» (кнопка появится в развёрнутом списке);');
  console.log('  • Либо запустите портативную копию: release\\win-unpacked\\AMT Chat.exe — она не запускается через NSIS, SmartScreen её не блокирует.');
  console.log('Для корпоративного развёртывания: подпишите AMT Chat Setup.exe сертификатом организации (см. docs/BUILD.md §Signing).');
  console.log('─────────────────────────────────────────────────────────────\n');
}

const target = process.argv[2] || 'all';

// Guard: только когда запускается напрямую (node scripts/build.js), а не как
// require() из тестов. Без этого `require('./build.js')` в тестах бы начал
// собирать дистрибутив.
if (require.main === module) {
  if (target === 'py') {
    buildPy();
    console.log('\nBuild complete.');
  } else {
    // win или all: сначала (при all) PyInstaller, затем electron-builder.
    if (target === 'all') buildPy();

    const { env, reason, asciiCache } = resolveBuildEnv();
    if (asciiCache) {
      console.log(`\n[build.js] ${reason}`);
      fs.mkdirSync(env.ELECTRON_BUILDER_CACHE, { recursive: true });
    } else if (reason) {
      console.log(`[build.js] ${reason}`);
    }

    if (!buildWin(asciiCache ? env : undefined)) process.exit(1);
    console.log('electron-builder OK -> release/');
    printSmartScreenNote();
    console.log('\nBuild complete.');
  }
}

// Export for tests (не влияет на CLI-режим благодаря require.main guard выше)
module.exports = { hasNonAscii, pickAsciiCacheDir, resolveBuildEnv, findMakensis, isSpawnUnknownOutput };
