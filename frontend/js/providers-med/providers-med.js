// Провайдеры (медиа) — CRUD шаблонов медиа-провайдеров.
// Хранятся на бэкенде (providers.json, Fernet-шифрованный ключ), активный
// провайдер подхватывается слоем генерации медиа (нативные tool-calling + MCP).
// Все функции вешаются на window для вызова из core/main.js и HTML onclick.
(function () {
    if (typeof document === 'undefined') return;

    function el(id) { return document.getElementById(id); }

    function activeId() {
        const grid = el('providersMedGrid');
        const sel = grid && grid.querySelector('.provider-card.active');
        return sel ? sel.dataset.id : '';
    }

    function _flash(msg, kind) {
        if (typeof window.flashStatus === 'function') window.flashStatus(msg);
    }

    // SVG icon helper
    function providerIconSvg(iconName) {
        const safe = (iconName || 'custom').replace(/[^a-z0-9]/gi, '');
        return `<svg viewBox="0 0 24 24"><use href="#provider-icon-${safe}"/></svg>`;
    }

    // Capability badges
    function capBadges(caps) {
        const badges = [];
        if (caps.image) {
            badges.push(`<span class="cap-badge active">
                <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                Картинки</span>`);
        }
        if (caps.video) {
            badges.push(`<span class="cap-badge active">
                <svg viewBox="0 0 24 24"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
                Видео</span>`);
        }
        if (caps.audio) {
            badges.push(`<span class="cap-badge active">
                <svg viewBox="0 0 24 24"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                Голос</span>`);
        }
        return badges.join('');
    }

    // Dialect chips
    function dialectChips(dialect) {
        const chips = [];
        if (dialect.extra_body_ref) chips.push('<span class="dialect-chip">extra_body</span>');
        if (dialect.v1_suffix) chips.push('<span class="dialect-chip">/v1</span>');
        if (dialect.return_base64) chips.push('<span class="dialect-chip">b64</span>');
        if (dialect.videos_mode_body) chips.push('<span class="dialect-chip">video-mode</span>');
        if (dialect.agnesapi_poll) chips.push('<span class="dialect-chip">agnesapi</span>');
        if (dialect.stt) chips.push('<span class="dialect-chip">STT</span>');
        if (dialect.xi_api_key) chips.push('<span class="dialect-chip">xi-key</span>');
        return chips.join('');
    }

    // Render a single provider card
    function renderProviderCard(p, activeId_) {
        const card = document.createElement('div');
        card.className = 'provider-card' + (p.id === activeId_ ? ' active' : '');
        card.dataset.id = p.id;

        const caps = p.capabilities || {};
        const dialect = p.dialect || {};

        card.innerHTML = `
            <div class="provider-header">
                <div class="provider-icon-wrap">${providerIconSvg(p.icon || 'custom')}</div>
                <div class="provider-name-block">
                    <h4 class="provider-name">${p.name || p.id}</h4>
                    <p class="provider-base">${p.base_url || 'без base'}</p>
                </div>
                ${p.id === activeId_ ? '<span class="provider-badge">активен</span>' : ''}
            </div>
            <div class="provider-caps">${capBadges(caps)}</div>
            <div class="provider-dialects">${dialectChips(dialect)}</div>
            <div class="provider-actions">
                <button class="provider-action-btn" data-action="activate">
                    ${p.id === activeId_ ?
                        '<svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg> Активен' :
                        '<svg viewBox="0 0 24 24"><path d="M12 3v18M3 12h18"/></svg> Активировать'}
                </button>
                <button class="provider-action-btn" data-action="edit">
                    <svg viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    Редактировать
                </button>
                <button class="provider-action-btn" data-action="delete">
                    <svg viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    Удалить
                </button>
            </div>
        `;

        // Bind actions
        card.querySelector('[data-action="activate"]').onclick = () => {
            if (p.id === activeId_) {
                fetch(`${API_BASE}/api/providers/deactivate`, { method: 'POST' })
                    .then(() => loadProvidersMedUI()).catch(() => _flash('Не удалось снять'));
            } else {
                fetch(`${API_BASE}/api/providers/${encodeURIComponent(p.id)}/activate`, { method: 'POST' })
                    .then(() => loadProvidersMedUI()).catch(() => _flash('Не удалось активировать'));
            }
        };

        card.querySelector('[data-action="edit"]').onclick = () => {
            showProvidersMedForm(p);
        };

        card.querySelector('[data-action="delete"]').onclick = () => {
            const confirmDelete = () => {
                fetch(`${API_BASE}/api/providers/${encodeURIComponent(p.id)}`, { method: 'DELETE' })
                    .then(() => loadProvidersMedUI()).catch(() => _flash('Не удалось удалить'));
            };
            if (window.amtConfirm) {
                window.amtConfirm({
                    title: 'Удалить провайдера?',
                    text: `«${p.name || p.id}» будет удалён.`
                }).then(ok => { if (ok) confirmDelete(); });
            } else {
                if (confirm(`Удалить «${p.name || p.id}»?`)) confirmDelete();
            }
        };

        return card;
    }

    // Список карточек провайдеров.
    window.loadProvidersMedUI = async function () {
        const grid = el('providersMedGrid');
        if (!grid) return;
        grid.innerHTML = '<div class="providers-empty"><div>Загрузка…</div></div>';

        let data = null;
        try {
            const r = await fetch(API_BASE + '/api/providers');
            data = await r.json();
        } catch (e) {
            grid.innerHTML = '<div class="providers-empty"><div>Не удалось загрузить (бэкенд не запущен?)</div></div>';
            return;
        }

        const providers = (data && data.providers) || [];
        const activeId_ = (data && data.activeId) || '';

        if (!providers.length) {
            grid.innerHTML = `
                <div class="providers-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                        <rect x="3" y="4" width="18" height="14" rx="2"/>
                        <line x1="3" y1="9" x2="21" y2="9"/>
                        <circle cx="18" cy="15" r="2.4"/>
                    </svg>
                    <div>Нет провайдеров. Нажмите «Добавить провайдера».</div>
                </div>
            `;
        } else {
            grid.innerHTML = '';
            for (const p of providers) {
                grid.appendChild(renderProviderCard(p, activeId_));
            }
        }

        // Связываем кнопки формы.
        const addBtn = el('providersMedAddBtn');
        if (addBtn) addBtn.onclick = () => showProvidersMedForm();

        const form = el('providersMedForm');
        const saveBtn = el('providersMedSaveBtn');
        const cancelBtn = el('providersMedCancelBtn');
        if (cancelBtn) cancelBtn.onclick = () => hideProvidersMedForm();
        if (saveBtn) saveBtn.onclick = saveProvidersMed;
    };

    function hideProvidersMedForm() {
        const form = el('providersMedForm');
        if (form) form.classList.remove('visible');
        _resetProvidersMedForm();
    }

    function _resetProvidersMedForm() {
        ['pmedName', 'pmedBaseUrl', 'pmedKey', 'pmedModel'].forEach(id => {
            const e = el(id);
            if (e) e.value = '';
        });
        const icon = el('pmedIcon');
        if (icon) icon.value = 'custom';
        ['pmedCapImage', 'pmedCapVideo'].forEach(id => {
            const e = el(id);
            if (e) e.checked = true;
        });
        ['pmedCapAudio', 'pmedDRef', 'pmedDV1', 'pmedDReturn64', 'pmedDVidMode', 'pmedDAgnesPoll', 'pmedDStt', 'pmedDXiKey'].forEach(id => {
            const e = el(id);
            if (e) e.checked = false;
        });
        const form = el('providersMedForm');
        if (form) form.classList.remove('visible');
        const title = el('providersMedFormTitle');
        if (title) title.textContent = 'Новый провайдер';
    }

    function showProvidersMedForm(provider) {
        _resetProvidersMedForm();
        const form = el('providersMedForm');
        if (!form) return;

        const title = el('providersMedFormTitle');
        if (title) title.textContent = provider ? `Редактировать: ${provider.name}` : 'Новый провайдер';

        if (provider) {
            el('pmedName').value = provider.name || '';
            el('pmedBaseUrl').value = provider.base_url || '';
            el('pmedKey').value = ''; // Never show existing key
            el('pmedModel').value = provider.model || '';
            el('pmedIcon').value = provider.icon || 'custom';
            el('pmedCapImage').checked = provider.capabilities?.image ?? true;
            el('pmedCapVideo').checked = provider.capabilities?.video ?? true;
            el('pmedCapAudio').checked = provider.capabilities?.audio ?? false;
            el('pmedDRef').checked = provider.dialect?.extra_body_ref ?? false;
            el('pmedDV1').checked = provider.dialect?.v1_suffix ?? false;
            el('pmedDReturn64').checked = provider.dialect?.return_base64 ?? false;
            el('pmedDVidMode').checked = provider.dialect?.videos_mode_body ?? false;
            el('pmedDAgnesPoll').checked = provider.dialect?.agnesapi_poll ?? false;
            el('pmedDStt').checked = provider.dialect?.stt ?? false;
            el('pmedDXiKey').checked = provider.dialect?.xi_api_key ?? false;
            form.dataset.editingId = provider.id;
        } else {
            form.dataset.editingId = '';
        }

        form.classList.add('visible');
        el('pmedName').focus();
        form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    async function saveProvidersMed() {
        const g = id => el(id).value.trim();
        const c = id => el(id).checked;
        const payload = {
            name: g('pmedName') || 'provider',
            base_url: g('pmedBaseUrl'),
            api_key: g('pmedKey'),
            model: g('pmedModel'),
            icon: el('pmedIcon').value,
            capabilities: { image: c('pmedCapImage'), video: c('pmedCapVideo'), audio: c('pmedCapAudio') },
            dialect: {
                extra_body_ref: c('pmedDRef'),
                v1_suffix: c('pmedDV1'),
                return_base64: c('pmedDReturn64'),
                videos_mode_body: c('pmedDVidMode'),
                agnesapi_poll: c('pmedDAgnesPoll'),
                stt: c('pmedDStt'),
                xi_api_key: c('pmedDXiKey'),
            },
        };

        const editingId = el('providersMedForm').dataset.editingId;
        let url, method;

        if (editingId) {
            url = `${API_BASE}/api/providers/${encodeURIComponent(editingId)}`;
            method = 'PUT';
        } else {
            url = `${API_BASE}/api/providers`;
            method = 'POST';
        }

        try {
            const r = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            _flash(editingId ? 'Провайдер обновлён' : 'Провайдер добавлен');
            hideProvidersMedForm();
            loadProvidersMedUI();
        } catch (e) {
            _flash('Ошибка: ' + e.message, 'error');
        }
    }
})();
