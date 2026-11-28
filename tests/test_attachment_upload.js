// Regression: "AI не видит фото/файл, прикреплённый через Ctrl+V и скрепку"
//
// Корень: в sendMessage() глобальный attachedFiles очищается (attachedFiles = [])
// ДО вызова uploadAttachments(). uploadAttachments() итерирует attachedFiles,
// поэтому при загрузке обрабатывался уже пустой массив -> ни одного файла не
// попадало на бэкенд -> в FILES_DIR не появлялись байты -> ИИ «не видел фото».
//
// Фикс: sendMessage передаёт в uploadAttachments() отобранный срез
// _filesForThisMessage (созданный до очистки глобального массива), а сам
// uploadAttachments() принимает список явно.
//
// Тест source-check (plain Node, без jsdom), как test_stream_cards.js.
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const BASE = path.join(__dirname, '..');
const mainJs = fs.readFileSync(path.join(BASE, 'frontend', 'js', 'core', 'main.js'), 'utf8');

let passed = 0;
function t(name, fn) { try { fn(); console.log('  ✓ ' + name); passed++; } catch (e) { console.error('  ✗ ' + name + '\n    ' + e.message); process.exitCode = 1; } }

// 1. uploadAttachments принимает явный список (items), по умолчанию — attachedFiles
t('uploadAttachments() принимает параметр items (не только глобальный attachedFiles)', () => {
  assert.ok(/async function uploadAttachments\(items\)/.test(mainJs),
    'uploadAttachments должен принимать параметр items');
  assert.ok(mainJs.includes('const list = Array.isArray(items) ? items : attachedFiles;'),
    'внутрь должен резолвиться list из items либо из attachedFiles');
  assert.ok(/for \(const item of list\)/.test(mainJs),
    'цикл загрузки должен идти по list');
});

// 2. В release (1.1.5) sendMessage передаёт _filesForThisMessage, а не пустые скобки
t('sendMessage вызывает uploadAttachments(_filesForThisMessage) — не глобальный (пустой)', () => {
  assert.ok(mainJs.includes('attachmentsPayload = await uploadAttachments(_filesForThisMessage);'),
    'загрузка в sendMessage должна передавать отобранный срез _filesForThisMessage');
  // И НЕ должно остаться «загрузки по глобальному» с пустыми скобками в sendMessage
  // (определение функции uploadAttachments() без аргументов тоже не должно остаться)
  assert.ok(!/await uploadAttachments\(\)/.test(mainJs),
    'не должно быть вызова uploadAttachments() без аргумента (читал бы пустой глобальный массив)');
});

// 3. _filesForThisMessage создаётся slice'ом ДО очистки attachedFiles
t('_filesForThisMessage = attachedFiles.slice() создаётся до очистки attachedFiles в sendMessage', () => {
  const sliceIdx = mainJs.indexOf('_filesForThisMessage = attachedFiles.slice()');
  assert.ok(sliceIdx > 0, 'нет назначения _filesForThisMessage = attachedFiles.slice()');
  // ближайшая очистка attachedFiles ПОСЛЕ среза — та, что прямо в sendMessage
  const clearIdx = mainJs.indexOf('attachedFiles = [];', sliceIdx);
  assert.ok(clearIdx > sliceIdx, 'сразу после среза в sendMessage должна идти очистка attachedFiles');
  // и до загрузки (uploadAttachments(_filesForThisMessage)) срез уже создан
  const uploadIdx = mainJs.indexOf('uploadAttachments(_filesForThisMessage)');
  assert.ok(uploadIdx > sliceIdx, 'загрузка должна происходить ПОСЛЕ создания среза');
});

// 4. revoke objectURL те��ерь только по обработанному list, а не по глобальному
t('revoke objectURL идёт по list (обработанные), не по глобальному attachedFiles', () => {
  assert.ok(mainJs.includes('list.forEach(f => { if (f.thumb) URL.revokeObjectURL(f.thumb); });'),
    'release objectURL должен происходить по list');
});

console.log('\n  ' + passed + '/' + 4 + ' attachment-upload regression checks passed.');
