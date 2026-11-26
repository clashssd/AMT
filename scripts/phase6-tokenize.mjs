#!/usr/bin/env node
// One-off Phase-6 tokenization pass over frontend/css/style.css.
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const p = path.join(process.cwd(), 'frontend', 'css', 'style.css');
let src = readFileSync(p, 'utf8');
let changes = 0;
function subAll(re, fn) {
  const before = src;
  src = src.replace(re, fn);
  if (src !== before) changes++;
}

// --- 1. hex colors (property-agnostic) ---
const hexMap = {
  '#fff': 'var(--accent-contrast)',
  '#ffffff': 'var(--accent-contrast)',
  '#f8f8fc': 'var(--accent-contrast)',
  '#e0e0f0': 'var(--text)',
  '#e8e8f4': 'var(--text)',
  '#e8e8f0': 'var(--text)',
  '#d0d0e8': 'var(--text)',
  '#eaeaf6': 'var(--text)',
  '#c5c5d8': 'var(--text)',
  '#c5c5dd': 'var(--text)',
  '#d0d0d0': 'var(--text)',
  '#c8c8d0': 'var(--text-dim)',
  '#a0a0b5': 'var(--text-dim)',
  '#9a9aa8': 'var(--text-dim)',
  '#8a8a9a': 'var(--text-dim)',
  '#8a8aa0': 'var(--text-dim)',
  '#8a8aa8': 'var(--text-dim)',
  '#666': 'var(--text-faint)',
  '#888': 'var(--text-faint)',
  '#8888a0': 'var(--text-faint)',
  '#7a7a90': 'var(--text-faint)',
  '#6a6a78': 'var(--text-faint)',
  '#6a6a85': 'var(--text-faint)',
  '#9a9ab8': 'var(--text-faint)',
  '#8b86c9': 'var(--accent)',
  '#aba5c9': 'var(--accent-2)',
  '#c4b5fd': 'var(--accent-2)',
  '#b49af8': 'var(--accent-2)',
  '#d8d4ec': 'var(--accent-2)',
  '#7aa2ff': 'var(--info)',
  '#60a5fa': 'var(--info)',
  '#8ab4ff': 'var(--info)',
  '#7c5cff': 'var(--accent)',
  '#4ade80': 'var(--success)',
  '#facc15': 'var(--warning)',
  '#f87171': 'var(--danger)',
  '#fca5a5': 'var(--danger)',
  '#ff6b6b': 'var(--danger)',
  '#8899bb': 'var(--info)',
};
for (const [k, v] of Object.entries(hexMap)) {
  subAll(new RegExp(k + '(?![0-9a-fA-F])', 'gi'), () => v);
}

// --- 2. black / white keywords (as color values only) ---
subAll(/(^|[\s:(,;])black(?![\w-])/g, (m, g) => g + 'var(--accent-contrast)');
subAll(/(^|[\s:(,;])white(?![\w-])/g, (m, g) => g + 'var(--accent-contrast)');

// --- 3. rgb/rgba calls: tokenize by channel signature ---
// Order matters: most specific first.
const rgbaRules = [
  // white-ish -> glass-bg
  [/rgba?\(\s*255\s*,\s*255\s*,\s*255\s*[,/]\s*[^)]*\)/gi, 'var(--glass-bg)'],
  // black shadow -> shadow-md
  [/rgba?\(\s*0\s*,\s*0\s*,\s*0\s*[,/]\s*[^)]*\)/gi, 'var(--shadow-md)'],
  // accent #8b86c9 = 139,134,201
  [/rgba?\(\s*139\s*,\s*134\s*,\s*201\s*[,/]\s*[^)]*\)/gi, 'var(--accent-soft)'],
  // #aba5c9 = 171,165,201
  [/rgba?\(\s*171\s*,\s*165\s*,\s*201\s*[,/]\s*[^)]*\)/gi, 'var(--accent-soft)'],
  // #aba5c9 = 171,171,197
  [/rgba?\(\s*171\s*,\s*171\s*,\s*197\s*[,/]\s*[^)]*\)/gi, 'var(--accent-soft)'],
  // #bebade = 190,186,215
  [/rgba?\(\s*190\s*,\s*186\s*,\s*215\s*[,/]\s*[^)]*\)/gi, 'var(--accent-soft)'],
  // #c8c4e6 = 200,196,230
  [/rgba?\(\s*200\s*,\s*196\s*,\s*230\s*[,/]\s*[^)]*\)/gi, 'var(--accent-soft)'],
  // dark overlays (18,18,28 / 10,10,18 / 12,10,24 / 16,16,31) -> shadow-md
  [/rgba?\(\s*18\s*,\s*18\s*,\s*28\s*[,/]\s*[^)]*\)/gi, 'var(--shadow-md)'],
  [/rgba?\(\s*10\s*,\s*10\s*,\s*18\s*[,/]\s*[^)]*\)/gi, 'var(--shadow-md)'],
  [/rgba?\(\s*12\s*,\s*10\s*,\s*24\s*[,/]\s*[^)]*\)/gi, 'var(--shadow-md)'],
  [/rgba?\(\s*16\s*,\s*16\s*,\s*31\s*[,/]\s*[^)]*\)/gi, 'var(--shadow-md)'],
  // blue-ish (100,100,180) -> info-soft
  [/rgba?\(\s*100\s*,\s*100\s*,\s*180\s*[,/]\s*[^)]*\)/gi, 'var(--info-soft)'],
  // danger #f87171 = 248,113,113
  [/rgba?\(\s*248\s*,\s*113\s*,\s*113\s*[,/]\s*[^)]*\)/gi, 'var(--danger-soft)'],
  // success #4ade80 = 74,222,128
  [/rgba?\(\s*74\s*,\s*222\s*,\s*128\s*[,/]\s*[^)]*\)/gi, 'var(--success-soft)'],
  // warning #facc15 = 250,204,21
  [/rgba?\(\s*250\s*,\s*204\s*,\s*21\s*[,/]\s*[^)]*\)/gi, 'var(--warning-soft)'],
  // info #8ab4ff = 138,180,255
  [/rgba?\(\s*138\s*,\s*180\s*,\s*255\s*[,/]\s*[^)]*\)/gi, 'var(--info-soft)'],
  // generic white-ish (any rgba with r>=240 g>=240 b>=240) -> glass-bg
  [/rgba?\(\s*(2[4-9]\d|300)\s*,\s*(2[4-9]\d|300)\s*,\s*(2[4-9]\d|300)\s*[,/]\s*[^)]*\)/gi, 'var(--glass-bg)'],
];
for (const [re, rep] of rgbaRules) subAll(re, rep);

