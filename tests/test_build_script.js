// Tests for scripts/build.js — логика обхода `spawn UNKNOWN` (не-ASCII путь
// кэша electron-builder) и переключения ELECTRON_BUILDER_CACHE в ASCII-каталог.
//
// build.js экспортирует чистые функции через module.exports, но CLI-часть
// заходит под guard `require.main === module`, поэтому require() его из теста
// без side-effects.
'use strict';
const assert = require('assert');
const path = require('node:path');

// Сохраняем реальный env перед тестами, чтобы не ломать другие тесты.
const saved = {};
const ENV_KEYS = ['HOME', 'USER', 'USERNAME', 'LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP', 'ELECTRON_BUILDER_CACHE'];
for (const k of ENV_KEYS) saved[k] = process.env[k];

function setEnv(obj) {
  for (const k of ENV_KEYS) {
    if (k in obj) process.env[k] = obj[k];
    else delete process.env[k];
  }
}
function restoreEnv() {
  for (const k of ENV_KEYS) {
    if (saved[k] !== undefined) process.env[k] = saved[k];
    else delete process.env[k];
  }
}

// require'им build.js — CLI не запустится (guard), получаем только API.
// Путь к скрипту относительный от каталога tests/.
const ROOT = path.join(__dirname, '..');
const build = require(path.join(ROOT, 'scripts', 'build.js'));

let passed = 0;
const t = (name, fn) => {
  try { fn(); console.log(`  PASS ${name}`); passed++; }
  catch (e) { console.log(`  FAIL ${name}: ${e.message}`); process.exit(1); }
};

// ---- hasNonAscii ----
t('hasNonAscii: чистый ASCII -> false', () => {
  assert.strictEqual(build.hasNonAscii('C:/Users/bob/Desktop/AMT'), false);
});
t('hasNonAscii: кириллица в пути -> true', () => {
  assert.strictEqual(build.hasNonAscii('C:\\Users\\юляещека\\Desktop\\AMT'), true);
});
t('hasNonAscii: пустая строка -> false', () => {
  assert.strictEqual(build.hasNonAscii(''), false);
});
t('hasNonAscii: undefined/null -> false (без краша)', () => {
  assert.strictEqual(build.hasNonAscii(undefined), false);
  assert.strictEqual(build.hasNonAscii(null), false);
});
t('hasNonAscii: только ASCII > 0x7f ловится', () => {
  // 'é' (U+00E9) — не ASCII
  assert.strictEqual(build.hasNonAscii('/home/josé'), true);
});

// ---- resolveBuildEnv: кириллический HOME -> переопределение кэша ----
t('cyrillic HOME -> asciiCache=true, ELECTRON_BUILDER_CACHE установлен', () => {
  setEnv({ HOME: 'C:/Users/юляещека', USER: 'юляещека' });
  const r = build.resolveBuildEnv();
  assert.strictEqual(r.asciiCache, true);
  assert.ok(r.env.ELECTRON_BUILDER_CACHE, 'ELECTRON_BUILDER_CACHE должен быть задан');
  // ASCII-каталог не должен содержать кириллицу
  assert.strictEqual(build.hasNonAscii(r.env.ELECTRON_BUILDER_CACHE), false);
});

// ---- resolveBuildEnv: все пути ASCII ----
// На Windows теперь ВСЕГДА переопределяем кэш в ASCII (безвредно + предсказуемо).
// На unix — не трогаем. Тест платформенно-зависимый.
t('clean ASCII env: win32 -> asciiCache=true (всегда ASCII-кэш); unix -> false', () => {
  setEnv({ HOME: 'C:/Users/bob', USER: 'bob', LOCALAPPDATA: 'C:/Users/bob/AppData/Local', APPDATA: 'C:/Users/bob/AppData/Roaming', TEMP: 'C:/Users/bob/AppData/Local/Temp' });
  const r = build.resolveBuildEnv();
  if (process.platform === 'win32') {
    assert.strictEqual(r.asciiCache, true, 'на Windows всегда ASCII-кэш');
    assert.ok(r.env.ELECTRON_BUILDER_CACHE);
    assert.strictEqual(build.hasNonAscii(r.env.ELECTRON_BUILDER_CACHE), false);
  } else {
    assert.strictEqual(r.asciiCache, false, 'на unix без не-ASCII — не трогаем');
  }
});

// ---- resolveBuildEnv: кириллический LOCALAPPDATA (типично на Windows) ----
t('cyrillic LOCALAPPDATA -> asciiCache=true', () => {
  setEnv({ HOME: 'C:/Users/юляещека', USER: 'юляещека', LOCALAPPDATA: 'C:/Users/юляещека/AppData/Local', APPDATA: 'C:/Users/юляещека/AppData/Roaming', TEMP: 'C:/Users/юляещека/AppData/Local/Temp' });
  const r = build.resolveBuildEnv();
  assert.strictEqual(r.asciiCache, true);
  assert.strictEqual(build.hasNonAscii(r.env.ELECTRON_BUILDER_CACHE), false);
  // reason должен упомянуть offending источники
  assert.ok(/LOCALAPPDATA|HOME|TEMP|APPDATA/.test(r.reason), 'reason должен назвать offending переменные');
});

