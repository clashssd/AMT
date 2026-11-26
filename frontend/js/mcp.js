// frontend/js/mcp.js
// MCP-серверы: страница настроек + секция хранилища
// Загружается после main.js (использует API_BASE из main.js).

// ===== Страница настроек: секция «MCP-серверы» =====
async function renderMcpSettings() {
    const list = document.getElementById('mcp-server-list');
    if (!list) return;
    list.innerHTML = '<div class="mcp-empty">Загрузка…</div>';
    let servers = [];
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/servers`);
        servers = await resp.json();
        if (!Array.isArray(servers)) servers = [];
    } catch { servers = []; }
    if (!servers.length) {
        list.innerHTML = '<div class="mcp-empty">Нет подключённых MCP-серверов. Нажмите «＋ Добавить MCP-сервер» ниже.</div>';
        return;
    }
    list.innerHTML = '';
    for (const s of servers) {
        const card = document.createElement('div');
        card.className = 'mcp-server-card' + (s.enabled ? '' : ' off');
        const body = s.transport === 'stdio'
            ? `<code class="mcp-cmd">${escapeHtml(s.command || '')} ${(s.args || []).map(escapeHtml).join(' ')}</code>`
            : `<code class="mcp-cmd">${escapeHtml(s.url || '')}</code>`;
        card.innerHTML = `
            <div class="mcp-card-header">
                <span class="mcp-card-name">${escapeHtml(s.name || s.id)}</span>
                <span class="mcp-badge">${escapeHtml(s.transport)}</span>
                <label class="mcp-enable-toggle" title="Вкл/выкл">
                    <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="mcpToggle('${escapeHtml(s.id)}', this.checked)">
                </label>
            </div>
            <div class="mcp-card-body">${body}</div>
            <div class="mcp-card-actions">
                <button onclick="mcpTest('${escapeHtml(s.id)}')">Тест</button>
                <button onclick="mcpEdit('${escapeHtml(s.id)}')">Изменить</button>
                <button class="danger" onclick="mcpDelete('${escapeHtml(s.id)}')">Удалить</button>
            </div>
        `;
        list.appendChild(card);
    }
}

async function mcpToggle(id, enabled) {
    try {
        await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(id)}/enable`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
    } catch { /* ignore */ }
    flashStatus('MCP-сервер «' + id + '» ' + (enabled ? 'включён' : 'выключен'));
    renderMcpSettings();
}

async function mcpTest(id) {
    flashStatus('Проверка подключения к «' + id + '»…');
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(id)}/test`, { method: 'POST' });
        const data = await resp.json();
        if (data.status === 'connected') {
            const names = (data.tools || []).map(t => '• ' + t.name + (t.description ? ': ' + t.description : '')).join('\n');
            alert('Подключено! Доступно инструментов: ' + (data.tools || []).length + (names ? '\n\n' + names : ''));
        } else {
            alert('Ошибка: ' + (data.message || data.status || 'неизвестно'));
        }
    } catch (e) {
        alert('Ошибка сети: ' + e);
    }
}

async function mcpDelete(id) {
    if (!confirm('Удалить MCP-сервер «' + id + '»?')) return;
    try {
        await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(id)}`, { method: 'DELETE' });
    } catch { /* ignore */ }
    flashStatus('MCP-сервер «' + id + '» удалён');
    renderMcpSettings();
    if (typeof renderMcpStorage === 'function' && document.getElementById('mcp-storage-list')) renderMcpStorage();
}

function mcpEdit(id) {
    // Редактирование: открываем форму и подгружаем текущие настройки сервера.
    fetch(`${API_BASE}/api/mcp/servers`).then(r => r.json()).then(servers => {
        const s = (servers || []).find(x => x.id === id);
        mcpShowAddForm(s || null);
    });
}

