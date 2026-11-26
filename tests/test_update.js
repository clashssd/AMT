/**
 * tests/test_update.js — smoke tests for the auto-update system.
 *
 * Same style as test_secrets.js: plain Node, no Electron.
 * Asserts the interface shape across the whole update pipeline:
 *   electron/update-manager.js, electron/update-ipc.js, main.js,
 *   electron/preload.js, frontend/js/update-ui.js, frontend/home.html,
 *   frontend/css/style.css, package.json (deps + build.publish),
 *   backend/changelog.json.
 */
'use strict';

const assert = require('assert');
const path = require('path');
const fs = require('fs');

const root = path.join(__dirname, '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');

// --- 1. electron/update-manager.js exists and exports the right symbols ---
assert.ok(fs.existsSync(path.join(root, 'electron', 'update-manager.js')), 'electron/update-manager.js must exist');
const um = read('electron/update-manager.js');
assert.ok(um.includes("require('electron-updater')"), 'update-manager must require electron-updater');
assert.ok(um.includes('init'), 'update-manager must export init');
assert.ok(um.includes('checkForUpdates'), 'update-manager must export checkForUpdates');
assert.ok(um.includes('downloadUpdate'), 'update-manager must export downloadUpdate');
assert.ok(um.includes('quitAndInstall'), 'update-manager must export quitAndInstall');
assert.ok(um.includes('getStatus'), 'update-manager must export getStatus');
assert.ok(um.includes('openReleasesPage'), 'update-manager must export openReleasesPage');
assert.ok(um.includes('autoDownload = false'), 'update-manager must disable autoDownload');
assert.ok(um.includes('autoInstallOnAppQuit = false'), 'update-manager must disable autoInstallOnAppQuit');
assert.ok(um.includes('github.com/') && um.includes('releases'), 'update-manager must open the GitHub Releases page');
assert.ok(um.includes('debug.log'), 'update-manager must log to debug.log');
assert.ok(um.includes('APPDATA'), 'update-manager must use APPDATA for the log path');
assert.ok(um.includes('update-available'), 'update-manager must handle update-available events');
assert.ok(um.includes('download-progress'), 'update-manager must handle download-progress events');
assert.ok(um.includes('update-downloaded'), 'update-manager must handle update-downloaded events');
assert.ok(um.includes('error'), 'update-manager must handle error events');

// --- 2. electron/update-ipc.js exists and registers the handlers ---
assert.ok(fs.existsSync(path.join(root, 'electron', 'update-ipc.js')), 'electron/update-ipc.js must exist');
const ui = read('electron/update-ipc.js');
assert.ok(ui.includes("require('./update-manager')"), 'update-ipc must require update-manager');
assert.ok(ui.includes('registerUpdateIpc'), 'update-ipc must export registerUpdateIpc');
assert.ok(ui.includes("'updates:status'"), 'update-ipc must handle updates:status');
assert.ok(ui.includes("'updates:check'"), 'update-ipc must handle updates:check');
assert.ok(ui.includes("'updates:download'"), 'update-ipc must handle updates:download');
assert.ok(ui.includes("'updates:install'"), 'update-ipc must handle updates:install');
assert.ok(ui.includes("'updates:openReleases'"), 'update-ipc must handle updates:openReleases');

// --- 3. main.js wires it all together ---
const mainSrc = read('main.js');
assert.ok(mainSrc.includes("require('./electron/update-ipc')"), 'main.js must require update-ipc');
assert.ok(mainSrc.includes("require('./electron/update-manager')"), 'main.js must require update-manager');
assert.ok(mainSrc.includes('registerUpdateIpc'), 'main.js must call registerUpdateIpc');
assert.ok(mainSrc.includes('updateManager.init'), 'main.js must call updateManager.init');
assert.ok(mainSrc.includes('delayMs'), 'main.js must pass delayMs to updateManager.init');
assert.ok(mainSrc.includes('intervalMs'), 'main.js must pass intervalMs to updateManager.init');

