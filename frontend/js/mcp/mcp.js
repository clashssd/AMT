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
    // Кэшируем имена для тематических модалок (мcpTest/mcpDelete).
    window.__mcpServersCache = {};
    for (const s of servers) window.__mcpServersCache[s.id] = s;
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

// Показать результат теста MCP-сервера в тематической модалке (вместо нативного alert).
function showMcpToolsModal(name, tools, error) {
    const modal = document.getElementById('mcpToolsModal');
    if (!modal) return;
    const title = document.getElementById('mcpToolsTitle');
    const summary = document.getElementById('mcpToolsSummary');
    const list = document.getElementById('mcpToolsList');
    const close = document.getElementById('mcpToolsClose');
    if (title) title.textContent = 'MCP-сервер «' + name + '»';
    if (summary) {
        if (error) {
            summary.textContent = error;
            summary.style.color = 'var(--danger, #e06)';
        } else {
            summary.textContent = 'Подключено. Доступно инструментов: ' + (tools || []).length;
            summary.style.color = '';
        }
    }
    if (list) {
        list.innerHTML = '';
        if (!error && tools && tools.length) {
            for (const t of tools) {
                const item = document.createElement('div');
                item.className = 'mtl-item';
                item.innerHTML = '<b>' + escapeHtml(t.name || '') + '</b>' + (t.description ? '<span>' + escapeHtml(t.description) + '</span>' : '');
                list.appendChild(item);
            }
        } else if (!error) {
            list.innerHTML = '<div class="mtl-empty">Сервер не предоставляет инструментов</div>';
        }
    }
    if (close) close.onclick = () => modal.classList.add('hidden');
    modal.onclick = (e) => { if (e.target === modal) modal.classList.add('hidden'); };
    modal.classList.remove('hidden');
}

async function mcpTest(id) {
    flashStatus('Проверка подключения к «' + id + '»…');
    const cfg = mcpServerName(id);
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(id)}/test`, { method: 'POST' });
        const data = await resp.json();
        if (data.status === 'connected') {
            showMcpToolsModal(cfg || id, data.tools || [], null);
        } else {
            showMcpToolsModal(cfg || id, [], 'Ошибка: ' + (data.message || data.status || 'неизвестно'));
        }
    } catch (e) {
        showMcpToolsModal(cfg || id, [], 'Ошибка сети: ' + e);
    }
}

async function mcpDelete(id) {
    const ok = await amtConfirm({
        title: 'Удалить MCP-сервер?',
        text: '«' + id + '» будет удалён из реестра.',
        yesLabel: 'Удалить',
    });
    if (!ok) return;
    try {
        await fetch(`${API_BASE}/api/mcp/servers/${encodeURIComponent(id)}`, { method: 'DELETE' });
    } catch { /* ignore */ }
    flashStatus('MCP-сервер «' + id + '» удалён');
    renderMcpSettings();
    if (typeof renderMcpStorage === 'function' && document.getElementById('mcp-storage-list')) renderMcpStorage();
}

// Подсказка для заголовков модалок: имя сервера по id (если известно).
function mcpServerName(id) {
    const s = window.__mcpServersCache || null;
    if (s && s[id]) return s[id].name || id;
    return null;
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
    if (!id || !name) { flashStatus('Заполните имя и ID сервера.'); return; }
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
        if (!body.command) { flashStatus('Укажите команду STDIO-сервера.'); return; }
    } else {
        body.url = document.getElementById('mcp-url').value.trim();
        if (!body.url) { flashStatus('Укажите URL HTTP-сервера.'); return; }
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
            flashStatus('Ошибка: ' + (err.error || resp.status));
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
        flashStatus('Ошибка сети: ' + e);
    }
}

// ===== RAG preset: one-click local knowledge-base MCP server =====
async function mcpInstallRagPreset() {
    flashStatus('Подключение RAG-сервера (база знаний)…');
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/presets/rag`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            flashStatus('Ошибка: ' + (data.error || resp.status));
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
        flashStatus('Ошибка сети: ' + e);
    }
}