function mcpShowAddForm(existing = null) {
    const form = document.getElementById('mcp-add-form');
    if (!form) return;
    const isEdit = !!existing;
    form.style.display = 'block';
    const isStdio = (existing?.transport || 'stdio') === 'stdio';
    form.innerHTML = `
        <h4>${isEdit ? 'Изменить MCP-сервер' : 'Добавить MCP-сервер'}</h4>
        <div class="mcp-form-grid">
            <input id="mcp-name" placeholder="Имя (например, Файловая система)" value="${isEdit ? escapeHtml(existing.name || '') : ''}">
            <input id="mcp-id" placeholder="ID (слог, например fs)" ${isEdit ? 'disabled' : ''} value="${isEdit ? escapeHtml(existing.id || '') : ''}">
            <div class="mcp-transport-radios">
                <label><input type="radio" name="mcp-transport" value="stdio" ${isStdio ? 'checked' : ''}> STDIO</label>
                <label><input type="radio" name="mcp-transport" value="http" ${!isStdio ? 'checked' : ''}> HTTP</label>
            </div>
            <div id="mcp-stdio-fields" style="display:${isStdio ? 'block' : 'none'}">
                <input id="mcp-command" placeholder="Команда (например, npx)" value="${isEdit ? escapeHtml(existing.command || '') : ''}">
                <input id="mcp-args" placeholder="Аргументы (через пробел)" value="${isEdit ? escapeHtml((existing.args || []).join(' ')) : ''}">
            </div>
            <div id="mcp-http-fields" style="display:${!isStdio ? 'block' : 'none'}">
                <input id="mcp-url" placeholder="URL (например, http://localhost:3000/mcp)" value="${isEdit ? escapeHtml(existing.url || '') : ''}">
                <input id="mcp-headers" placeholder="Заголовки (JSON, например {&#34;Authorization&#34;: &#34;Bearer …&#34;})" value="${isEdit ? escapeHtml(JSON.stringify(existing.headers || {})) : '{}'}">
            </div>
            <div id="mcp-env-fields">
                <div class="mcp-env-label">Переменные окружения</div>
                <div id="mcp-env-list"></div>
                <button type="button" onclick="mcpAddEnvRow()">＋ Переменная</button>
            </div>
            <label><input type="checkbox" id="mcp-enabled" ${existing ? (existing.enabled !== false ? 'checked' : '') : 'checked'}> Включён</label>
            <label><input type="checkbox" id="mcp-auto-approve" ${existing ? (existing.auto_approve ? 'checked' : '') : ''}> Авто-одобрение вызовов инструментов</label>
        </div>
        <div class="mcp-form-actions">
            <button class="test-btn primary" onclick="mcpSubmit(${isEdit ? `"${escapeHtml(existing.id)}"` : 'null'})">${isEdit ? 'Сохранить' : 'Добавить'}</button>
            <button type="button" onclick="document.getElementById('mcp-add-form').style.display='none'">Отмена</button>
        </div>
    `;
    form.querySelectorAll('input[name="mcp-transport"]').forEach(r => {
        r.addEventListener('change', () => {
            const std = form.querySelector('input[name="mcp-transport"]:checked').value === 'stdio';
            document.getElementById('mcp-stdio-fields').style.display = std ? 'block' : 'none';
            document.getElementById('mcp-http-fields').style.display = std ? 'none' : 'block';
        });
    });
    if (existing?.env) {
        Object.entries(existing.env).forEach(([k, v]) => {
            mcpAddEnvRow(k, String(v));
        });
    }
    form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function mcpAddEnvRow(key = '', val = '') {
    const list = document.getElementById('mcp-env-list');
    if (!list) return;
    const row = document.createElement('div');
    row.className = 'mcp-env-row';
    row.innerHTML = `<input placeholder="KEY" class="mcp-env-key" value="${escapeHtml(key)}"><input placeholder="значение" type="password" class="mcp-env-val" value="${escapeHtml(val)}">`;
    list.appendChild(row);
}

async function mcpSubmit(existingId) {
    const form = document.getElementById('mcp-add-form');
    if (!form) return;
    const transport = form.querySelector('input[name="mcp-transport"]:checked').value;
    const id = document.getElementById('mcp-id').value.trim();
    const name = document.getElementById('mcp-name').value.trim();
    if (!id || !name) { alert('Заполните имя и ID сервера.'); return; }
    const body = {
        id,
        name,
        transport,
        enabled: document.getElementById('mcp-enabled').checked,
        auto_approve: document.getElementById('mcp-auto-approve').checked,
    };
    if (transport === 'stdio') {
        body.command = document.getElementById('mcp-command').value.trim();
        body.args = document.getElementById('mcp-args').value.split(' ').filter(Boolean);
        if (!body.command) { alert('Укажите команду STDIO-сервера.'); return; }
    } else {
        body.url = document.getElementById('mcp-url').value.trim();
        if (!body.url) { alert('Укажите URL HTTP-сервера.'); return; }
        let headers = {};
        try { headers = JSON.parse(document.getElementById('mcp-headers').value || '{}'); } catch { /* ignore */ }
        body.headers = headers;
    }
    body.env = {};
    form.querySelectorAll('.mcp-env-row').forEach(row => {
        const k = row.querySelector('.mcp-env-key').value.trim();
        const v = row.querySelector('.mcp-env-val').value;
        if (k) body.env[k] = v;
    });
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/servers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert('Ошибка: ' + (err.error || resp.status));
            return;
        }
        if (existingId) {
            // Обновление: PUT текущие значения (env не передаётся — оставляем как есть)
            await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(existingId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        }
        form.style.display = 'none';
        flashStatus(existingId ? 'MCP-сервер обновлён' : 'MCP-сервер добавлен');
        renderMcpSettings();
    } catch (e) {
        alert('Ошибка сети: ' + e);
    }
}

