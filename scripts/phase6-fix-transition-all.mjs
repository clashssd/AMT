import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const p = path.join(process.cwd(), 'frontend', 'css', 'style.css');
let s = readFileSync(p, 'utf8');
const before = s;

// Line 1818: .settings-nav a → transition: color, background, border
s = s.replace(
  /(\.settings-nav\s+a\s*{[^}]*?)transition:\s*all\s+0\.2s;/s,
  '$1transition: color var(--motion-fast) var(--ease-out), background var(--motion-fast) var(--ease-out), border-color var(--motion-fast) var(--ease-out);'
);

// Line 3251: .chip → transition: background, border-color, color
s = s.replace(
  /(\.chip\s*{[^}]*?)transition:\s*all\s+\.15s;/s,
  '$1transition: background var(--motion-fast) var(--ease-out), border-color var(--motion-fast) var(--ease-out), color var(--motion-fast) var(--ease-out);'
);

// Line 3305: .dash-view-btn → transition: background, color
s = s.replace(
  /(\.dash-view-btn\s*{[^}]*?)transition:\s*all\s+\.15s;/s,
  '$1transition: background var(--motion-fast) var(--ease-out), color var(--motion-fast) var(--ease-out);'
);

writeFileSync(p, s);
console.log('changed:', before !== s);
console.log('remaining "transition: all":', (s.match(/transition:\s*all\b/g) || []).length);
