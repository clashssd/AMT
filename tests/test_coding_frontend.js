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
assert(main.includes('codingPageVisibility'), 'main.js should wire coding settings visibility');
assert(main.includes('codingSettingsSaveBtn'), 'main.js should wire coding settings save');
assert(main.includes("key: 'coding'") && main.includes("title: 'Коддинг'"), 'main.js should render a coding storage section');
assert(main.includes('codingSessions = []'), 'renderStorageInteractive should accept coding sessions');
assert(main.includes('tool_approval_request'), 'main.js should handle coding approval requests');
assert(main.includes('respondCodingApproval'), 'main.js should respond to coding approval decisions');
const fallback = main.slice(main.indexOf('async function fallbackRest'));
assert(fallback.includes('chat_mode'), 'fallbackRest should send chat_mode');
assert(fallback.includes('project_root'), 'fallbackRest should send project_root');
assert(fallback.includes('tool_policy'), 'fallbackRest should send tool_policy');

console.log('test_coding_frontend.js: PASS');