// ===== RAG preset: one-click local knowledge-base MCP server =====
async function mcpInstallRagPreset() {
    flashStatus('Подключение RAG-сервера (база знаний)…');
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/presets/rag`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            alert('Ошибка: ' + (data.error || resp.status));
            return;
        }
        if (data.created) {
            flashStatus('RAG-сервер добавлен. Теперь проиндексируйте папку — см. инструмент index_folder в списке инструментов.');
        } else {
            flashStatus('RAG-сервер уже подключён.');
        }
        renderMcpSettings();
        // Auto-open the RAG card so the user can hit «Тест» and see its tools.
        setTimeout(() => { if (data.config) mcpTest('rag'); }, 400);
    } catch (e) {
        alert('Ошибка сети: ' + e);
    }
}

// ===== Хранилище: секция «MCP-серверы» =====
async function renderMcpStorage() {
    const list = document.getElementById('mcp-storage-list');
    if (!list) return;
    let servers = [];
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/servers`);
        servers = await resp.json();
        if (!Array.isArray(servers)) servers = [];
    } catch { servers = []; }
    list.innerHTML = '';
    if (!servers.length) {
        list.innerHTML = '<div class="mcp-empty">MCP-серверов нет</div>';
        return;
    }
    for (const s of servers) {
        const row = document.createElement('div');
        row.className = 'storage-item mcp-storage-item';
        row.dataset.key = 'mcp';
        row.dataset.id = escapeHtml(s.id);
        row.innerHTML = `
            <div class="si-icon">${svgIcon('plug')}</div>
            <div class="si-body">
                <div class="si-title">${escapeHtml(s.name || s.id)}</div>
                <div class="si-sub">${escapeHtml(s.transport)}${s.enabled ? '' : ' · выключен'}</div>
            </div>
            <div class="si-actions">
                <button data-mcp-act="toggle">${s.enabled ? 'Выключить' : 'Включить'}</button>
                <button data-mcp-act="edit">Изменить</button>
                <button data-mcp-act="delete" class="danger">Удалить</button>
            </div>
        `;
        list.appendChild(row);
    }
    // Привязываем действия
    list.querySelectorAll('.storage-item').forEach(row => {
        row.querySelectorAll('.si-actions button').forEach(btn => {
            btn.addEventListener('click', e => {
                e.stopPropagation();
                const id = row.dataset.id;
                const act = btn.dataset.mcpAct;
                if (act === 'toggle') mcpToggle(id, !row.querySelector('input')?.checked);
                else if (act === 'edit') { showPage('settings'); showSettingsPage('sec-mcp'); mcpEdit(id); }
                else if (act === 'delete') mcpDelete(id);
            });
        });
    });
}
