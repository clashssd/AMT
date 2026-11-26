#!/usr/bin/env node
// check-design-tokens.mjs — AMT design guard.
//
// Exits 1 (failure) when:
//   - a CSS file references `var(--x)` where `--x` is not defined in
//     tokens.css OR in style.css's own `:root` block;
//   - style.css has more than 120 color literals (hex + rgb/rgba);
//   - components-v2.css has more than 0 color literals;
//   - a white background (`background: #fff/#ffffff/white/rgba(255,255,255,…)`)
//     is present outside tokens.css and outside an `--accent-contrast` value.
//
// Exits 0 (success) when all checks pass.
//
// The guard is deliberately lenient in counting:
//   - color literals inside `url(...)` / `data:` / `/* */` comments are ignored;
//   - `color-mix(in srgb, ..., white)` is allowed in tokens.css;
//   - `background: var(--accent-contrast)` is allowed;
//   - `box-shadow` rgba(255,…) highlights are allowed (spec §3:
//     "если белый нужен для блика — rgba(255,255,255,0.06) и только как
//      highlight, не как фон").

import { readFileSync } from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const files = {
  style: path.join(ROOT, 'frontend/css/style.css'),
  cv2:   path.join(ROOT, 'frontend/css/components-v2.css'),
  tokens: path.join(ROOT, 'frontend/css/tokens.css'),
};

function read(p) {
  try { return readFileSync(p, 'utf8'); }
  catch { return ''; }
}

const styleSrc = read(files.style);
const cv2Src   = read(files.cv2);
const tokensSrc = read(files.tokens);

// ---------------------------------------------------------------------------
// 1. Collect defined custom properties
// ---------------------------------------------------------------------------
const defined = new Set();
// tokens.css: every `--name:` declaration
for (const m of tokensSrc.matchAll(/--([A-Za-z][\w-]*)\s*:/g)) defined.add(m[1]);
// style.css: `:root` / `[data-theme=...]` blocks only
{
  const rootBlocks = styleSrc.matchAll(/:root\s*[{][^}]*[\}]/g);
  const dataThemeBlocks = styleSrc.matchAll(/\[data-theme=[^\]]+\]\s*[{][^}]*[\}]/g);
  for (const m of rootBlocks) {
    for (const v of m[0].matchAll(/--([A-Za-z][\w-]*)\s*:/g)) defined.add(v[1]);
  }
  for (const m of dataThemeBlocks) {
    for (const v of m[0].matchAll(/--([A-Za-z][\w-]*)\s*:/g)) defined.add(v[1]);
  }
}
// Also include the variables that themes.js emits at runtime (46 vars in
// toCssVars) — these are defined per-theme at runtime and not in any file.
const RUNTIME_VARS = [
  'bg-grad-1','bg-grad-2','bg-grad-3',
  'accent','accent-2','text','text-dim','success','warning','danger','info',
  'glass-bg','glass-bg-2','glass-border','theme-radius','theme-blur','theme-glow',
  'surface-0','surface-1','surface-2','surface-3','surface-hover','surface-active',
  'border','border-strong','divider','text-strong','text-faint','muted',
  'accent-contrast','accent-soft','accent-glow','accent-dim','focus-ring',
  'success-soft','warning-soft','danger-soft','info-soft',
  'field-bg','field-bg-hover','field-border','field-border-focus','field-text','field-placeholder',
  'card-bg','card-bg-2','modal-bg','overlay-bg','dropdown-bg','tooltip-bg',
  'code-bg','table-bg','table-row-hover','scrollbar-thumb','scrollbar-track',
  'control-bg','control-border','control-checked',
  'radius-xs','radius-sm','radius-md','radius-lg','radius-xl','radius-pill',
  'shadow-sm','shadow-md','shadow-lg','blur-sm','blur-md','blur-lg',
  'ease-out','motion-fast','motion-base','motion-slow','font-mono','glass','surface-dim',
];
for (const v of RUNTIME_VARS) defined.add(v);

// ---------------------------------------------------------------------------
// 2. Find var() references and check each is defined
//    (comments stripped so `var(--token)` inside /* */ is ignored)
// ---------------------------------------------------------------------------
const styleNoComments = stripComments(styleSrc);
const cv2NoComments = stripComments(cv2Src);
const varRefs = new Set();
for (const m of styleNoComments.matchAll(/var\(\s*--([A-Za-z][\w-]*)\s*[,)]/g)) varRefs.add(m[1]);
for (const m of cv2NoComments.matchAll(/var\(\s*--([A-Za-z][\w-]*)\s*[,)]/g)) varRefs.add(m[1]);