// --- 4. extended hex map (theme-specific accents, darks, etc.) ---
const hexMap2 = {
  '#ababc5': 'var(--text)',
  '#b0b0c8': 'var(--text-dim)',
  '#a7a7c5': 'var(--text)',
  '#b8b8ce': 'var(--text-dim)',
  '#c0c0d8': 'var(--text-dim)',
  '#d0d0e0': 'var(--text)',
  '#c9c9dd': 'var(--text)',
  '#d8d8e8': 'var(--text)',
  '#d4d4e8': 'var(--text)',
  '#e0e0ee': 'var(--text)',
  '#f0f0f8': 'var(--accent-contrast)',
  '#e9e9f5': 'var(--text)',
  '#c0c0d0': 'var(--text-dim)',
  '#c2c7cf': 'var(--text-dim)',
  '#a8a8c0': 'var(--text-dim)',
  '#9a9ab0': 'var(--text-dim)',
  '#a0a0b8': 'var(--text-dim)',
  '#a0a8c0': 'var(--text-dim)',
  '#9090a5': 'var(--text-dim)',
  '#9eab33': 'var(--success)',
  '#5a5a68': 'var(--text-faint)',
  '#5a5a7a': 'var(--text-faint)',
  '#5a5a6e': 'var(--text-faint)',
  '#6a6a8a': 'var(--text-faint)',
  '#6a6a82': 'var(--text-faint)',
  '#636d79': 'var(--text-faint)',
  '#555': 'var(--text-faint)',
  '#464c55': 'var(--text-faint)',
  '#302f33': 'var(--text-faint)',
  // dark backgrounds / overlays
  '#14141c': 'var(--bg-grad-2)',
  '#141214': 'var(--bg-grad-2)',
  '#05050a': 'var(--bg-grad-1)',
  '#0c0c0c': 'var(--bg-grad-1)',
  '#16161f': 'var(--bg-grad-2)',
  '#11131a': 'var(--bg-grad-2)',
  '#12100a': 'var(--bg-grad-1)',
  '#0b0f14': 'var(--bg-grad-1)',
  '#0e0a1a': 'var(--bg-grad-1)',
  '#1a1a24': 'var(--bg-grad-3)',
  '#1a1630': 'var(--bg-grad-3)',
  '#180a04': 'var(--bg-grad-1)',
  '#150408': 'var(--bg-grad-1)',
  '#2b0000': 'var(--bg-grad-1)',
  '#071410': 'var(--bg-grad-1)',
  '#04141a': 'var(--bg-grad-1)',
  '#0a1620': 'var(--bg-grad-1)',
  '#12232d': 'var(--bg-grad-2)',
  '#1e3a2d': 'var(--bg-grad-2)',
  '#2a0810': 'var(--bg-grad-2)',
  '#0c0a18': 'var(--bg-grad-3)',
  '#310b3d': 'var(--bg-grad-3)',
  '#1d1d1d': 'var(--bg-grad-3)',
  '#2f1211': 'var(--bg-grad-2)',
  // accent variants (theme-specific)
  '#7c5cfd': 'var(--accent)',
  '#6a4ce0': 'var(--accent)',
  '#c084fc': 'var(--accent-2)',
  '#b8b3dd': 'var(--accent-2)',
  '#b0a8d8': 'var(--accent-2)',
  '#e8d4f0': 'var(--accent-2)',
  '#f0d8dd': 'var(--accent-2)',
  '#6fe0a8': 'var(--success)',
  '#7ee2a8': 'var(--success)',
  '#2a8339': 'var(--success)',
  '#5aa07a': 'var(--success)',
  '#7fb399': 'var(--success)',
  '#5c7a6a': 'var(--success)',
  '#d4e6dc': 'var(--success)',
  '#d4eef0': 'var(--info)',
  '#ccd6f0': 'var(--info)',
  '#9bc2ff': 'var(--info)',
  '#6ea8ff': 'var(--info)',
  '#4b7bff': 'var(--info)',
  '#3b82f6': 'var(--info)',
  '#c0d4ff': 'var(--info)',
  '#e8eef8': 'var(--info)',
  '#73cbf5': 'var(--info)',
  '#8ccdd9': 'var(--info)',
  '#4a6a75': 'var(--info)',
  '#5f7d84': 'var(--info)',
  '#1f3a44': 'var(--info)',
  // warning variants
  '#f4c448': 'var(--warning)',
  '#d8b192': 'var(--warning)',
  '#efe4d4': 'var(--warning)',
  '#d8c98a': 'var(--warning)',
  '#9eab33': 'var(--warning)',
  // danger variants
  '#d83627': 'var(--danger)',
  '#c42b1c': 'var(--danger)',
  '#ef4949': 'var(--danger)',
  '#ff8a8a': 'var(--danger)',
  '#f08a9a': 'var(--danger)',
  '#e04f74': 'var(--danger)',
  '#e88ebc': 'var(--danger)',
  '#6f0a44': 'var(--danger)',
  '#f0d4cd': 'var(--danger)',
  '#d08a9a': 'var(--danger)',
  '#8a4a55': 'var(--danger)',
  '#fca5a5': 'var(--danger)',
  '#fecaca': 'var(--danger)',
  '#e3a7a7': 'var(--danger)',
  '#8a5a4a': 'var(--danger)',
  '#cfa9a9': 'var(--danger)',
  // misc
  '#7878a0': 'var(--text-faint)',
  '#6a3a7a': 'var(--accent)',
};
for (const [k, v] of Object.entries(hexMap2)) {
  subAll(new RegExp(k + '(?![0-9a-fA-F])', 'gi'), () => v);
}

