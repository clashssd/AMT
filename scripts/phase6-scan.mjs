import { readFileSync } from 'node:fs';
import path from 'node:path';

const p = path.join(process.cwd(), 'frontend/css/style.css');
const s = readFileSync(p, 'utf8');
const c = s.replace(/\/\*[\s\S]*?\*\//g, '');
const noUrl = c.replace(/url\([^)]*\)/gi, '').replace(/data:[^)'"\s]*/gi, '');

const hex = noUrl.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
const rgba = noUrl.match(/rgba?\(/g) || [];
console.log('hex:', hex.length, 'rgba:', rgba.length, 'total:', hex.length + rgba.length);

// Show the top remaining hex colors
const map = {};
for (const h of hex) {
  const k = h.toLowerCase();
  map[k] = (map[k] || 0) + 1;
}
const sorted = Object.entries(map).sort((a, b) => b[1] - a[1]);
console.log('\nTop remaining hex:');
for (const [k, v] of sorted.slice(0, 20)) console.log(`  ${k} x${v}`);

// Show the top remaining rgba
const rm = {};
for (const m of noUrl.matchAll(/rgba?\([^)]*\)/g)) {
  const norm = m[0].replace(/\s+/g, '').toLowerCase();
  rm[norm] = (rm[norm] || 0) + 1;
}
const sortedR = Object.entries(rm).sort((a, b) => b[1] - a[1]);
console.log('\nTop remaining rgba:');
for (const [k, v] of sortedR.slice(0, 20)) console.log(`  ${k} x${v}`);
