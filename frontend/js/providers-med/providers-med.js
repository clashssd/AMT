// Провайдеры (медиа) — CRUD шаблонов медиа-провайдеров.
// Хранятся на бэкенде (providers.json, Fernet-шифрованный ключ), активный
// провайдер подхватывается слоем генерации медиа (нативные tool-calling + MCP).
// Все функции вешаются на window для вызова из core/main.js и HTML onclick.
(function () {
    if (typeof document === 'undefined') return;

    function el(id) { return document.getElementById(id); }

    function activeId() {
        const list = el('providersMedList');
        const sel = list && list.querySelector('.mcp-selected');
        return sel ? sel.dataset.id : '';
    }

    function _flash(msg, kind) {
        if (typeof window.flashStatus === 'function') window.flashStatus(msg);
    }

    // Список карточек провайдеров.
    window.loadProvidersMedUI = async function () {
        const list = el('providersMedList');
        if (!list) return;
        list.innerHTML = '<div class="mcp-empty">Загрузка…</div>';
        let data = null;
        try {
            const r = await fetch(API_BASE + '/api/providers');
            data = await r.json();
        } catch (e) {
            list.innerHTML = '<div class="mcp-empty">Не удалось загрузить (бэкенд не запущен?)</div>';
            return;
        }
        const providers = (data && data.providers) || [];
        const activeId_ = (data && data.activeId) || '';
        if (!providers.length) {
            list.innerHTML = '<div class="mcp-empty">Нет провайдеров. Нажмите «Добавить провайдера».</div>';
            return;
        }
        list.innerHTML = '';
        for (const p of providers) {
            const card = document.createElement('div');
            card.className = 'mcp-item' + (p.id === activeId_ ? ' mcp-selected' : '');
            card.dataset.id = p.id;
            const caps = p.capabilities || {};
            const capBadges = [
                caps.image ? '🖼' : null,
                caps.video ? '🎬' : null,
                caps.audio ? '🔊' : null
            ].filter(Boolean).join(' ');
            const name = document.createElement('div');
            name.className = 'mcp-item-title';
            name.textContent = (p.name || p.id) + (p.hasKey ? ' 🔒' : '') + ' ' + capBadges;
            const meta = document.createElement('div');
            meta.className = 'mcp-item-meta';
            meta.textContent = p.base_url || 'без base';
            card.appendChild(name);
            card.appendChild(meta);
            if (p.id === activeId_) {
                const act = document.createElement('span');
                act.className = 'mcp-item-status';
                act.textContent = 'активен';
                card.appendChild(act);
            }
            const acts = document.createElement('div');
            acts.className = 'mcp-item-actions';
            acts.style.marginTop = '6px';
            const btnActivate = document.createElement('button');
            btnActivate.className = 'test-btn';
            btnActivate.textContent = p.id === activeId_ ? 'Снять активный' : 'Активировать';
            btnActivate.onclick = () => {
                const target = p.id === activeId_ ? null : p.id;
                if (target) fetch(`${API_BASE}/api/providers/${encodeURIComponent(p.id)}/activate`, { method: 'POST' })
                    .then(() => loadProvidersMedUI()).catch(() => _flash('Не удалось активировать'));
                else fetch(`${API_BASE}/api/providers/deactivate`, { method: 'POST' })
                    .then(() => loadProvidersMedUI()).catch(() => _flash('Не удалось снять'));
            };
            acts.appendChild(btnActivate);
            const btnDel = document.createElement('button');
            btnDel.className = 'test-btn';
            btnDel.textContent = 'Удалить';
            btnDel.onclick = () => {
                window.amtConfirm
                    ? window.amtConfirm({ title: 'Удалить провайдера?', text: `«${p.name || p.id}» будет удалён.` })
                        .then(ok => { if (ok) fetch(`${API_BASE}/api/providers/${encodeURIComponent(p.id)}`, { method: 'DELETE' }).then(() => loadProvidersMedUI()); })
                    : (confirm(`Удалить «${p.name || p.id}»?`) ? fetch(`${API_BASE}/api/providers/${encodeURIComponent(p.id)}`, { method: 'DELETE' }).then(() => loadProvidersMedUI()) : null);
            };
            acts.appendChild(btnDel);
            card.appendChild(acts);
            list.appendChild(card);
        }

        // Связываем кнопки формы.
        const addBtn = el('providersMedAddBtn');
        if (addBtn) addBtn.onclick = () => showProvidersMedForm();
        const form = el('providersMedForm');
        const saveBtn = el('providersMedSaveBtn');
        const cancelBtn = el('providersMedCancelBtn');
        if (cancelBtn) cancelBtn.onclick = () => { form.style.display = 'none'; _resetProvidersMedForm(); };
        if (saveBtn) saveBtn.onclick = saveProvidersMed;
    };

    function _resetProvidersMedForm() {
        ['pmedName', 'pmedBaseUrl', 'pmedKey', 'pmedModel'].forEach(id => { const e = el(id); if (e) e.value = ''; });
        ['pmedCapImage', 'pmedCapVideo'].forEach(id => { const e = el(id); if (e) e.checked = true; });
        ['pmedCapAudio', 'pmedDRef', 'pmedDV1', 'pmedDReturn64', 'pmedDVidMode', 'pmedDAgnesPoll', 'pmedDStt', 'pmedDXiKey']
            .forEach(id => { const e = el(id); if (e) e.checked = false; });
        const form = el('providersMedForm');
        if (form) form.style.display = 'none';
    }

    function showProvidersMedForm() {
        _resetProvidersMedForm();
        const form = el('providersMedForm');
        if (form) form.style.display = 'block';
        const n = el('pmedName');
        if (n) n.focus();
    }

    async function saveProvidersMed() {
        const g = id => el(id).value.trim();
        const c = id => el(id).checked;
        const payload = {
            name: g('pmedName') || 'provider',
            base_url: g('pmedBaseUrl'),
            api_key: g('pmedKey'),
            model: g('pmedModel'),
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
        try {
            const r = await fetch(`${API_BASE}/api/providers`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const d = await r.json();
            _flash('Провайдер добавлен');
            loadProvidersMedUI();
        } catch (e) {
            _flash('Ошибка: ' + e.message, 'error');
        }
    }
})();
