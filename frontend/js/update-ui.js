/**
 * frontend/js/update-ui.js — Update banner + dialog (vanilla JS).
 *
 * Loaded before main.js. Defines window.AMTUpdates with:
 *   init()       — wire the banner, dialog, and changelog refresh button
 *   check()      — trigger an IPC autoUpdater check
 *   download()   — start downloading the update
 *   install()    — quit and install
 *   openReleases() — open GitHub Releases in the external browser
 *
 * State machine:
 *   idle → checking → available | not-available
 *   available → downloading → downloaded
 *   any → error
 *
 * The dialog is shown on 'available' or 'downloaded'. The banner shows
 * 'available' (new version is ready) and 'error'. Both are dismissable.
 */
(function () {
    'use strict';

    // --- state ---
    let _state = {
        status: 'idle',       // idle | checking | available | not-available | downloading | downloaded | error
        newVersion: null,     // e.g. '1.0.7'
        error: null,          // error message string
        progress: 0,          // 0-100
        speed: null,          // bytes/sec or null
    };

    const API_BASE = window.location.origin;

    // --- element refs (set in init) ---
    let _banner = null;
    let _bannerText = null;
    let _bannerDismiss = null;
    let _bannerLink = null;
    let _dialog = null;
    let _dialogTitle = null;
    let _dialogVersion = null;
    let _dialogChangelog = null;
    let _dialogProgressWrap = null;
    let _dialogProgress = null;
    let _dialogProgressText = null;
    let _dialogDownloadBtn = null;
    let _dialogLaterBtn = null;
    let _dialogInstallBtn = null;
    let _dialogOpenReleasesBtn = null;
    let _dialogError = null;
    let _unsubStatus = null;

    // --- helpers ---
    function _isElectron() {
        return !!(window.api && window.api.updates);
    }

    function _showBanner() {
        if (!_banner) return;
        _banner.classList.remove('hidden');
    }
    function _hideBanner() {
        if (!_banner) return;
        _banner.classList.add('hidden');
    }
    function _showDialog() {
        if (!_dialog) return;
        _dialog.classList.remove('hidden');
    }
    function _hideDialog() {
        if (!_dialog) return;
        _dialog.classList.add('hidden');
    }

    function _updateDialogUI() {
        if (!_dialogVersion) return;
        const s = _state;

        // Title
        if (_dialogTitle) {
            if (s.status === 'downloaded') {
                _dialogTitle.textContent = 'Обновление скачано';
            } else if (s.status === 'error') {
                _dialogTitle.textContent = 'Ошибка обновления';
            } else {
                _dialogTitle.textContent = 'Доступно обновление';
            }
        }

        // Version
        _dialogVersion.textContent = s.newVersion ? `v${s.newVersion}` : '';

        // Buttons visibility
        if (_dialogDownloadBtn) {
            _dialogDownloadBtn.style.display = (s.status === 'available') ? '' : 'none';
            _dialogDownloadBtn.disabled = s.status === 'downloading';
            _dialogDownloadBtn.textContent = s.status === 'downloading' ? 'Загрузка…' : '⬇ Скачать обновление';
        }
        if (_dialogLaterBtn) {
            _dialogLaterBtn.style.display = (s.status === 'available' || s.status === 'downloading') ? '' : 'none';
        }
        if (_dialogInstallBtn) {
            _dialogInstallBtn.style.display = (s.status === 'downloaded') ? '' : 'none';
        }
        if (_dialogOpenReleasesBtn) {
            _dialogOpenReleasesBtn.style.display = (s.status === 'error') ? '' : 'none';
        }

        // Progress
        if (_dialogProgressWrap) {
            _dialogProgressWrap.style.display = (s.status === 'downloading') ? '' : 'none';
        }
        if (_dialogProgress) {
            _dialogProgress.style.width = Math.min(100, s.progress) + '%';
        }
        if (_dialogProgressText) {
            let txt = Math.round(s.progress) + '%';
            if (s.speed != null) {
                txt += ' · ' + (s.speed > 1048576 ? (s.speed / 1048576).toFixed(1) + ' МБ/с' : Math.round(s.speed / 1024) + ' КБ/с');
            }
            _dialogProgressText.textContent = txt;
        }

        // Error text
        if (_dialogError) {
            _dialogError.style.display = s.error ? '' : 'none';
            if (s.error) _dialogError.textContent = s.error;
        }
    }

    function _updateBannerUI() {
        if (!_bannerText) return;
        const s = _state;
        if (s.status === 'available' && s.newVersion) {
            _bannerText.textContent = `Доступно обновление v${s.newVersion}`;
            _bannerLink.style.display = '';
            _showBanner();
        } else if (s.status === 'error') {
            _bannerText.textContent = 'Ошибка проверки обновлений' + (s.error ? ': ' + s.error : '');
            if (_bannerLink) _bannerLink.style.display = 'none';
            _showBanner();
        } else {
            _hideBanner();
        }
    }

    function _handleStatus(payload) {
        const s = _state;
        const ev = payload && payload.event;
        const data = (payload && payload.data) || {};

        switch (ev) {
            case 'checking':
                s.status = 'checking';
                break;
            case 'available':
                s.status = 'available';
                s.newVersion = data.version || null;
                s.progress = 0;
                s.error = null;
                _showDialog();
                _updateDialogUI();
                break;
            case 'not-available':
                s.status = 'not-available';
                s.error = null;
                _hideDialog();
                break;
            case 'downloading':
                s.status = 'downloading';
                s.progress = data.percent != null ? data.percent : (s.progress || 0);
                s.speed = data.bytesPerSecond != null ? data.bytesPerSecond : s.speed;
                _updateDialogUI();
                break;
            case 'downloaded':
                s.status = 'downloaded';
                s.progress = 100;
                s.error = null;
                _updateDialogUI();
                break;
            case 'error':
                s.status = 'error';
                s.error = data.message || 'Неизвестная ошибка';
                _showDialog();
                _updateDialogUI();
                break;
        }
        _updateBannerUI();
    }

    // --- changelog fetch (independent of main.js) ---
    async function _loadChangelogIntoDialog() {
        if (!_dialogChangelog) return;
        try {
            const r = await fetch(`${API_BASE}/api/changelog`);
            const data = await r.json();
            const releases = (data.releases || []);
            if (!releases.length) {
                _dialogChangelog.innerHTML = '<em>Чейнджлог недоступен</em>';
                return;
            }
            // Show up to 3 most recent releases
            _dialogChangelog.innerHTML = releases.slice(0, 3).map(rel =>
                `<div class="update-changelog-item">` +
                `<b>v${rel.version}</b> — ${rel.title || ''}` +
                `<ul>` +
                (rel.changes || []).slice(0, 4).map(c => `<li>${c}</li>`).join('') +
                `</ul></div>`
            ).join('');
        } catch {
            _dialogChangelog.innerHTML = '<em>Не удалось загрузить чейнджлог</em>';
        }
    }

    // --- public API ---
    function init() {
        _banner = document.getElementById('updateBanner');
        _bannerText = _banner ? _banner.querySelector('.update-banner-text') : null;
        _bannerDismiss = _banner ? _banner.querySelector('.update-banner-dismiss') : null;
        _bannerLink = _banner ? _banner.querySelector('.update-banner-link') : null;

        _dialog = document.getElementById('updateDialog');
        if (_dialog) {
            _dialogTitle = _dialog.querySelector('#updateDialogTitle');
            _dialogVersion = _dialog.querySelector('#updateDialogVersion');
            _dialogChangelog = _dialog.querySelector('#updateDialogChangelog');
            _dialogProgressWrap = _dialog.querySelector('.update-progress-wrap');
            _dialogProgress = _dialog.querySelector('.update-progress');
            _dialogProgressText = _dialog.querySelector('.update-progress-text');
            _dialogDownloadBtn = _dialog.querySelector('#updateDownloadBtn');
            _dialogLaterBtn = _dialog.querySelector('#updateLaterBtn');
            _dialogInstallBtn = _dialog.querySelector('#updateInstallBtn');
            _dialogOpenReleasesBtn = _dialog.querySelector('#updateOpenReleasesBtn');
            _dialogError = _dialog.querySelector('#updateDialogError');

            if (_dialogDownloadBtn) {
                _dialogDownloadBtn.addEventListener('click', async () => {
                    if (!_isElectron()) return;
                    const res = await window.api.updates.download();
                    // 'downloading' events will update progress via onStatus
                    if (!res.ok && res.error) {
                        _state.error = res.error;
                        _state.status = 'error';
                        _updateDialogUI();
                        _updateBannerUI();
                    }
                });
            }
            if (_dialogLaterBtn) {
                _dialogLaterBtn.addEventListener('click', () => _hideDialog());
            }
            if (_dialogInstallBtn) {
                _dialogInstallBtn.addEventListener('click', async () => {
                    if (!_isElectron()) return;
                    await _loadChangelogIntoDialog();
                    window.api.updates.install();
                });
            }
            if (_dialogOpenReleasesBtn) {
                _dialogOpenReleasesBtn.addEventListener('click', () => {
                    if (_isElectron()) window.api.updates.openReleases();
                });
            }
            // Dismiss the whole dialog
            const closeBtn = _dialog.querySelector('#updateDialogClose');
            if (closeBtn) closeBtn.addEventListener('click', () => _hideDialog());
        }

        if (_bannerDismiss) {
            _bannerDismiss.addEventListener('click', _hideBanner);
        }
        if (_bannerLink) {
            _bannerLink.addEventListener('click', (e) => {
                e.stopPropagation();
                _showDialog();
            });
        }

        // Subscribe to live status events
        if (_isElectron()) {
            _unsubStatus = window.api.updates.onStatus(_handleStatus);
            // Set current version in the changelog page
            window.api.updates.status().then(info => {
                const verEl = document.getElementById('changelogVersion');
                if (verEl && info && info.version) verEl.textContent = info.version;
            }).catch(() => {});
        }

        // Wire the changelog refresh button on the docs-updates page
        const refBtn = document.getElementById('changelogRefreshBtn');
        if (refBtn) {
            refBtn.addEventListener('click', async () => {
                // Always refresh the local changelog list
                if (typeof window._loadChangelog === 'function') {
                    window._loadChangelog();
                }
                // If in Electron, also trigger a live update check
                if (_isElectron()) {
                    const res = await window.api.updates.check();
                    if (res && res.ok === false && res.error) {
                        _state.error = res.error;
                        _state.status = 'error';
                        _updateBannerUI();
                    }
                }
            });
        }
    }

    window.AMTUpdates = {
        init: init,
        check: async () => {
            if (!_isElectron()) return { ok: false, error: 'Not in Electron' };
            return window.api.updates.check();
        },
        download: async () => {
            if (!_isElectron()) return { ok: false, error: 'Not in Electron' };
            return window.api.updates.download();
        },
        install: async () => {
            if (!_isElectron()) return;
            return window.api.updates.install();
        },
        openReleases: () => {
            if (!_isElectron()) {
                window.open('https://github.com/clashssd/AMT/releases', '_blank');
                return;
            }
            window.api.updates.openReleases();
        },
    };
})();
