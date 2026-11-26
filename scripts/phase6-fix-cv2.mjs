import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const p = path.join(process.cwd(), 'frontend', 'css', 'components-v2.css');
let s = readFileSync(p, 'utf8');
const before = s;

// Fix 1: `content: ;` (empty content in ::before) -> `content: "";`
s = s.replace(/content:\s*;/g, 'content: "";');

// Fix 2: inset highlight rgba(255,255,255,0.06) -> var(--glass-border)
s = s.replace(/inset 0 1px 0 rgba\(255\s*,\s*255\s*,\s*255\s*,\s*0\.06\)/g, 'inset 0 1px 0 var(--glass-border)');

writeFileSync(p, s);
console.log('content ; still:', s.includes('content: ;'));
console.log('rgba(255,255,255,0.06) left:', (s.match(/rgba\(255\s*,\s*255\s*,\s*255\s*,\s*0\.06\)/g) || []).length);
console.log('var(--glass-border) count:', (s.match(/var\(--glass-border\)/g) || []).length);
console.log('bytes changed:', Buffer.byteLength(s) - Buffer.byteLength(before));
