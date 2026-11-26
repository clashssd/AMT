const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

function read(file) {
  return fs.readFileSync(path.join(__dirname, '..', file), 'utf8');
}

const main = read('frontend/js/core/main.js');
const home = read('frontend/home.html');

assert(main.includes('chat_mode'), 'main.js should set chat_mode');
assert(main.includes('syncToBackend'), 'main.js should set syncToBackend default');
assert(main.includes('projectRoot'), 'main.js should track coding projectRoot');
assert(main.includes('data-page="code"') || home.includes('data-page="code"'), 'Code sidebar/page surface should exist');
assert(home.includes('sec-coding'), 'home.html should include sec-coding settings section');

console.log('test_coding_frontend.js: PASS');
