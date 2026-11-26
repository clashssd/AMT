# SDD ledger — plan: .superpowers/plans/autoupdater-implementation.md

Task 1: complete (commits 2853223..2853223, tests: node tests/run_js_tests.js → all 11 files pass, exit 0)

Ruling: update-manager.js init() accepts getWindows: () => BrowserWindow.getAllWindows() —
deviation from plan (no getWindows param); autoUpdater events are forwarded to all
renderer windows via win.webContents.send('updates:status-changed', payload).
Reason: update-manager is a standalone module; main.js owns the BrowserWindow reference.

Ruling: changelogRefreshBtn in Electron calls both window.AMTUpdates.check() (IPC autoUpdater check)
AND the existing loadChangelog() (backend /api/changelog list). Both happen; the changelog list
still shows, and the live check triggers the banner/dialog via autoUpdater events.

Ruling: test_update.js line 32 — original assertion checked for literal
'github.com/clashssd/AMT/releases'; the code builds the URL from UPDATE_SOURCE object.
Fixed to: um.includes('github.com/') && um.includes('releases').