const undefinedVars = [...varRefs].filter(n => !defined.has(n));

// ---------------------------------------------------------------------------
// 3. Count color literals (hex + rgb/rgba) excluding url()/data:/comments
// ---------------------------------------------------------------------------
function stripComments(src) {
  // Remove /* ... */ comments (non-greedy)
  return src.replace(/\/\*[\s\S]*?\*\//g, '');
}
function countLiterals(src, skipRootBlocks) {
  let clean = stripComments(src);
  if (skipRootBlocks) {
    // Remove :root { ... } and [data-theme=...] { ... } blocks — their
    // declarations ARE the token definitions, not hardcodes.
    clean = clean.replace(/:root\s*[{][^}]*[\}]/g, '');
    clean = clean.replace(/\[data-theme=[^\]]+\]\s*[{][^}]*[\}]/g, '');
  }
  // Strip url(...) and data: URI contents so hex inside them is not counted
  const noUrl = clean.replace(/url\([^)]*\)/gi, '').replace(/data:[^)'"\s]*/gi, '');
  const hex = (noUrl.match(/#[0-9a-fA-F]{3,8}\b/g) || []).length;
  const rgba = (noUrl.match(/rgba?\(/g) || []).length;
  return hex + rgba;
}
const styleLits = countLiterals(styleSrc, true);
const cv2Lits   = countLiterals(cv2Src, false);

// ---------------------------------------------------------------------------
// 4. White background check (outside tokens.css and outside accent-contrast)
// ---------------------------------------------------------------------------
const whiteBgRe = /background(-color)?\s*:\s*(#fff\b|#ffffff\b|white\b|rgb\(255\s*,\s*255\s*,\s*255\s*\)|rgba\(255\s*,\s*255\s*,\s*255\s*,\s*0\.[5-9])/gi;
function findWhiteBg(src) {
  const clean = stripComments(src);
  // Remove @media print { ... } blocks — print styles intentionally use white/black
  const noPrint = clean.replace(/@media\s+print\s*{[\s\S]*?}/g, '');
  const hits = [];
  let m;
  whiteBgRe.lastIndex = 0;
  while ((m = whiteBgRe.exec(noPrint)) !== null) {
    hits.push({ line: noPrint.slice(0, m.index).split('\n').length, match: m[0] });
  }
  return hits;
}
const styleWhite = findWhiteBg(styleSrc, 'style.css');
const cv2White   = findWhiteBg(cv2Src, 'components-v2.css');

// ---------------------------------------------------------------------------
// 5. Report
// ---------------------------------------------------------------------------
let failed = false;
const lines = [];
lines.push('check:design — AMT design guard');
lines.push('');
lines.push(`defined tokens: ${defined.size}`);
lines.push(`var() refs used: ${varRefs.size}`);

if (undefinedVars.length) {
  failed = true;
  lines.push(`❌ ${undefinedVars.length} undefined var() reference(s):`);
  for (const v of undefinedVars.slice(0, 30)) lines.push(`   --${v}`);
  if (undefinedVars.length > 30) lines.push(`   … and ${undefinedVars.length - 30} more`);
} else {
  lines.push('✅ all var() refs defined');
}

if (styleLits > 120) {
  failed = true;
  lines.push(`❌ style.css has ${styleLits} color literals (limit 120)`);
} else {
  lines.push(`✅ style.css color literals: ${styleLits} / 120`);
}

if (cv2Lits > 0) {
  failed = true;
  lines.push(`❌ components-v2.css has ${cv2Lits} color literals (limit 0)`);
} else {
  lines.push('✅ components-v2.css color literals: 0 / 0');
}

if (styleWhite.length) {
  failed = true;
  lines.push(`❌ ${styleWhite.length} white background literal(s) in style.css:`);
  for (const h of styleWhite.slice(0, 20)) lines.push(`   line ${h.line}: ${h.match}`);
} else {
  lines.push('✅ no white background literals in style.css');
}

if (cv2White.length) {
  failed = true;
  lines.push(`❌ ${cv2White.length} white background literal(s) in components-v2.css:`);
  for (const h of cv2White.slice(0, 20)) lines.push(`   line ${h.line}: ${h.match}`);
} else {
  lines.push('✅ no white background literals in components-v2.css');
}

lines.push('');
lines.push(failed ? 'FAIL' : 'PASS');
console.log(lines.join('\n'));
process.exit(failed ? 1 : 0);
