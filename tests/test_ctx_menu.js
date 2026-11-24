// Tests for chat context-menu items builder (pure logic extraction).
'use strict';
const assert = require('assert');
const fs = require('node:fs');
const path = require('node:path');

const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'main.js'), 'utf8');

function extractFn(name) {
    const start = src.indexOf('function ' + name + '(');
    assert.ok(start > 0, name + ' not found');
    let i = src.indexOf('{', start), depth = 0, end = -1;
    for (; i < src.length; i++) {
        if (src[i] === '{') depth++;
        else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
    }
    return src.slice(start, end);
}

// Build a context that provides the module-scoped deps used by chatContextItems
function makeCtx() {
    const groups = [{ id: 'g1', name: 'Работа' }, { id: 'g2', name: 'Личное' }];
    const state = { lastMove: null, lastRename: null, lastDel: null, lastOpen: null };
    const deps = `
        const groups = ${JSON.stringify(groups)};
        function moveSpecificChatToGroup(id, g) { state.lastMove = [id, g]; }
        function renameChatById(id) { state.lastRename = id; }
        function deleteChatById(id) { state.lastDel = id; }
        function openChat(c) { state.lastOpen = c; }
        const state = ${JSON.stringify(state)};
        ${extractFn('chatContextItems')}
        return (chat) => ({ items: chatContextItems(chat), state });
    `;
    return new Function(deps)();
}

let passed = 0;
const t = (name, fn) => { fn(); console.log(`  PASS ${name}`); passed++; };

t('context items: 4 top-level actions', () => {
    const { items } = makeCtx()({ id: 'c1', title: 'Чат', messages: [] });
    const labels = items.map(i => i.label);
    assert.deepStrictEqual(labels, ['Переименовать', 'В группу', 'Открыть', 'Удалить чат']);
    assert.strictEqual(items[3].danger, true);
});

t('group submenu lists all groups + "Без группы"', () => {
    const { items } = makeCtx()({ id: 'c1' });
    const group = items.find(i => i.label === 'В группу');
    assert.strictEqual(group.sub.length, 3, '2 groups + Без группы');
    const names = group.sub.map(s => s.label);
    assert.ok(names.includes('Работа') && names.includes('Личное') && names.includes('Без группы'));
});

t('actions invoke correct handlers', () => {
    const { items, state } = makeCtx()({ id: 'cX', title: 't' });
    items[0].action(); // rename
    assert.strictEqual(state.lastRename, 'cX');
    items[2].action(); // open
    assert.ok(state.lastOpen);
    items[3].action(); // delete
    assert.strictEqual(state.lastDel, 'cX');
    // group action
    const g = items.find(i => i.label === 'В группу');
    g.sub[0].action(); // Работа
    assert.deepStrictEqual(state.lastMove, ['cX', 'g1']);
    g.sub[2].action(); // Без группы
    assert.deepStrictEqual(state.lastMove, ['cX', null]);
});

console.log(`\n${passed} context-menu tests passed`);
if (passed === 0) process.exit(1);