// --- 4. preload.js exposes the updates API ---
const preloadSrc = read('electron/preload.js');
assert.ok(preloadSrc.includes('updates:'), 'preload.js must expose window.api.updates');
assert.ok(preloadSrc.includes("'updates:check'"), 'preload.js must wire updates:check');
assert.ok(preloadSrc.includes("'updates:download'"), 'preload.js must wire updates:download');
assert.ok(preloadSrc.includes("'updates:install'"), 'preload.js must wire updates:install');
assert.ok(preloadSrc.includes("'updates:openReleases'"), 'preload.js must wire updates:openReleases');
assert.ok(preloadSrc.includes("'updates:status-changed'"), 'preload.js must subscribe to updates:status-changed');

// --- 5. frontend/js/update-ui.js exists and defines the API ---
assert.ok(fs.existsSync(path.join(root, 'frontend', 'js', 'update-ui.js')), 'frontend/js/update-ui.js must exist');
const updateUi = read('frontend/js/update-ui.js');
assert.ok(updateUi.includes('window.AMTUpdates'), 'update-ui.js must define window.AMTUpdates');
assert.ok(updateUi.includes('init'), 'window.AMTUpdates must have init');
assert.ok(updateUi.includes('check'), 'window.AMTUpdates must have check');
assert.ok(updateUi.includes('download'), 'window.AMTUpdates must have download');
assert.ok(updateUi.includes('install'), 'window.AMTUpdates must have install');
assert.ok(updateUi.includes('openReleases'), 'window.AMTUpdates must have openReleases');
assert.ok(updateUi.includes('updateBanner'), 'update-ui.js must reference the update banner');
assert.ok(updateUi.includes('updateDialog'), 'update-ui.js must reference the update dialog');

// --- 6. home.html has the banner, dialog, and script tag ---
const html = read('frontend/home.html');
assert.ok(html.includes('id="updateBanner"'), 'home.html must have the updateBanner element');
assert.ok(html.includes('id="updateDialog"'), 'home.html must have the updateDialog element');
assert.ok(html.includes('./js/update-ui.js'), 'home.html must load update-ui.js');
// update-ui.js must be loaded before main.js
assert.ok(html.indexOf('update-ui.js') < html.indexOf('./js/main.js'), 'update-ui.js must load before main.js');

// --- 7. style.css has the update styles ---
const css = read('frontend/css/style.css');
assert.ok(css.includes('.update-banner'), 'style.css must have .update-banner styles');
assert.ok(css.includes('.update-progress'), 'style.css must have .update-progress styles');

// --- 8. package.json: electron-updater is a runtime dep ---
const pkg = JSON.parse(read('package.json'));
assert.ok(pkg.dependencies && pkg.dependencies['electron-updater'], 'package.json must have electron-updater in dependencies');
assert.ok(pkg.build && pkg.build.publish, 'package.json build must have publish config');
assert.strictEqual(pkg.build.publish.provider, 'github', 'publish provider must be github');
assert.strictEqual(pkg.build.publish.owner, 'clashssd', 'publish owner must be clashssd');
assert.strictEqual(pkg.build.publish.repo, 'AMT', 'publish repo must be AMT');

// --- 9. changelog.json has the 1.0.7 entry ---
const changelog = JSON.parse(read('backend/changelog.json'));
assert.strictEqual(changelog.version, '1.0.7', 'changelog top-level version must be 1.0.7');
const rel107 = changelog.releases.find(r => r.version === '1.0.7');
assert.ok(rel107, 'changelog.json must contain a 1.0.7 release entry');
assert.ok(Array.isArray(rel107.changes) && rel107.changes.length > 0, '1.0.7 entry must have changes');

// --- 10. release instructions exist somewhere in docs ---
const readmePath = path.join(root, 'README.md');
const hasReadme = fs.existsSync(readmePath);
assert.ok(hasReadme, 'README.md must exist (release instructions)');
const readme = read('README.md');
assert.ok(readme.includes('v1.0.7') || readme.includes('release'), 'README.md must document the release process');

console.log('PASS test_update: all interface checks passed');