// ---- pickAsciiCacheDir: кириллический USER -> не "________", а 'user' ----
t('pickAsciiCacheDir: кириллическое имя -> безопасный токен (не все underscores)', () => {
  process.env.USER = 'юляещека';
  const dir = build.pickAsciiCacheDir({ userHome: 'C:/Users/юляещека' });
  assert.ok(dir, 'должен вернуть каталог');
  // Не должно быть каталога, в имени которого только underscores
  assert.ok(!/^[_\\\/]+$/.test(path.basename(dir)), `basename "${path.basename(dir)}" не должен быть только underscores`);
  delete process.env.USER;
});

// ---- findMakensis ----
t('findMakensis: несуществующий кэш -> null', () => {
  assert.strictEqual(build.findMakensis('C:/no-such-dir-xyz'), null);
});
t('findMakensis: пустой/undefined кэш -> null', () => {
  assert.strictEqual(build.findMakensis(''), null);
  assert.strictEqual(build.findMakensis(undefined), null);
});

// ---- module guard: require не запустил CLI ----
t('require(build.js) не выполняет build (require.main guard)', () => {
  // Если guard сломан, require() начал бы PyInstaller/electron-builder и
  // этот тест не дошёл бы сюда (или завис). Сам факт, что мы здесь и все
  // выше проверки прошли, подтверждает отсутствие side-effects.
  assert.strictEqual(typeof build.hasNonAscii, 'function');
});

// ---- isSpawnUnknownOutput: распознавание ошибки из лога electron-builder ----
// Это ровно та ошибка, что в фото пользователя:
//   "x spawn UNKNOWN  failedTask=build  stackTrace=Error: spawn UNKNOWN
//     at ChildProcess.spawn ..."
t('isSpawnUnknownOutput: стек из фото пользователя -> true', () => {
  const out = [
    'x spawn UNKNOWN  failedTask=build stackTrace=Error: spawn UNKNOWN',
    '    at ChildProcess.spawn (node:internal/child_process:860:9)',
    '    at execFile (C:\\...\\node_modules\\builder-util\\src\\util.ts:99:13)',
  ].join('\n');
  assert.strictEqual(build.isSpawnUnknownOutput(out), true);
});
t('isSpawnUnknownOutput: "Error: spawn UNKNOWN" (без failedTask) -> true', () => {
  assert.strictEqual(build.isSpawnUnknownOutput('Error: spawn UNKNOWN'), true);
});
t('isSpawnUnknownOutput: успешный вывод build -> false', () => {
  assert.strictEqual(build.isSpawnUnknownOutput('electron-builder OK -> release/'), false);
});
t('isSpawnUnknownOutput: пустая/undefined -> false (без краша)', () => {
  assert.strictEqual(build.isSpawnUnknownOutput(''), false);
  assert.strictEqual(build.isSpawnUnknownOutput(undefined), false);
});
t('isSpawnUnknownOutput: другой error (ENOENT) -> false', () => {
  assert.strictEqual(build.isSpawnUnknownOutput('Error: ENOENT no such file'), false);
});

// ---- find7za / extract7z / findNsisArchive: 7z- распаковка как fallback ----
// (app-builder.exe ищет `7za` в PATH; на машине юляещеки её нет, есть только
//  `7z.exe` в C:\Program Files\7-Zip — ищется через стандартную локацию.)
t('find7za: возвращает путь к 7z-бинарнику (7z.exe в Program Files) или null', () => {
  const seven = build.find7za();
  // На машине без 7-Zip — null; с 7-Zip — путь к 7z.exe/7za.
  // Не утверждаем строгое значение, проверяем, что тип строки или null.
  assert.ok(seven === null || typeof seven === 'string');
  if (seven !== null) {
    assert.ok(require('fs').existsSync(seven), `найденный ${seven} должен существовать`);
  }
});
t('find7za: win32, 7z.exe в Program Files -> найден', () => {
  // Фиксированная проверка: если 7z.exe есть в стандартной локации — он вернётся.
  const seven = build.find7za();
  if (process.platform === 'win32') {
    const expected = [
      `${process.env['PROGRAMFILES']}\\7-Zip\\7z.exe`,
      `${process.env['PROGRAMFILES(X86)']}\\7-Zip\\7z.exe`,
    ];
    for (const p of expected) {
      if (require('fs').existsSync(p)) {
        assert.strictEqual(seven, p, 'должен вернуть первый найденный путь');
        return;
      }
    }
  }
  // Если ни одной стандартной локации нет — вернём null (PATH тоже проверен).
});
t('findNsisArchive: несуществующий кэш -> null', () => {
  assert.strictEqual(build.findNsisArchive('C:/no-such-dir-xyz'), null);
});
t('findNsisArchive: пустой/undefined кэш -> null', () => {
  assert.strictEqual(build.findNsisArchive(''), null);
  assert.strictEqual(build.findNsisArchive(undefined), null);
});
t('extract7z: несуществующий архив -> false (без краша)', () => {
  const ok = build.extract7z('C:/no-such-archive.7z', 'C:/no-such-out');
  assert.strictEqual(ok, false);
});

restoreEnv();
console.log(`\n${passed} build.js (spawn-UNKNOWN/ascii-cache/7z-fallback) tests passed`);
if (passed === 0) process.exit(1);
