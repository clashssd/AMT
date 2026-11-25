#!/usr/bin/env node
// Runs all frontend JS tests (Node, no dependencies).
'use strict';
const { spawnSync } = require('node:child_process');
const { join } = require('node:path');

const files = ['test_secure_store.js', 'test_token_estimator.js', 'test_main_logic.js', 'test_ctx_menu.js', 'test_stream_cards.js', 'test_player_overlay.js', 'test_round7.js', 'test_build_script.js', 'test_secrets.js'];
let failed = 0;
for (const f of files) {
    const p = join(__dirname, f);
    const res = spawnSync(process.execPath, [p], { stdio: 'inherit' });
    if (res.status !== 0) failed++;
}
process.exit(failed ? 1 : 0);