// ===== Media preset: one-click media-generation MCP server =====
async function mcpInstallMediaPreset() {
    flashStatus('Подключение медиа-сервера (картинки, видео, аудио, файлы)…');
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/presets/media`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            flashStatus('Ошибка: ' + (data.error || resp.status));
            return;
        }
        if (data.created) {
            flashStatus('Медиа-сервер добавлен. Инструменты generate_image / generate_video / generate_audio / generate_file теперь доступны (при включённом tool-calling).');
        } else {
            flashStatus('Медиа-сервер уже подключён.');
        }
        renderMcpSettings();
        setTimeout(() => { if (data.config) mcpTest('media'); }, 400);
    } catch (e) {
        flashStatus('Ошибка сети: ' + e);
    }
}

// ===== Writer preset: one-click file-generation MCP server =====
async function mcpInstallWriterPreset() {
    flashStatus('Подключение генератора файлов (тексты, Office, код, архивы, данные)…');
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/presets/writer`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            flashStatus('Ошибка: ' + (data.error || resp.status));
            return;
        }
        if (data.created) {
            flashStatus('Генератор файлов добавлен. Инструменты create_text / create_office / create_code / create_archive теперь доступны (при включённом tool-calling).');
        } else {
            flashStatus('Генератор файлов уже подключён.');
        }
        renderMcpSettings();
        setTimeout(() => { if (data.config) mcpTest('writer'); }, 400);
    } catch (e) {
        flashStatus('Ошибка сети: ' + e);
    }
}

// ===== Хран��лище: секция «MCP-серверы» =====
// ===== AMT Coding preset: advanced read-only diagnostics MCP server =====
async function mcpInstallAmtCodingPreset() {
    flashStatus('Подключение AMT Coding MCP (диагностика кодинг-проекта)…');
    try {
        const resp = await fetch(`${API_BASE}/api/mcp/presets/amt-coding`, { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            flashStatus('Ошибка: ' + (data.error || resp.status));
            return;
        }
        if (data.created) {
            flashStatus('AMT Coding MCP добавлен. Инструменты fs_read / fs_list / fs_search / git_status / git_diff / git_log / git_branch / run_tests / project_doctor доступны.');
        } else {
            flashStatus('AMT Coding MCP уже подключён.');
        }
        renderMcpSettings();
        setTimeout(() => { if (data.config) mcpTest('amt-coding'); }, 400);
    } catch (e) {
        flashStatus('Ошибка сети: ' + e);
    }
}

// ===== Writer generation form handlers =====
let _writerLastResult = null;

async function writerGenerate() {
    const family = document.getElementById('writerFamily').value;
    const title = document.getElementById('writerTitle').value.trim();
    const spec = document.getElementById('writerSpec').value.trim();
    const sourceFileInput = document.getElementById('writerSourceFile');
    const btn = document.getElementById('writerGenerateBtn');
    const resultDiv = document.getElementById('writerResult');
    const dlBtn = document.getElementById('writerResultBtn');

    if (!spec) {
        flashStatus('Укажите спецификацию или содержимое');
        return;
    }

    // Read source file if selected
    let sourceB64 = '';
    if (sourceFileInput.files && sourceFileInput.files[0]) {
        try {
            const buf = await sourceFileInput.files[0].arrayBuffer();
            sourceB64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
        } catch (e) {
            flashStatus('Ошибка чтения файла: ' + e);
            return;
        }
    }

    btn.disabled = true;
    btn.textContent = 'Генерация…';
    resultDiv.style.display = 'block';
    resultDiv.textContent = 'Генерация файла…';
    dlBtn.style.display = 'none';

    try {
        const body = { family, title, spec };
        if (sourceB64) body.source_b64 = sourceB64;

        const resp = await fetch(`${API_BASE}/api/writer/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            resultDiv.textContent = 'Ошибка: ' + (data.error || JSON.stringify(data));
            return;
        }

        _writerLastResult = data;
        resultDiv.innerHTML = `
            <div style="padding:8px 0">
                <b>Готово:</b> ${data.stored_name || data.artifact_id || 'unknown'}<br>
                <small>Family: ${data.family} · Size: ${data.bytes} bytes · Hash: ${(data.hash || '').substring(0, 16)}…</small>
                ${data.validation?.notes?.length ? `<br><small>Validation: ${data.validation.notes.join(', ')}</small>` : ''}
            </div>`;
        dlBtn.style.display = 'inline-block';
        flashStatus('Файл сгенерирован и готов к скачиванию');
    } catch (e) {
        resultDiv.textContent = 'Ошибка сети: ' + e;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Сгенерировать';
    }
}

function writerDownload() {
    if (!_writerLastResult || !_writerLastResult.stored_name) {
        flashStatus('Нет результата для скачивания');
        return;
    }
    const url = `${API_BASE}/api/filegen/download/${_writerLastResult.stored_name}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = _writerLastResult.stored_name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

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