// --- 5. catch remaining color-ish rgba (any color channel, not in url/data) ---
// Run in a second pass after the hex map so `src` is up-to-date.
src = src.replace(
  /rgba?\(([^)]*)\)/g,
  (full, args, offset) => {
    const head = src.slice(Math.max(0, offset - 120), offset);
    if (/url\(/.test(head) || /data:/.test(head)) return full;
    const a = args.split(/[,/]\s*/).map(s => s.trim()).filter(Boolean);
    const n = a[0] | 0;
    if (n === 255 && a.length === 4) return 'var(--glass-bg)';
    if (n === 0) return 'var(--shadow-md)';
    return full; // leave as-is
  }
);

// --- 6. second catch-all pass for rgba (now that hex map ran) ---
src = src.replace(
  /rgba?\(([^)]*)\)/g,
  (full, args, offset) => {
    const head = src.slice(Math.max(0, offset - 120), offset);
    if (/url\(/.test(head) || /data:/.test(head)) return full;
    const a = args.split(/[,/]\s*/).map(s => s.trim()).filter(Boolean);
    const n = a[0] | 0;
    if (n === 255 && a.length === 4) return 'var(--glass-bg)';
    if (n === 0) return 'var(--shadow-md)';
    return full; // leave as-is
  }
);

writeFileSync(p, src);
const hexLeft = (src.match(/#[0-9a-fA-F]{3,8}\b/g) || []).length;
const rgbaLeft = (src.match(/rgba?\(/g) || []).length;
console.log(`changes: ${changes}`);
console.log(`remaining hex: ${hexLeft}`);
console.log(`remaining rgba: ${rgbaLeft}`);
console.log(`total color literals: ${hexLeft + rgbaLeft}`);
