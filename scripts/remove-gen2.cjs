const fs = require('fs');
const p = 'C:/Users/berds/Desktop/AMT — копия/frontend/js/main.js';
const lines = fs.readFileSync(p, 'utf8').split('\n');
// Second generate block: lines 4409-4847 (1-based) = indices 4408-4846 (0-based)
const out = [...lines.slice(0, 4408), ...lines.slice(4847)];
fs.writeFileSync(p, out.join('\n'));
console.log('Removed 2nd generate block. New line count:', out.length);
