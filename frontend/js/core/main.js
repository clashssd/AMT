// ============================================================================
// AMT Chat — основной модуль фронтенда (vanilla JS, без фреймворков).
//
// Структура файла (секции с метками "// ===== ИМЯ ====="):
//   DOM                     — все getElementById / querySelector (кэш нод)
//   НАСТРОЙКИ / КОНСТАНТЫ   — storage-ключи, дефолты моделей, лимиты
//   State                   — текущий чат, агент, история
//   Chat storage            — persist в localStorage
//   Messages / Chat actions — отправка, рендер, стриминг через WS
//   Logs / Memory           — журнал, память ИИ
//   File Attachment         — прикрепление файлов
//   Model Test / Orchestrator — диагностика и оркестратор
//   [[GEN:...]] токены      — медиа прямо в чате
//   Инструменты (sandbox)   — picker, approve/deny, write_file/create_dir
//   Проекты                 — рабочая папка ИИ-инструментов
//   Ключи API               - мульти-ключи, round-robin
//   Event listeners (init)  — все addEventListener, вызывается при загрузке
//
// Публичная поверхность: функции в глобальной области видимости,
// инициализация на końcu файла (init()).
// ============================================================================

const API_BASE = window.location.origin;
const WS_BASE = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
const WS_URL = `${WS_BASE}${window.location.host}/ws/chat`;

const STORAGE_SETTINGS = 'amt_settings';
const STORAGE_CHATS = 'amt_chats';
const STORAGE_API_KEY = 'amt_api_key';
const STORAGE_CURRENT_CHAT = 'amt_current_chat';

// ===== DOM =====
const chatPage = document.getElementById('chatPage');
const settingsPage = document.getElementById('settingsPage');
const logsPage = document.getElementById('logsPage');
const homePage = document.getElementById('homePage');
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const newChatBtn = document.getElementById('newChatBtn');
const copyAllBtn = document.getElementById('copyAllBtn');
const clearBtn = document.getElementById('clearBtn');
const deleteBtn = document.getElementById('deleteBtn');
const tokenCounter = document.getElementById('tokenCounter');
const chatTitle = document.getElementById('chatTitle');
const navLinks = document.querySelectorAll('nav a[data-page]');
const chatsList = document.getElementById('chatsList');

const baseUrlInput = document.getElementById('baseUrl');
const apiKeyInput = document.getElementById('apiKey');
const modelInput = document.getElementById('model');
const systemPromptInput = document.getElementById('systemPrompt');
const temperatureInput = document.getElementById('temperature');
const tempValue = document.getElementById('tempValue');
const httpProxyInput = document.getElementById('httpProxy');
const httpsProxyInput = document.getElementById('httpsProxy');
const proxyTypeSelect = document.getElementById('proxyType');
const proxyUrlInput = document.getElementById('proxyUrl');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');
const testConnectionBtn = document.getElementById('testConnectionBtn');
const testResult = document.getElementById('testResult');
const togglePass = document.getElementById('togglePass');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const logViewer = document.getElementById('logViewer');
const refreshLogsBtn = document.getElementById('refreshLogsBtn');
const clearLogsBtn = document.getElementById('clearLogsBtn');
const dashTabs = document.getElementById('dashTabs');
const dashWrap = document.getElementById('dashWrap');
const dashStats = document.getElementById('dashStats');
const dashTable = document.getElementById('dashTable');
const dashEmpty = document.getElementById('dashEmpty');
const dashEvent = document.getElementById('dashEvent');
const dashFilterChips = document.getElementById('dashFilterChips');
const rawLogsWrap = document.getElementById('rawLogsWrap');
const structuredLogsWrap = document.getElementById('structuredLogsWrap');
const structuredLogsContainer = document.getElementById('structuredLogsContainer');
let logViewMode = 'dash';        // 'dash' | 'structured' | 'raw'
let dashFilter = 'all';
let dashData = null;             // {tasks, stats}
const wipeMemoryBtn = document.getElementById('wipeMemoryBtn');
const memoryResult = document.getElementById('memoryResult');
const fileInput = document.getElementById('fileInput');
const attachBtn = document.getElementById('attachBtn');
const composerToolsBtn = document.getElementById('composerToolsBtn');
const composerToolsPop = document.getElementById('composerToolsPop');

const attachmentArea = document.getElementById('attachmentArea');
const testModelsBtn = document.getElementById('testModelsBtn');
const modelsList = document.getElementById('modelsList');
const maxTokensInput = document.getElementById('maxTokens');
const contextWindowInput = document.getElementById('contextWindow');
const orchEnabled = document.getElementById('orchEnabled');
const orchAuto = document.getElementById('orchAuto');
const orchRoleDrift = document.getElementById('orchRoleDrift');
const orchKeepContext = document.getElementById('orchKeepContext');
const orchLogVerbosity = document.getElementById('orchLogVerbosity');
const orchAutoSave = document.getElementById('orchAutoSave');
const saveOrchBtn = document.getElementById('saveOrchBtn');
const orchHealthBtn = document.getElementById('orchHealthBtn');
const orchHealth = document.getElementById('orchHealth');
const autoTemp = document.getElementById('autoTemp');
const addGroupBtn = document.getElementById('addGroupBtn');
const chatGroupSelect = document.getElementById('chatGroupSelect');
const logFilterBtns = document.querySelectorAll('.filter-btn');
const chatKeySelect = document.getElementById('chatKeySelect');
const chatSearchInput = document.getElementById('chatSearchInput');
const chatSearchClose = document.getElementById('chatSearchClose');
const chatSearchResults = document.getElementById('chatSearchResults');
const newSessionBtn = document.getElementById('newSessionBtn');
const sessionModal = document.getElementById('sessionModal');
const sessionMode = document.getElementById('sessionMode');
const sessionName = document.getElementById('sessionName');
const sessionKey = document.getElementById('sessionKey');
const sessionAgent = document.getElementById('sessionAgent');
const sessionPrompt = document.getElementById('sessionPrompt');
const createSessionBtn = document.getElementById('createSessionBtn');
const cancelSessionBtn = document.getElementById('cancelSessionBtn');
const importAgentsBtn = document.getElementById('importAgentsBtn');
const importAgentsFile = document.getElementById('importAgentsFile');
const pinnedSection = document.getElementById('pinnedSection');
const pinnedList = document.getElementById('pinnedList');
const settingsSubnavLinks = document.querySelectorAll('.settings-subnav-links a');
// Агенты / скиллы / ключи
const agentName = document.getElementById('agentName');
const agentDesc = document.getElementById('agentDesc');
const agentPrompt = document.getElementById('agentPrompt');
const agentModel = document.getElementById('agentModel');
const agentTemp = document.getElementById('agentTemp');
const agentGroup = document.getElementById('agentGroup');
const addAgentBtn = document.getElementById('addAgentBtn');
const agentList = document.getElementById('agentList');
const skillName = document.getElementById('skillName');
const skillPrompt = document.getElementById('skillPrompt');
const skillGroup = document.getElementById('skillGroup');
const addSkillBtn = document.getElementById('addSkillBtn');
const skillList = document.getElementById('skillList');
const entityGroupFilter = document.getElementById('entityGroupFilter');
const keyLabel = document.getElementById('keyLabel');
const keyBaseUrl = document.getElementById('keyBaseUrl');
const keyApi = document.getElementById('keyApi');
const keyModel = document.getElementById('keyModel');
const keyTemp = document.getElementById('keyTemp');
const addKeyBtn = document.getElementById('addKeyBtn');
const keyRoundRobin = document.getElementById('keyRoundRobin');
const keyList = document.getElementById('keyList');
const chatAgentSelect = document.getElementById('chatAgentSelect');
// Мульти-селекты в шапке чата (агенты + ключи): кнопка + чекбокс-поповер
const chatAgentMsel = document.getElementById('chatAgentMsel');
const chatAgentMselBtn = document.getElementById('chatAgentMselBtn');
const chatAgentMselPop = document.getElementById('chatAgentMselPop');
const chatKeyMsel = document.getElementById('chatKeyMsel');
const chatKeyMselBtn = document.getElementById('chatKeyMselBtn');
const chatKeyMselPop = document.getElementById('chatKeyMselPop');
const chatPromptMsel = document.getElementById('chatPromptMsel');
const chatPromptMselBtn = document.getElementById('chatPromptMselBtn');
const chatPromptMselPop = document.getElementById('chatPromptMselPop');
const chatPromptCustom = document.getElementById('chatPromptCustom');
// Индикатор статуса локального бэкенда (в шапке чата + баннер)
const backendStatus = document.getElementById('backendStatus');
const backendStatusLabel = document.getElementById('backendStatusLabel');
const backendOfflineBanner = document.getElementById('backendOfflineBanner');
// Ядровые агенты (веб-агент + глубокий аналитик + без фильтров) — переключатели в композере
const webAgentToggle = document.getElementById('webAgentToggle');
const thinkerToggle = document.getElementById('thinkerToggle');
const jailbreakToggle = document.getElementById('jailbreakToggle');
const sysInteractionToggle = document.getElementById('sysInteractionToggle');
let coreWebActive = false;
let coreThinkerActive = false;
let coreJailbreakActive = false;
let sysInteractionActive = false;
/** Список активных ядровых агентов (для передачи в /api/chat и /api/media/generate). */
function activeCoreAgentList() {
    const list = [];
    if (coreWebActive) list.push('core_web');
    if (coreThinkerActive) list.push('core_thinker');
    if (coreJailbreakActive) list.push('core_jailbreak');
    return list;
}
// Личность (композиция)
const persName = document.getElementById('persName');
const persUseKey = document.getElementById('persUseKey');
const persKey = document.getElementById('persKey');
const persUseModel = document.getElementById('persUseModel');
const persModel = document.getElementById('persModel');
const persUseAgent = document.getElementById('persUseAgent');
const persAgentsList = document.getElementById('persAgentsList');
const persUseSkills = document.getElementById('persUseSkills');
const persSkillsList = document.getElementById('persSkillsList');
const persParallel = document.getElementById('persParallel');
const persPrompt = document.getElementById('persPrompt');
const persUseOrch = document.getElementById('persUseOrch');
const persOrch = document.getElementById('persOrch');
const persOrchCustom = document.getElementById('persOrchCustom');
const createPersonalityBtn = document.getElementById('createPersonalityBtn');
const previewPersonalityBtn = document.getElementById('previewPersonalityBtn');
const personalityPreview = document.getElementById('personalityPreview');
const chatModeSelect = document.getElementById('chatModeSelect');
const chatModePersonality = document.getElementById('chatModePersonality');
const startChatWithBtn = document.getElementById('startChatWithBtn');
const chatModeResult = document.getElementById('chatModeResult');
// Главная страница (создание чата)
const homeTypeSeg = document.getElementById('homeTypeSeg');
const homePersonalityBlock = document.getElementById('homePersonalityBlock');
const homeCustomBlock = document.getElementById('homeCustomBlock');
const homeAgentSel = document.getElementById('homeAgentSel');
const homeSkillsPicker = document.getElementById('homeSkillsPicker');
const homeOrchSel = document.getElementById('homeOrchSel');
const homeOrchRules = document.getElementById('homeOrchRules');
const homeKeySel = document.getElementById('homeKeySel');
const homeModelInput = document.getElementById('homeModelInput');
const homeBaseUrlInput = document.getElementById('homeBaseUrl');
const homeSystemPrompt = document.getElementById('homeSystemPrompt');
const homeCreateBtn = document.getElementById('homeCreateBtn');
const homeResetBtn = document.getElementById('homeResetBtn');
const homeQuickList = document.getElementById('homeQuickList');
const homeQuickGroup = document.getElementById('homeQuickGroup');
const homeScenarioAddBtn = document.getElementById('homeScenarioAddBtn');
const homeEntityModal = document.getElementById('homeEntityModal');
let homeChatType = 'plain';
let homeEntityKind = 'agent'; // для модалки «прописать»
// Хранилище
const storagePage = document.getElementById('storagePage');
const docsPage = document.getElementById('docsPage');

const storageStats = document.getElementById('storageStats');
const storageSections = document.getElementById('storageSections');
const storageRefreshBtn = document.getElementById('storageRefreshBtn');
const storageExportBtn = document.getElementById('storageExportBtn');

// State for attachments
let attachedFiles = [];
// Захват в момент отправки сообщения: чтобы processGenTokens/renderGenInChat
// могли передать приложенный файл из чата в /api/media/generate как ref_image_b64.
let _lastChatAttachments = [];
// Пути эндпоинтов медиа-фасада (из настроек). Пустые значения = дефолтный путь
// (решает media.py: _get_path/generate_media). Ключи совпадают с _get_path.
function buildPathsObj() {
    return {
        text_to_media: settings?.mediaPathText || '',
        image_to_media: settings?.mediaPathImage || '',
        text_image_to_media: settings?.mediaPathTextImage || '',
        voice: settings?.mediaPathVoice || '',
        video: settings?.mediaPathVideo || '',
    };
}
let agentsCache = [];
let skillsCache = [];
let currentAgentId = '';
let currentKeyId = '';       // явный ключ сессии ("" = активный)
let currentSession = null;   // активная сессия
// Мульти-выбор в шапке чата (помимо 3 core-тумблеров):
let selectedAgentIds = [];   // несколько агентов → core_agents
let selectedKeyIds = [];     // несколько ключей → первый как key_id, остальные через 429-ротацию

// ===== Группы чатов =====
const STORAGE_GROUPS = 'amt_groups';
let groups = []; // [{id, name}]
let activeLogFilter = 'all';

async function loadGroups() {
    groups = await SecureStore.get(STORAGE_GROUPS, []);
}
async function saveGroups() {
    await SecureStore.set(STORAGE_GROUPS, groups);
}
function createGroup(name) {
    const g = { id: Date.now().toString(36), name: name || 'Новая группа' };
    groups.push(g);
    return g;
}
function deleteGroup(id) {
    groups = groups.filter(g => g.id !== id);
    // Чаты из этой группы → без группы
    chats.forEach(c => { if (c.groupId === id) c.groupId = null; });
}
function getGroupName(id) {
    const g = groups.find(x => x.id === id);
    return g ? g.name : 'Без группы';
}

// ===== State =====
let settings = {
    base_url: '',
    model: '',
    system_prompt: '',
    temperature: 0.7
};
let chats = [];
let currentChatId = null;
let isStreaming = false;
let currentWs = null;
let currentStreamingEl = null;
let currentFullText = '';

// ===== Chat storage (зашифрованно) =====
async function loadChats() {
    chats = await SecureStore.get(STORAGE_CHATS, []);
}

async function saveChats() {
    await SecureStore.set(STORAGE_CHATS, chats);
}

async function saveCurrentChatId() {
    await SecureStore.set(STORAGE_CURRENT_CHAT, currentChatId || '');
}

async function loadCurrentChatId() {
    currentChatId = await SecureStore.get(STORAGE_CURRENT_CHAT, null);
}

function createNewChat(mode = 'general') {
    const chat = {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        title: mode === 'coding' ? 'Новый кодинг-чат' : 'Новый чат',
        messages: [],
        groupId: null,
        created_at: Date.now(),
        updated_at: Date.now(),
        chat_mode: mode,
        projectRoot: '',
        toolPolicy: [],
        syncToBackend: mode === 'coding' ? false : true
    };
    chats.unshift(chat);
    return chat;
}

function deleteChat(id) {
    chats = chats.filter(c => c.id !== id);
    if (currentChatId === id) {
        currentChatId = null;
    }
}

function getCurrentChat() {
    return chats.find(c => c.id === currentChatId);
}

function currentChatSurface() {
    return (document.querySelector('nav a.active[data-page]')?.dataset.page === 'code') ? 'code' : 'chat';
}

function chatMatchesSurface(chat, surface) {
    const chatMode = chat?.chat_mode || 'general';
    if (surface === 'code') return chatMode === 'coding';
    return chatMode !== 'coding';
}

async function renderChatsList() {
    if (!chatsList) return;
    chatsList.innerHTML = '';
    const surface = currentChatSurface();

    // Сгруппировать: сначала чаты без группы, потом по группам
    const visibleChats = chats.filter(c => chatMatchesSurface(c, surface));
    const ungrouped = visibleChats.filter(c => !c.groupId);
    if (ungrouped.length > 0) {
        const label = document.createElement('div');
        label.className = 'chats-ungrouped-label';
        label.textContent = 'Без группы';
        chatsList.appendChild(label);
        ungrouped.forEach(chat => chatsList.appendChild(renderChatItem(chat)));
    }

    groups.forEach(group => {
        const groupChats = visibleChats.filter(c => c.groupId === group.id);
        if (groupChats.length === 0) return;
        const header = document.createElement('div');
        header.className = 'chat-group-header';
        header.innerHTML = `
            <span class="group-name">
                <button class="group-collapse" data-group="${group.id}" title="Свернуть">▼</button>
                ${escapeHtml(group.name)}
            </span>
            <button class="group-delete" data-group="${group.id}" title="Удалить группу">✕</button>
        `;
        chatsList.appendChild(header);
        groupChats.forEach(chat => {
            const item = renderChatItem(chat);
            item.dataset.group = group.id;
            chatsList.appendChild(item);
        });
    });

    // События на кнопки групп
    chatsList.querySelectorAll('.group-delete').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!(await amtConfirm({ text: 'Удалить группу? Чаты останутся, но без группы.' }))) return;
            deleteGroup(btn.dataset.group);
            saveGroups().then(saveChats).then(() => renderChatsList());
        });
    });
    chatsList.querySelectorAll('.group-collapse').forEach(btn => {
        btn.addEventListener('click', () => {
            const gid = btn.dataset.group;
            const items = chatsList.querySelectorAll(`[data-group="${gid}"]`);
            const hidden = items[0] && items[0].style.display === 'none';
            items.forEach(it => it.style.display = hidden ? '' : 'none');
            btn.textContent = hidden ? '▼' : '▶';
        });
    });
}

function renderChatItem(chat) {
    const item = document.createElement('div');
    item.className = 'chat-item' + (chat.id === currentChatId ? ' active' : '');
    item.dataset.chatId = chat.id;
    // Цветной бейдж: буква/иконка + палитра по хэшу названия
    const letter = (chat.title || '?').trim().charAt(0).toUpperCase() || '?';
    const colors = ['c1','c2','c3','c4','c5','c6'];
    const h = Array.from(chat.title || '').reduce((a, ch) => (a + ch.charCodeAt(0)) % 997, 0);
    const color = colors[h % colors.length];
    const sub = chat.groupId ? (groups.find(g => g.id === chat.groupId)?.name || '') : '';
    item.innerHTML = `
        <span class="chat-item-badge ${color}">${escapeHtml(letter)}</span>
        <span class="chat-item-text">
            <span class="chat-item-title">${escapeHtml(chat.title)}</span>
            <span class="chat-item-sub">${chat.messages?.length || 0} сообщ. ${sub ? '· ' + escapeHtml(sub) : ''}</span>
        </span>
        <button class="chat-item-delete" data-chat-id="${chat.id}" title="Удалить чат">✕</button>
    `;
    item.addEventListener('click', e => {
        if (e.target.classList.contains('chat-item-delete')) {
            e.stopPropagation();
            deleteChat(chat.id);
            saveChats().then(saveCurrentChatId).then(() => {
                renderChatsList();
                if (chats.length === 0) startNewChat();
            });
            return;
        }
        openChat(chat);
    });
    item.addEventListener('contextmenu', e => onChatItemContextMenu(e, chat));
    return item;
}

// ===== Группа текущего чата (select в шапке) =====
function renderGroupSelect(chat) {
    if (!chatGroupSelect) return;
    chat = chat || getCurrentChat();
    chatGroupSelect.innerHTML = '';
    const none = document.createElement('option');
    none.value = '';
    none.textContent = 'Без группы';
    chatGroupSelect.appendChild(none);
    groups.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.name;
        chatGroupSelect.appendChild(opt);
    });
    chatGroupSelect.value = (chat && chat.groupId) ? chat.groupId : '';
}

function moveChatToGroup(groupId) {
    const chat = getCurrentChat();
    if (!chat) return;
    chat.groupId = groupId || null;
    saveChats().then(renderChatsList);
}

function renameCurrentChat() {
    if (currentChatId) openChatMetaModal(currentChatId);
}

// ===== Контекстное меню чатов (ПКМ) =====
let ctxMenuEl = null;
function hideCtxMenu() {
    if (ctxMenuEl) ctxMenuEl.classList.add('hidden');
}
function showCtxMenu(x, y, items) {
    if (!ctxMenuEl) ctxMenuEl = document.getElementById('ctxMenu');
    if (!ctxMenuEl) return;
    ctxMenuEl.innerHTML = '';
    items.forEach(it => {
        if (it.sub) {
            const label = document.createElement('div');
            label.className = 'ctx-group-label';
            label.textContent = it.label;
            ctxMenuEl.appendChild(label);
            const sub = document.createElement('div');
            sub.className = 'ctx-sub';
            it.sub.forEach(s => sub.appendChild(makeCtxItem(s, s.action)));
            ctxMenuEl.appendChild(sub);
        } else {
            ctxMenuEl.appendChild(makeCtxItem(it, it.action));
        }
    });
    ctxMenuEl.classList.remove('hidden');
    const rect = ctxMenuEl.getBoundingClientRect();
    const px = Math.min(x, window.innerWidth - rect.width - 8);
    const py = Math.min(y, window.innerHeight - rect.height - 8);
    ctxMenuEl.style.left = px + 'px';
    ctxMenuEl.style.top = py + 'px';
}
function makeCtxItem(it, action) {
    const b = document.createElement('button');
    b.className = 'ctx-item' + (it.danger ? ' danger' : '');
    b.innerHTML = `<span class="ctx-icon">${it.icon || ''}</span><span>${escapeHtml(it.label)}</span>`;
    b.addEventListener('click', () => { hideCtxMenu(); action && action(); });
    return b;
}
function chatContextItems(chat) {
    const groupItems = groups.map(g => ({ label: g.name, action: () => moveSpecificChatToGroup(chat.id, g.id) }));
    groupItems.push({ label: 'Без группы', action: () => moveSpecificChatToGroup(chat.id, null) });
    return [
        { icon: '✎', label: 'Переименовать', action: () => renameChatById(chat.id) },
        { icon: '📁', label: 'В группу', sub: groupItems },
        { icon: '↗', label: 'Открыть', action: () => openChat(chat) },
        { icon: '✕', label: 'Удалить чат', danger: true, action: () => deleteChatById(chat.id) },
    ];
}
function onChatItemContextMenu(e, chat) {
    e.preventDefault();
    showCtxMenu(e.clientX, e.clientY, chatContextItems(chat));
}
function renameChatById(id) {
    openChatMetaModal(id);
}
function moveSpecificChatToGroup(chatId, groupId) {
    // через модальное окно, но сразу применяем выбранную группу
    const c = chats.find(x => x.id === chatId);
    if (!c) return;
    c.groupId = groupId || null;
    saveChats().then(renderChatsList);
    if (chatId === currentChatId) renderGroupSelect(c);
}
// Модальное окно «переименовать + группа»
let chatMetaModal = null;
let chatMetaTargetId = null;
function openChatMetaModal(chatId) {
    let c = chats.find(x => x.id === chatId);
    // Если чата нет в локальном массиве (хранилище с сервера) — ищем в localChats
    if (!c && typeof loadStorage !== 'undefined') {
        // loadStorage хранит localChats в замыкании; используем fallback
    }
    if (!c) return;
    if (!chatMetaModal) chatMetaModal = document.getElementById('chatMetaModal');
    if (!chatMetaModal) { renameChatById_fallback(chatId); return; }
    chatMetaTargetId = chatId;
    chatMetaModal.querySelector('#chatMetaTitle').textContent = 'Настройка чата';
    chatMetaModal.querySelector('#chatMetaName').value = c.title;
    const gs = chatMetaModal.querySelector('#chatMetaGroup');
    gs.innerHTML = '<option value="">Без группы</option>';
    groups.forEach(g => {
        const o = document.createElement('option');
        o.value = g.id; o.textContent = g.name;
        gs.appendChild(o);
    });
    gs.value = c.groupId || '';
    chatMetaModal.classList.remove('hidden');
}
function saveChatMeta() {
    const c = chats.find(x => x.id === chatMetaTargetId);
    if (!c) return;
    const nameEl = chatMetaModal.querySelector('#chatMetaName');
    const groupEl = chatMetaModal.querySelector('#chatMetaGroup');
    c.title = nameEl.value.trim() || 'Новый чат';
    c.groupId = groupEl.value || null;
    saveChats().then(renderChatsList);
    if (chatMetaTargetId === currentChatId) {
        if (chatTitle) chatTitle.value = c.title;
        renderGroupSelect(c);
    }
    chatMetaModal.classList.add('hidden');
}
async function renameChatById_fallback(id) {
    const c = chats.find(x => x.id === id);
    if (!c) return;
    const name = await amtPrompt('Название чата:', c.title);
    if (name !== null) { c.title = name.trim() || 'Новый чат'; saveChats().then(renderChatsList); if (id === currentChatId && chatTitle) chatTitle.value = c.title; }
}
async function deleteChatById(id) {
    if (!(await amtConfirm('Удалить чат?'))) return;
    deleteChat(id);
    saveChats().then(saveCurrentChatId).then(() => {
        renderChatsList();
        if (chats.length === 0) startNewChat();
    });
}

function promptNewGroup() {
    openGroupModal();
}
// Модалка создания группы
async function openGroupModal() {
    const m = document.getElementById('groupModal');
    if (!m) { const n = await amtPrompt('Имя группы:'); if (n && n.trim()) { const g = createGroup(n.trim()); saveGroups().then(() => { renderChatsList(); renderGroupSelect(); }); } return; }
    document.getElementById('groupName').value = '';
    m.classList.remove('hidden');
    document.getElementById('groupName').focus();
}
function closeGroupModal() {
    const m = document.getElementById('groupModal');
    if (m) m.classList.add('hidden');
}
function saveGroupModal() {
    const name = document.getElementById('groupName').value.trim();
    if (!name) { flashStatus('Введите название группы'); return; }
    const g = createGroup(name);
    saveGroups().then(() => {
        renderChatsList();
        renderGroupSelect();
    });
    closeGroupModal();
    flashStatus('Группа «' + name + '» создана');
}

async function renderMessages(chat) {
    chatMessages.innerHTML = '';
    if (!chat.messages.length) {
        chatMessages.innerHTML = `
            <div class="welcome-screen" id="welcomeScreen">
                <div class="welcome-icon">AMT</div>
                <h3>Чем я могу помочь?</h3>
                <p>Задай вопрос — я отвечу на основе подключённой модели.</p>
            </div>
        `;
        renderPinned();
        updateTokenCounter();
        return;
    }
    chat.messages.forEach((m, idx) => {
        let el;
        if (m.role === 'user') {
            el = appendMessageEl(m.content, 'user');
            // Рендерим карточки файлов в пуле пользователя
            if (m.files && m.files.length) {
                const contentEl = el.querySelector('.message-content');
                m.files.forEach(fname => {
                    const card = document.createElement('div');
                    card.className = 'msg-file-card';
                    card.innerHTML = `<div class="msg-file-card-icon"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M8 4h8l4 4v12a2 2 0 01-2 2H8a2 2 0 01-2-2V6a2 2 0 012-2z" fill="rgba(59,130,246,0.15)"/><path d="M16 4v4h4"/><path d="M10 13h4M10 17h4" stroke-linecap="round"/></svg></div><div class="msg-file-card-info"><span class="msg-file-card-name">${escapeHtml(fname)}</span></div>`;
                    // Клик — скачать/открыть файл
                    card.addEventListener('click', () => {
                        const a = document.createElement('a');
                        a.href = `${API_BASE}/api/files/${encodeURIComponent(fname)}`;
                        a.download = fname;
                        a.click();
                    });
                    contentEl.appendChild(card);
                });
            }
        } else {
            el = addBotPlaceholder();
            setBotContent(el, m.content);
        }
        attachPinButton(el, idx, m.pinned, m.role);
    });
    enhanceStreamCards(chatMessages);
    renderPinned();
    toggleComposerVisibility();
    updateTokenCounter();
}

// Превращает ссылки YouTube/Twitch в сообщениях в кликабельные карточки.
function enhanceStreamCards(root) {
    const hostOf = u => { try { return new URL(u).hostname; } catch (e) { return ''; } };
    const isStreamHost = h => /youtube|youtu\.be|twitch/.test(h);
    const CHANNEL_RE = /youtube\.com\/(?:c|channel|@)\//;
    const STREAM_RE = /(https?:\/\/(?:www\.)?(?:youtu\.be\/[A-Za-z0-9_-]+|youtube\.com\/(?:embed|shorts|live|c|channel|@)\/[A-Za-z0-9_-]+|youtube\.com\S*?\/\S*?v=[A-Za-z0-9_-]+|twitch\.tv\/[A-Za-z0-9_-]+))/g;
    // Любые http(s) ссылки в тексте (для веб-карточек)
    const WEB_URL_RE = /(https?:\/\/[^\s<>"']+)/g;
    const isMediaFile = u => /\.(mp4|webm|mov|m4v|mkv|mp3|wav|ogg|m4a|flac|aac|png|jpe?g|webp|gif)\?/i.test(u);
    root.querySelectorAll('.message-content').forEach(contentEl => {
        if (contentEl.querySelector('.stream-card')) return; // уже обработано
        const text = contentEl.textContent || '';
        const matches = text.match(STREAM_RE);
        // Собираем ВСЕ URL (и стрим, и веб)
        const webMatches = text.match(WEB_URL_RE) || [];
        if ((!matches || !matches.length) && webMatches.length === 0) return;
        // Работаем с .md-content div'ами (созданными renderMediaInText) или с текстовыми нодами
        const mdDivs = Array.from(contentEl.querySelectorAll('.md-content'));
        // Сохраняем медиа-элементы (video/audio/img/кнопки)
        const preserved = [];
        Array.from(contentEl.childNodes).forEach(node => {
            if (node.nodeType === Node.ELEMENT_NODE && !node.classList.contains('md-content')) {
                preserved.push(node);
            }
        });
        // Убираем md-content div'ы (пересоберём их с карточками)
        mdDivs.forEach(d => d.remove());
        // Чистим оставшийся контент (текстовые ноды)
        Array.from(contentEl.childNodes).forEach(n => { if (n.nodeType === Node.TEXT_NODE) contentEl.removeChild(n); });
        // Разбиваем полный текст на части вокруг стрим-URL'ов
        const fullText = text;
        let last = 0;
        const consumed = new Set();
        const textParts = [];
        // Сначала расставляем стрим-URL'ы
        (matches || []).forEach(u => {
            const pos = fullText.indexOf(u, last);
            if (pos === -1 || consumed.has(pos)) return;
            if (!isStreamHost(hostOf(u))) return;
            consumed.add(pos);
            textParts.push({ text: fullText.slice(last, pos), url: u, isStream: true });
            last = pos + u.length;
        });
        // Теперь расставляем оставшиеся веб-URL'ы (не покрытые стрим-карточками)
        webMatches.forEach(u => {
            // Пропускаем URL, уже покрытые стрим-карточкой
            const streamCovered = (matches || []).some(sm => u.startsWith(sm));
            if (streamCovered) return;
            if (consumed.has(u)) return;
            const pos = fullText.indexOf(u, last);
            if (pos === -1) return;
            // Проверяем, не является ли это медиа-файлом (уже рендерится как <video>/<img>)
            if (isMediaFile(u)) return;
            consumed.add(pos);
            textParts.push({ text: fullText.slice(last, pos), url: u, isStream: false });
            last = pos + u.length;
        });
        textParts.push({ text: fullText.slice(last) });
        // Пересобираем: для каждой части — md-content div (если есть текст) или карточка
        textParts.forEach(part => {
            if (part.text) {
                const div = document.createElement('div');
                div.className = 'md-content';
                div.innerHTML = markdownToHtml(part.text);
                contentEl.appendChild(div);
            }
            if (part.url) {
                const u = part.url;
                if (part.isStream) {
                    // Стрим-карточка (YouTube/Twitch)
                    const isChannel = CHANNEL_RE.test(u);
                    const isLive = /twitch\.tv/.test(u);
                    const card = document.createElement('div');
                    let badgeText = '▶';
                    let cardClass = 'stream-card';
                    if (isChannel) { cardClass += ' channel'; badgeText = '📺'; }
                    else if (isLive) { cardClass += ' live'; badgeText = 'LIVE'; }
                    card.className = cardClass;
                    card.dataset.url = u;
                    const nick = isChannel ? (u.split('/').pop() || '').replace(/^@/, '') : (u.replace(/^https?:\/\//, ''));
                    const title = isChannel ? 'Канал: ' + nick : (isLive ? 'Твитч-стрим' : 'YouTube');
                    const copyBtn = document.createElement('button');
                    copyBtn.className = 'stream-card-copy';
                    copyBtn.textContent = '⧉';
                    copyBtn.title = 'Копировать ссылку';
                    copyBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(u).then(() => {
                            copyBtn.textContent = '✓';
                            setTimeout(() => copyBtn.textContent = '⧉', 1500);
                        });
                    });
                    card.innerHTML = `<div class="stream-card-badge">${badgeText}</div><div class="stream-card-body"><div class="stream-card-title">${escapeHtml(title)}</div><div class="stream-card-host">${escapeHtml(nick)} · нажмите, чтобы открыть в плеере</div></div>`;
                    card.appendChild(copyBtn);
                    card.addEventListener('click', () => {
                        if (window.openMediaOverlay) {
                            if (isChannel) window.openMediaOverlay('stream', u, { channel: true, channelName: nick });
                            else window.openMediaOverlay('stream', u);
                        }
                    });
                    contentEl.appendChild(card);
                } else {
                    // Веб-карточка (Lordfilm, rule34, агрегаторы, обычные ссылки)
                    const card = document.createElement('div');
                    card.className = 'stream-card web-link';
                    card.dataset.url = u;
                    let host = hostOf(u);
                    let path = '';
                    try { const up = new URL(u); path = up.pathname + up.search; } catch (e) {}
                    const title = host || u;
                    const openBtn = document.createElement('button');
                    openBtn.className = 'stream-card-copy web-open-btn';
                    openBtn.textContent = '\u2197';
                    openBtn.title = 'Открыть в браузере';
                    openBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (window.api && window.api.openExternal) {
                            window.api.openExternal(u);
                        } else {
                            window.open(u, '_blank');
                        }
                    });
                    // Кнопка «▶ В плеере» — попытка открыть в iframe внутри плеера
                    // (часть сайтов позволяет встраивание; остальные покажут
                    // fallback-карточку с «Открыть в браузере» в самом плеере).
                    const playerBtn = document.createElement('button');
                    playerBtn.className = 'stream-card-copy web-player-btn';
                    playerBtn.textContent = '\u25B6';
                    playerBtn.title = 'Открыть в плеере (с фильтрами)';
                    playerBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (window.openMediaOverlay) window.openMediaOverlay('video', u);
                    });
                    // Кнопка «🌐 В браузере (режим)» — отдельное Electron-окно без
                    // X-Frame-Options (работает для ЛЮБЫХ сайтов).
                    let browserBtn = null;
                    if (window.api && window.api.openBrowserWindow) {
                        browserBtn = document.createElement('button');
                        browserBtn.className = 'stream-card-copy web-browser-btn';
                        browserBtn.textContent = '\uD83C\uDF10';
                        browserBtn.title = 'Открыть в режиме браузера (обходит X-Frame-Options)';
                        browserBtn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            window.api.openBrowserWindow(u).catch(() => {
                                if (window.api.openExternal) window.api.openExternal(u);
                            });
                        });
                    }
                    const copyBtn = document.createElement('button');
                    copyBtn.className = 'stream-card-copy';
                    copyBtn.textContent = '\u29C9';
                    copyBtn.title = 'Копировать ссылку';
                    copyBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        navigator.clipboard.writeText(u).then(() => {
                            copyBtn.textContent = '\u2713';
                            setTimeout(() => copyBtn.textContent = '\u29C9', 1500);
                        });
                    });
                    card.innerHTML = `<div class="stream-card-badge">\uD83D\uDD17</div><div class="stream-card-body"><div class="stream-card-title">${escapeHtml(title)}</div><div class="stream-card-host">${escapeHtml(host)}${path ? ' \u00B7 ' + escapeHtml(path.slice(0, 40)) : ''} \u00B7 \u25B6 плеер / \uD83C\uDF10 браузер / \u2197 внешний</div></div>`;
                    card.appendChild(copyBtn);
                    if (browserBtn) card.appendChild(browserBtn);
                    card.appendChild(playerBtn);
                    card.appendChild(openBtn);
                    // Клик по карточке = открыть в плеере (попытка iframe)
                    card.addEventListener('click', () => {
                        if (window.openMediaOverlay) window.openMediaOverlay('video', u);
                    });
                    contentEl.appendChild(card);
                }
            }
        });
        // Возвращаем медиа-элементы
        preserved.forEach(el => contentEl.appendChild(el));
    });
}

// Сделанный message-элемент (для рендера без сохранения в чат)
function appendMessageEl(text, role) {
    const div = document.createElement('div');
    div.className = 'message ' + role;
    div.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
    chatMessages.appendChild(div);
    return div;
}

// Кнопки действий на сообщении (внутри .message-content). Видны всегда,
// с текстовыми подписями и tooltip (title) при наведении.
function attachPinButton(msgEl, idx, isPinned, role) {
    if (!msgEl) return;
    if (!role) role = msgEl.classList.contains('user') ? 'user' : 'assistant';
    const contentEl = msgEl.querySelector('.message-content');
    if (!contentEl) return;

    // Контейнер действий (виден всегда, позиционируется в углу сообщения)
    let actions = contentEl.querySelector('.msg-actions');
    if (!actions) {
        actions = document.createElement('div');
        actions.className = 'msg-actions';
        contentEl.appendChild(actions);
    }

    const isUser = role === 'user';
    msgEl.__idx = idx; // чтобы кнопки всегда знали индекс (для копирования)
    const getMsg = () => { const c = getCurrentChat(); return c ? c.messages[msgEl.__idx] : null; };
    const doCopy = async () => {
        const m = getMsg();
        const txt = m ? m.content : '';
        try { await navigator.clipboard.writeText(txt); flashStatus('Скопировано'); }
        catch { try { document.execCommand('copy'); flashStatus('Скопировано'); } catch { flashStatus('Не удалось скопировать'); } }
    };
    const mkBtn = (cls, icon, title, onClick) => {
        let b = actions.querySelector('.' + cls);
        if (!b) {
            b = document.createElement('button');
            b.className = cls;
            b.innerHTML = `<span class="msg-act-label">${icon}</span>`;
            b.title = title;
            b.addEventListener('click', onClick);
            actions.appendChild(b);
        }
        return b;
    };

    // SVG-иконки (тонкие линии, акцент темы через currentColor)
    const svg = (inner) =>
        `<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
    const ICONS = {
        pin:   svg('<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.6.8 1 1.8 1.2 2.8h5.6c.2-1 .6-2 1.2-2.8A6 6 0 0 0 12 3z"/>'),
        edit:  svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>'),
        del:   svg('<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>'),
        regen: svg('<path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/>'),
        copy:  svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
    };
    if (isUser) {
        // Свой вопрос: Копировать / Закрепить / Изменить / Удалить
        mkBtn('msg-copy-btn', ICONS.copy, 'Скопировать это сообщение', (e) => { e.stopPropagation(); doCopy(); });
        const pinBtn = mkBtn('msg-pin-btn', ICONS.pin, 'Закрепить / открепить сообщение', (e) => { e.stopPropagation(); togglePinMessage(idx); });
        pinBtn.classList.toggle('pinned', !!isPinned);
        mkBtn('msg-edit-btn', ICONS.edit, 'Редактировать сообщение (текст и файлы)', (e) => { e.stopPropagation(); openMessageEdit(idx); });
        mkBtn('msg-delete-btn', ICONS.del, 'Удалить это сообщение', (e) => { e.stopPropagation(); deleteMessage(idx); });
    } else {
        // Ответ ИИ: Копировать / Перегенерировать / Удалить ответ
        mkBtn('msg-copy-btn', ICONS.copy, 'Скопировать ответ ИИ', (e) => { e.stopPropagation(); doCopy(); });
        mkBtn('msg-regen-btn', ICONS.regen, 'Получить новый ответ на последний вопрос', (e) => { e.stopPropagation(); regenerateMessage(idx); });
        mkBtn('msg-delete-btn', ICONS.del, 'Удалить ответ ИИ', (e) => { e.stopPropagation(); deleteMessage(idx); });
        // Убрать лишние кнопки user-ролей, если рендер переиспользует элемент
        const pin = actions.querySelector('.msg-pin-btn');
        if (pin) pin.remove();
        const ed = actions.querySelector('.msg-edit-btn');
        if (ed) ed.remove();
    }
}

// ===== Перегенерация ответа ИИ =====
async function regenerateMessage(idx) {
    const chat = getCurrentChat();
    if (!chat || !chat.messages[idx]) return;
    if (isStreaming) { flashStatus('Дождитесь окончания текущего ответа'); return; }
    // Находим последний вопрос пользователя до этого ответа
    let userIdx = -1;
    for (let i = idx - 1; i >= 0; i--) {
        if (chat.messages[i].role === 'user') { userIdx = i; break; }
    }
    if (userIdx < 0) { flashStatus('Не найдено сообщение для перегенерации'); return; }
    const userText = chat.messages[userIdx].content;
    const attachments = chat.messages[userIdx].files || [];
    // Отмечаем ответ «в работе»
    const target = chat.messages[idx];
    target.content = '';
    target.pending = true;
    renderMessages(chat);
    // Ключ ��ожет быть в поле настроек ЛИБО в хранилище — проверяем как в sendMessage
    let reply = '';
    isStreaming = true;
    setStatus('connecting');
    try {
        const historyForApi = chat.messages.slice(0, userIdx).map(m => ({ role: m.role, content: m.content }));
        try {
            reply = await streamViaWebSocket(userText, historyForApi, currentAgentId, attachments);
        } catch (e) {
            reply = await fallbackRest(userText, historyForApi, currentAgentId, attachments);
        }
    } catch (err) {
        reply = 'Не удалось получить ответ.';
    }
    isStreaming = false;
    setStatus('idle');
    target.content = (typeof reply === 'string' && reply && reply !== 'Ошибка соединения') ? reply : target.content;
    target.pending = false;
    renderMessages(chat);
    saveChats();
}

// ===== Удаление отдельного сообщения =====
async function deleteMessage(idx) {
    const chat = getCurrentChat();
    if (!chat || !chat.messages[idx]) return;
    const m = chat.messages[idx];
    const preview = (m.content || '').replace(/\s+/g, ' ').slice(0, 40);
    const ok = await amtConfirm({ title: 'Удалить сообщение?', text: `${preview ? '«' + preview + '»' : ''} — это действие нельзя отменить.`, yesLabel: 'Удалить' });
    if (!ok) return;
    chat.messages.splice(idx, 1);
    chat.updated_at = Date.now();
    // сброс закрепа, если сообщение было закреплено
    renderMessages(chat);
    saveChats().then(() => { renderMessages(chat); updateTokenCounter(); });
    flashStatus('Сообщение удалено');
}

// ===== Редактирование отправленного сообщения =====
let msgEditEl = null;
function openMessageEdit(idx) {
    const chat = getCurrentChat();
    if (!chat || !chat.messages[idx]) return;
    const m = chat.messages[idx];
    if (!msgEditEl) msgEditEl = document.getElementById('msgEditModal');
    if (!msgEditEl) return;
    const ta = msgEditEl.querySelector('.msg-edit-text');
    const fileArea = msgEditEl.querySelector('.msg-edit-files');
    const fileInput = msgEditEl.querySelector('.msg-edit-fileinput');
    ta.value = m.content || '';
    // показать уже прикрепленные файлы (если были)
    let editingFiles = [];
    if (fileArea) {
        fileArea.innerHTML = '';
        (m.files || []).forEach(f => {
            const d = document.createElement('div');
            d.className = 'attachment-item';
            d.textContent = f.name || f;
            fileArea.appendChild(d);
        });
    }
    if (fileInput) {
        fileInput.dataset.msgIdx = idx;
        fileInput.value = '';
    }
    const roleLabel = msgEditEl.querySelector('.msg-edit-role');
    if (roleLabel) roleLabel.textContent = m.role === 'user' ? 'Ваше сообщение' : 'Ответ ассистента';
    msgEditEl.classList.remove('hidden');
    msgEditEl.dataset.idx = idx;
    // обработчики: сохранить/отмена уже привязаны, но сбросим файлы
}
function closeMessageEdit() {
    if (msgEditEl) msgEditEl.classList.add('hidden');
}
function saveMessageEdit() {
    const idx = parseInt(msgEditEl.dataset.idx);
    const chat = getCurrentChat();
    if (!chat || !chat.messages[idx]) return;
    const ta = msgEditEl.querySelector('.msg-edit-text');
    chat.messages[idx].content = (ta?.value || '').trim();
    chat.updated_at = Date.now();
    saveChats().then(() => { renderMessages(chat); });
    closeMessageEdit();
    flashStatus('Сообщение изменено');
}
// Файл к редактируемому сообщению
function attachFileToEditingMessage(file) {
    const idx = parseInt(msgEditEl.dataset.idx);
    const chat = getCurrentChat();
    if (!chat || !chat.messages[idx]) return;
    if (!chat.messages[idx].files) chat.messages[idx].files = [];
    chat.messages[idx].files.push(file.name);
    const fileArea = msgEditEl.querySelector('.msg-edit-files');
    if (fileArea) {
        const d = document.createElement('div');
        d.className = 'attachment-item';
        d.textContent = file.name;
        fileArea.appendChild(d);
    }
}

async function updateCurrentChatMessage(content, role, files = null) {
    const chat = getCurrentChat();
    if (!chat) return;
    const msg = { role, content, timestamp: Date.now() };
    if (files && files.length) msg.files = files;
    chat.messages.push(msg);
    chat.updated_at = Date.now();
    if (role === 'user' && chat.title === 'Новый чат') {
        chat.title = content.length > 30 ? content.slice(0, 30) + '…' : content;
        chatTitle.value = chat.title;
    }
    await saveChats();
    renderChatsList();
    updateTokenCounter();
}

function updateTokenCounter() {
    const chat = getCurrentChat();
    if (!chat || !tokenCounter) return;
    const tokens = estimateTokensForMessages(chat.messages);
    tokenCounter.textContent = `${tokens.toLocaleString('ru')} токенов`;
}

// ===== Settings (безопасное хранение API Key) =====
async function fetchServerSettings() {
    try {
        const res = await fetch(`${API_BASE}/api/settings`);
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

async function saveSettingsToServer() {
    const s = buildSettingsFromInputs();
    try {
        await fetch(`${API_BASE}/api/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(toBackendSettings({ ...s, apiKey: apiKeyInput.value.trim() }))
        });
    } catch {
        // Бэкенд недоступен — локальные настройки уже сохранены
    }
}

async function loadSettings() {
    // 1. Серверные настройки (если доступны)
    const server = await fetchServerSettings();
    if (server) {
        settings = {
            ...settings,
            base_url: server.baseUrl || '',
            model: server.model || '',
            system_prompt: server.systemPrompt || '',
            temperature: server.temperature ?? 0.7,
            maxTokens: server.maxTokens ?? 4096,
            contextWindow: server.contextWindow ?? 128000,
            maxIterations: server.maxIterations ?? 0
        };
    }

    // 2. Локальные зашифрованные настройки (приоритет)
    const saved = await SecureStore.get(STORAGE_SETTINGS, {});
    settings = { ...settings, ...saved };

    const apiKey = await SecureStore.get(STORAGE_API_KEY, '');
    baseUrlInput.value = settings.base_url || '';
    apiKeyInput.value = apiKey;
    modelInput.value = settings.model || '';
    systemPromptInput.value = settings.system_prompt || '';
    temperatureInput.value = settings.temperature || 0.7;
    tempValue.textContent = settings.temperature || 0.7;
    maxTokensInput.value = settings.maxTokens || 4096;
    contextWindowInput.value = settings.contextWindow || 128000;
    httpProxyInput.value = settings.http_proxy || '';
    httpsProxyInput.value = settings.https_proxy || '';
    if (proxyTypeSelect) proxyTypeSelect.value = settings.proxyType || '';
    if (proxyUrlInput) proxyUrlInput.value = settings.proxyUrl || '';
    // Медиа-ключи
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ''; };
    setVal('imageKey', settings.imageKey); setVal('imageBaseUrl', settings.imageBaseUrl); setVal('imageModel', settings.imageModel);
    setVal('videoKey', settings.videoKey); setVal('videoBaseUrl', settings.videoBaseUrl); setVal('videoModel', settings.videoModel);
    setVal('audioKey', settings.audioKey); setVal('audioBaseUrl', settings.audioBaseUrl); setVal('audioModel', settings.audioModel); setVal('audioVoiceId', settings.audioVoiceId);
    setVal('mediaPathText', settings.mediaPathText); setVal('mediaPathImage', settings.mediaPathImage);
    setVal('mediaPathTextImage', settings.mediaPathTextImage); setVal('mediaPathVoice', settings.mediaPathVoice); setVal('mediaPathVideo', settings.mediaPathVideo);
    setVal('codingKey', settings.codingKey); setVal('codingBaseUrl', settings.codingBaseUrl); setVal('codingModel', settings.codingModel);
    const miEl = document.getElementById('maxIterations');
    if (miEl) miEl.value = String(settings.maxIterations || 5);
    setStatus('idle');
}

function buildSettingsFromInputs() {
    // Авто-температура: если включена — подбираем под тип текущего сообщения
    let temp = parseFloat(temperatureInput.value) || 0.7;
    if (autoTemp && autoTemp.checked) {
        temp = autoPickTemperature();
        temperatureInput.value = temp;
        if (tempValue) tempValue.textContent = temp;
    }
    return {
        base_url: baseUrlInput.value.trim(),
        model: modelInput.value.trim(),
        system_prompt: systemPromptInput.value.trim(),
        temperature: temp,
        maxTokens: parseInt(maxTokensInput.value) || 4096,
        contextWindow: parseInt(contextWindowInput.value) || 128000,
        topP: parseFloat(document.getElementById('topP')?.value) || 1,
        frequencyPenalty: parseFloat(document.getElementById('frequencyPenalty')?.value) || 0,
        stopSequences: document.getElementById('stopSequences')?.value.trim() || '',
        responseFormat: document.getElementById('responseFormat')?.value || 'text',
        http_proxy: httpProxyInput.value.trim(),
        https_proxy: httpsProxyInput.value.trim(),
        proxyType: proxyTypeSelect?.value || '',
        proxyUrl: proxyUrlInput?.value.trim() || '',
        timeout: parseInt(document.getElementById('timeout')?.value) || 120,
        retries: parseInt(document.getElementById('retries')?.value) || 4,
        // Медиа-ключи (пер-функциональные)
        imageKey: document.getElementById('imageKey')?.value.trim() || '',
        imageBaseUrl: document.getElementById('imageBaseUrl')?.value.trim() || '',
        imageModel: document.getElementById('imageModel')?.value.trim() || '',
        videoKey: document.getElementById('videoKey')?.value.trim() || '',
        videoBaseUrl: document.getElementById('videoBaseUrl')?.value.trim() || '',
        videoModel: document.getElementById('videoModel')?.value.trim() || '',
        audioKey: document.getElementById('audioKey')?.value.trim() || '',
        audioBaseUrl: document.getElementById('audioBaseUrl')?.value.trim() || '',
        audioModel: document.getElementById('audioModel')?.value.trim() || '',
        audioVoiceId: document.getElementById('audioVoiceId')?.value.trim() || '',
        sttModel: document.getElementById('sttModel')?.value.trim() || '',
        mediaPathText: document.getElementById('mediaPathText')?.value.trim() || '',
        mediaPathVideo: document.getElementById('mediaPathVideo')?.value.trim() || '',
        mediaPathImage: document.getElementById('mediaPathImage')?.value.trim() || '',
        mediaPathTextImage: document.getElementById('mediaPathTextImage')?.value.trim() || '',
        mediaPathVoice: document.getElementById('mediaPathVoice')?.value.trim() || '',
        codingKey: document.getElementById('codingKey')?.value.trim() || '',
        codingBaseUrl: document.getElementById('codingBaseUrl')?.value.trim() || '',
        codingModel: document.getElementById('codingModel')?.value.trim() || '',
        // Voice control
        sttProvider: document.querySelector('input[name="sttProvider"]:checked')?.value || 'local',
        sttBaseUrl: document.getElementById('cloudSttBaseUrl')?.value.trim() || '',
        sttModelNew: document.getElementById('cloudSttModel')?.value.trim() || '',
        ttsProvider: document.getElementById('ttsProvider')?.value || 'browser',
        ttsBaseUrl: document.getElementById('ttsBaseUrl')?.value.trim() || '',
        ttsModel: document.getElementById('ttsModel')?.value.trim() || '',
        ttsVoiceId: document.getElementById('ttsVoiceId')?.value.trim() || '',
        voskModelPath: document.getElementById('localSttModelPath')?.value.trim() || '',
        wakeWordString: document.getElementById('wakeWordInput')?.value.trim() || 'Астра',
        vadSilenceMs: parseInt(document.getElementById('vadSilenceSlider')?.value) || 2000,
        vadSensitivity: parseFloat(document.getElementById('vadSensitivitySlider')?.value) || 1.8,
        maxIterations: parseInt(document.getElementById('maxIterations')?.value) || 0
    };
}

// Авто-подбор температуры по характеру последнего пользовательского сообщения
function autoPickTemperature() {
    const chat = getCurrentChat();
    const lastUser = chat && chat.messages.filter(m => m.role === 'user').pop();
    const text = (lastUser ? lastUser.content : (messageInput.value || '')).toLowerCase();
    // Творчество → высокая (проверяем ПЕРВЫМ: «write a poem/стори» важнее «write»)
    if (/истори|сказк|поэма|сценарий|придумай|изобрет|книга|миф|фантаз|расскажи сказку|story|poem|novel|creative|invent|write a |напиши историю/.test(text)) {
        return 1.2;
    }
    // Задачи, требующие точности → низкая температура
    if (/код|создай|напиши код|python|javascript|typescript|функци|реш|уравн|докажи|формула|algorithm|implement|regex|json|sql|расчёт|рассчитай|fix a bug|исправь/.test(text)) {
        return 0.3;
    }
    // Факты / объяснения → средне-низкая
    if (/что|почему|объяс|рассказ|разъясни|explain|why|what|how|define|перевед/.test(text)) {
        return 0.5;
    }
    return 0.7; // по умолчанию
}

function toBackendSettings(s) {
    return {
        baseUrl: s.base_url || '',
        apiKey: s.apiKey || '',
        model: s.model || '',
        systemPrompt: s.system_prompt || '',
        temperature: s.temperature ?? 0.7,
        maxTokens: s.maxTokens || 4096,
        contextWindow: s.contextWindow || 128000,
        topP: s.topP ?? 1,
        frequencyPenalty: s.frequencyPenalty ?? 0,
        stopSequences: s.stopSequences || '',
        responseFormat: s.responseFormat || 'text',
        httpProxy: s.http_proxy || '',
        httpsProxy: s.https_proxy || '',
        proxyType: s.proxyType || '',
        proxyUrl: s.proxyUrl || '',
        timeout: s.timeout || 120,
        retries: s.retries ?? 4,
        imageKey: s.imageKey || '',
        imageBaseUrl: s.imageBaseUrl || '',
        imageModel: s.imageModel || '',
        videoKey: s.videoKey || '',
        videoBaseUrl: s.videoBaseUrl || '',
        videoModel: s.videoModel || '',
        audioKey: s.audioKey || '',
        audioBaseUrl: s.audioBaseUrl || '',
        audioModel: s.audioModel || '',
        audioVoiceId: s.audioVoiceId || '',
        mediaPathText: s.mediaPathText || '',
        mediaPathVideo: s.mediaPathVideo || '',
        mediaPathImage: s.mediaPathImage || '',
        mediaPathTextImage: s.mediaPathTextImage || '',
        mediaPathVoice: s.mediaPathVoice || '',
        codingKey: s.codingKey || '',
        codingBaseUrl: s.codingBaseUrl || '',
        codingModel: s.codingModel || '',
        // Voice control (non-secret, persisted in settings.json)
        stt_provider: s.sttProvider || 'local',
        stt_base_url: s.sttBaseUrl || '',
        stt_model: s.sttModelNew || '',
        tts_provider: s.ttsProvider || 'browser',
        tts_base_url: s.ttsBaseUrl || '',
        tts_model: s.ttsModel || '',
        tts_voice_id: s.ttsVoiceId || '',
        vosk_model_path: s.voskModelPath || '',
        wake_word_string: s.wakeWordString || 'Астра',
        vad_silence_ms: s.vadSilenceMs || 2000,
        vad_sensitivity: s.vadSensitivity || 1.8,
        maxIterations: s.maxIterations || 0
    };
}

async function saveSettings() {
    settings = buildSettingsFromInputs();
    await SecureStore.set(STORAGE_SETTINGS, settings);
    await SecureStore.set(STORAGE_API_KEY, apiKeyInput.value.trim());
    await saveSettingsToServer();
    setStatus('idle');
}

async function saveAll() {
    await saveChats();
    await saveSettings();
}

function setStatus(type) {
    if (!statusDot || !statusText) return;
    statusDot.className = 'status-dot';
    statusText.textContent = 'Готов';
    const hasKey = !!apiKeyInput.value.trim();
    if (type === 'idle' && !hasKey) {
        statusDot.classList.add('offline');
        statusText.textContent = 'Нет API Key';
    } else if (type === 'connecting') {
        statusDot.classList.add('connecting');
        statusText.textContent = 'Соединение...';
    } else if (type === 'connected') {
        statusDot.classList.add('connected');
        statusText.textContent = settings.model || 'Подключено';
    } else if (type === 'error') {
        statusDot.classList.add('offline');
        statusText.textContent = 'Ошибка';
    }
}

// ===== Navigation =====
function showPage(page) {
    navLinks.forEach(a => a.classList.toggle('active', a.dataset.page === page));
    homePage.classList.toggle('active', page === 'home');
    chatPage.classList.toggle('active', page === 'chat' || page === 'code');
    settingsPage.classList.toggle('active', page === 'settings');
    logsPage.classList.toggle('active', page === 'logs');
    if (storagePage) storagePage.classList.toggle('active', page === 'storage');
    if (docsPage) docsPage.classList.toggle('active', page === 'docs');
    const chatSurface = page === 'code' ? 'coding' : 'general';
    if (chatPage.dataset) chatPage.dataset.surface = chatSurface;
    if (page === 'home') fillHomePage();
    if (page === 'logs') loadLogs();
    if (page === 'storage') loadStorage();
    if (page === 'chat' || page === 'code') {
        toggleComposerVisibility();
        renderChatsList();
    }
    if (page === 'settings') showSettingsPage('sec-connect');
    if (page === 'docs') showDocsPage('docs-about');
}

// ===== Messages =====
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Нормальные SVG-иконки (вместо emoji) — линия в стиле сайта
function svgIcon(name) {
    const paths = {
        chat: '<path d="M4 5h16v10H8l-4 4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
        agent: '<circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 20c0-4 4-6 8-6s8 2 8 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        skill: '<path d="M12 3l7 4v10l-7 4-7-4V7z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M9 12l2 2 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
        key: '<circle cx="8" cy="8" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M11 11l7 7-2 2-1-1-2 2-2-2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
        session: '<rect x="4" y="6" width="16" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 10h16" stroke="currentColor" stroke-width="1.6"/>',
        memory: '<path d="M9 4h6v3H9zM8 17h8v3H8z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><rect x="6" y="6" width="12" height="12" rx="3" fill="none" stroke="currentColor" stroke-width="1.6"/>',
        file: '<path d="M7 3h7l4 4v14H7z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M14 3v4h4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
        scenario: '<path d="M12 3v6M5 12l4 4M19 12l-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/>',
        group: '<path d="M4 6h16M4 12h10M4 18h7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        folder: '<path d="M3 6h6l2 2h10v10H3z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
        tool: '<path d="M14 6l4 4-8 8-4-4zM14 6l-3-3-3 3M10 10l3 3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>',
        ext: '<path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
        theme: '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12 4a8 8 0 010 16M12 4v16" fill="none" stroke="currentColor" stroke-width="1.4"/>',
        video: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 8.5v7l6-3.5z" fill="currentColor"/>',
        stream: '<circle cx="12" cy="12" r="2.5" fill="currentColor"/><path d="M7.5 7.5a6 6 0 000 9M16.5 7.5a6 6 0 010 9M4.8 4.8a9 9 0 000 14.4M19.2 4.8a9 9 0 010 14.4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        search: '<circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M15.5 15.5L21 21" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        channel: '<rect x="3" y="6" width="18" height="13" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 3l4 3 4-3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
        sysinteraction: '<rect x="3" y="4" width="18" height="14" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 22h10M12 18v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M7 9h4M7 13h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        plug: '<path d="M9 3v6M15 3v6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M6 9h12v3a6 6 0 01-6 6 6 6 0 01-6-6z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 18v3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
        knowledge: '<ellipse cx="12" cy="5" rx="8" ry="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    };
    const inner = paths[name] || paths.chat;
    return `<svg class="ic" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">${inner}</svg>`;
}

function hideWelcome() {
    const welcome = document.getElementById('welcomeScreen');
    if (welcome) welcome.style.display = 'none';
}

function addUserMessage(text, save = true, files = null) {
    hideWelcome();
    const div = document.createElement('div');
    div.className = 'message user';
    div.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
    chatMessages.appendChild(div);
    scrollToBottom();
    if (save) updateCurrentChatMessage(text, 'user', files);
    // Кнопки действий должны появляться СРАЗУ (без ожидания релоада):
    // индекс = последняя запись в chat.messages (только что дописанное сообщение)
    const chat = getCurrentChat();
    if (chat) attachPinButton(div, chat.messages.length - 1, false, 'user');
}

function addBotPlaceholder() {
    hideWelcome();
    const div = document.createElement('div');
    div.className = 'message bot';
    div.innerHTML = `<div class="message-content typing"><span class="typing-indicator"><span></span><span></span><span></span></span></div>`;
    chatMessages.appendChild(div);
    scrollToBottom();
    return div;
}

function appendBotContent(el, chunk) {
    const contentEl = el.querySelector('.message-content');
    contentEl.classList.remove('typing');
    contentEl.classList.add('streaming');
    contentEl.textContent += chunk;
    scrollToBottomIfNear();
}

// Регулярка для URL медиа (видео/аудио/картинки) в тексте ИИ
const MEDIA_URL_RE = /(https?:\/\/[^\s<>"']+\.(?:mp4|webm|mov|m4v|mkv|mp3|wav|ogg|m4a|flac|aac|png|jpg|jpeg|webp|gif|bmp))(?=[\s<>"']|$)/gi;
// Markdown images: ![alt](url) — для скриншотов и встроенных картинок от бэкенда
const MD_IMG_RE = /!\[[^\]]*\]\((https?:\/\/[^)\s]+|\/[^)\s]+)\)/g;

// Простой markdown → HTML (без XSS: сначала экранируем HTML, потом применяем форматирование)
// Порядок ВАЖЕН: сначала блоки ```code```, потом inline `code`, потом bold/italic,
// потом headers, потом lists, потом links, и ТОЛЬКО ПОСЛЕДНИМ — line breaks.
// Иначе \n внутри <li>/<pre>/<h*> превращается в <br> и ломает вёрстку.
function markdownToHtml(text) {
    let s = escapeHtml(text || '');
    // 1) Code blocks ```...``` → <pre><code> (сначала, чтобы внутри не трогать inline)
    s = s.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    // 2) Inline `code` → <code>
    s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    // 3) Bold **text** → <strong>
    s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    // 4) Italic *text* → <em> (не после * и не внутри ** — уже обработано)
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    // 5) Headers
    s = s.replace(/^#### (.+)$/gm, '<h5>$1</h5>');
    s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    s = s.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    s = s.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    // 6) Blockquote > text → <blockquote>
    s = s.replace(/^(?:&gt;\s?)(.+)$/gm, '<blockquote>$1</blockquote>');
    s = s.replace(/(<blockquote>[\s\S]*?<\/blockquote>)(\n(?!<blockquote>)(.*))?/g, (m, bq, rest) => bq + (rest ? '\n' + rest : ''));
    // 7) Unordered lists: - item / * item / • item → <li>; группировать в <ul>
    s = s.replace(/^(?:[-*•]\s+)(.+)$/gm, '<li>$1</li>');
    s = s.replace(/(?:<li>[\s\S]*?<\/li>)(?:\n(?=<li>)[\s\S]*?<\/li>)*?/g, '<ul>$&</ul>'.replace('$&', '$&'));
    // Более надёжная группировка <li> в <ul>:
    s = s.replace(/(?:^|\n)(<li>[\s\S]*?<\/li>(?:\n<li>[\s\S]*?<\/li>)*)/g, (m, group) => '\n<ul>\n' + group + '\n</ul>');
    // 8) Ordered lists: 1. item / 2. item → <li>; группировать в <ol>
    s = s.replace(/^(?:\d+[.)]\s+)(.+)$/gm, '<oli>$1</oli>');
    // Группируем последовательности <oli> в <ol>
    s = s.replace(/(?:^|\n)(<oli>[\s\S]*?<\/oli>(?:\n<oli>[\s\S]*?<\/oli>)*)/g, (m, group) => '\n<ol>\n' + group.replace(/<oli>/g, '<li>').replace(/<\/oli>/g, '</li>') + '\n</ol>');
    // 9) Markdown links [text](url) → <a>
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    // 9b) Markdown images ![text](url) → <img>
    //     Это критично для [[SCREENSHOT:url]] — бэкенд заменяет токен на
    //     ![скриншот](/api/screenshots/<stored>) и фронтенд должен отрендерить
    //     как <img>, а не как текст «![скриншот](...)».
    s = s.replace(/!\[([^\]\n]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]+)\)/g, '<img src="$2" alt="$1" class="md-img" style="max-width:480px;border-radius:8px;margin:4px 0;">');
    // 10) Auto-link plain URLs (не внутри <pre>/<code>)
    s = s.replace(/(^|[\s])(https?:\/\/[^\s<>"']+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
    // 11) Line breaks — только ВНЕ block-элементов.
    //     Стратегия: временно заменяем \n внутри <pre>...<\/pre> на \x00,
    //     затем заменяем все \n на <br>, затем восстанавливаем \x00 → \n в <pre>.
    s = s.replace(/<pre>([\s\S]*?)<\/pre>/g, (m, code) => '<pre>' + code.replace(/\n/g, '\x00') + '</pre>');
    s = s.replace(/\n/g, '<br>');
    s = s.replace(/\x00/g, '\n');
    // 12) Чистим пустые <br> перед/после block-элементов
    s = s.replace(/<br>\s*(<h[2-5]|<ul|<ol|<pre|<blockquote|<li)/g, '$1');
    s = s.replace(/(<\/h[2-5]>|<\/ul>|<\/ol>|<\/pre>|<\/blockquote>|<\/li>)\s*<br>/g, '$1');
    // 13) Убираем лишние пустые <ul></ul>
    s = s.replace(/<ul>\s*<\/ul>/g, '');
    return s;
}

function renderMediaInText(container, text) {
    // Разбиваем текст по медиа-URL и вставляем элементы
    const parts = text.split(MEDIA_URL_RE);
    container.innerHTML = '';
    for (let i = 0; i < parts.length; i++) {
        if (parts[i] === undefined || parts[i] === '') continue;
        const lower = parts[i].toLowerCase();
        if (lower.endsWith('.mp4') || lower.endsWith('.webm') || lower.endsWith('.mov') ||
            lower.endsWith('.m4v') || lower.endsWith('.mkv') ||
            lower.endsWith('.mp3') || lower.endsWith('.wav') || lower.endsWith('.ogg') ||
            lower.endsWith('.m4a') || lower.endsWith('.flac') || lower.endsWith('.aac') ||
            lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg') ||
            lower.endsWith('.webp') || lower.endsWith('.gif') || lower.endsWith('.bmp')) {
            const isVideo = /\.(mp4|webm|mov|m4v|mkv)/.test(lower);
            const isAudio = /\.(mp3|wav|ogg|m4a|flac|aac)/.test(lower);
            const frag = document.createDocumentFragment();
            if (isVideo) {
                const v = document.createElement('video');
                v.src = parts[i];
                v.controls = true;
                v.className = 'gen-inline-video';
                v.addEventListener('click', () => { if (window.openMediaOverlay) window.openMediaOverlay('video', parts[i]); });
                frag.appendChild(v);
                addMediaOpenBtn(frag, '⛶ Смотреть в плеере', () => { if (window.openMediaOverlay) window.openMediaOverlay('video', parts[i]); });
            } else if (isAudio) {
                const a = document.createElement('audio');
                a.src = parts[i];
                a.controls = true;
                a.className = 'gen-inline-audio';
                frag.appendChild(a);
                addMediaOpenBtn(frag, '▶ Прослушать', () => { if (window.openMediaOverlay) window.openMediaOverlay('audio', parts[i]); });
            } else {
                const img = document.createElement('img');
                img.src = parts[i];
                img.className = 'gen-inline-img';
                img.addEventListener('click', () => { if (window.openMediaOverlay) window.openMediaOverlay('image', parts[i]); });
                frag.appendChild(img);
                addMediaOpenBtn(frag, '🔍 Открыть', () => { if (window.openMediaOverlay) window.openMediaOverlay('image', parts[i]); });
            }
            container.appendChild(frag);
        } else {
            // Рендерим markdown (bold, italic, code, lists, links, images)
            const div = document.createElement('div');
            div.className = 'md-content';
            div.innerHTML = markdownToHtml(parts[i]);
            // Клик по markdown-картинке (скриншот) → открыть в плеере
            div.querySelectorAll('img.md-img').forEach(imgEl => {
                imgEl.style.cursor = 'pointer';
                imgEl.addEventListener('click', () => {
                    if (window.openMediaOverlay && imgEl.src) window.openMediaOverlay('image', imgEl.src);
                });
            });
            container.appendChild(div);
        }
    }
}

function setBotContent(el, text) {
    const contentEl = el.querySelector('.message-content');
    contentEl.classList.remove('typing', 'streaming');
    renderMediaInText(contentEl, text);
    // Превращаем YouTube/Twitch ссылки в кликабельные карточки
    enhanceStreamCards(el);
    // Подтягиваем к низу ТОЛЬКО если пользователь уже внизу — иначе не рвём его
    // прокрутку вверх (чтобы можно было параллельно листать чат во время генерации).
    scrollToBottomIfNear();
}

function setBotError(el, text) {
    const contentEl = el.querySelector('.message-content');
    el.classList.add('error');
    contentEl.classList.remove('typing', 'streaming');
    contentEl.textContent = text;
    scrollToBottomIfNear();
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Авто-скролл только если пользователь не прокрутил вверх.
// При стриминге не фиксируем прокрутку: если user скроллнул выше bottom,
// не подтягиваем обратно.
function isNearBottom() {
    const el = chatMessages;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 60;
}
function scrollToBottomIfNear() {
    if (isNearBottom()) scrollToBottom();
}

function copyAllMessages() {
    const chat = getCurrentChat();
    if (!chat || !chat.messages.length) return;
    const lines = [];
    chat.messages.forEach(m => lines.push(`${m.role === 'user' ? 'Вы' : 'AMT'}: ${m.content}`));
    navigator.clipboard.writeText(lines.join('\n\n'));
    flashStatus('Скопировано');
}

function flashStatus(text) {
    statusText.textContent = text;
    setTimeout(() => setStatus('idle'), 1500);
}

// ===== TOAST NOTIFICATIONS =====
let toastContainer = null;
function getToastContainer() {
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container';
        toastContainer.setAttribute('role', 'region');
        toastContainer.setAttribute('aria-live', 'polite');
        toastContainer.setAttribute('aria-label', 'Уведомления');
        document.body.appendChild(toastContainer);
    }
    return toastContainer;
}

function showToast(icon, title, body, duration = 4000) {
    const c = getToastContainer();
    const t = document.createElement('div');
    t.className = 'toast';
    t.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <div>
            <div class="toast-title">${title}</div>
            ${body ? `<div class="toast-body">${body}</div>` : ''}
        </div>
    `;
    c.appendChild(t);
    setTimeout(() => {
        t.classList.add('fade-out');
        setTimeout(() => t.remove(), 300);
    }, duration);
}

// Show toast when window actions happen (SYS_WINDOW_*_DONE events)
function showWindowToast(tag, detail) {
    const kv = {};
    (detail || '').split(' ').forEach(kvPair => {
        const i = kvPair.indexOf('=');
        if (i > 0) kv[kvPair.slice(0, i)] = kvPair.slice(i + 1);
    });
    if (tag === 'SYS_WINDOW_FOCUS_DONE') {
        const ok = kv.status === 'ok';
        showToast(ok ? '🖥️' : '⚠️', ok ? `Окно приведено: ${kv.app || ''}` : 'Не удалось сфокусировать окно',
            ok ? '' : (kv.error || '').slice(0, 100));
    } else if (tag === 'SYS_WINDOW_SEND_KEYS_DONE') {
        const ok = kv.status === 'ok';
        showToast(ok ? '⌨️' : '⚠️', ok ? `Текст введён в: ${kv.app || 'окно'}` : 'Не удалось ввести текст',
            ok ? (kv.text || '').slice(0, 60) : (kv.error || '').slice(0, 100));
    } else if (tag === 'SYS_WINDOW_CLICK_DONE') {
        const ok = kv.status === 'ok';
        showToast(ok ? '🖱️' : '⚠️', ok ? `Клик: ${kv.x}, ${kv.y}` : 'Клик не выполнен',
            kv.app ? kv.app : '');
    } else if (tag === 'SYS_WINDOW_SCREENSHOT_DONE') {
        const ok = kv.status === 'ok';
        showToast(ok ? '📸' : '⚠️', ok ? `Скриншот: ${kv.app || 'экран'}` : 'Скриншот не удался',
            ok ? (kv.path || '').slice(0, 80) : (kv.error || '').slice(0, 100));
    }
}

async function clearHistory() {
    if (!(await amtConfirm({ text: 'Очистить текущий чат? Это действие нельзя отменить.', yesLabel: 'Очистить' }))) return;
    const chat = getCurrentChat();
    if (chat) {
        chat.messages = [];
        chat.title = 'Новый чат';
        chat.updated_at = Date.now();
        await saveChats();
    }
    chatTitle.value = 'Новый чат';
    chatMessages.innerHTML = `
        <div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon">AMT</div>
            <h3>Чем я могу помочь?</h3>
            <p>Задай вопрос — я отвечу на основе подключённой модели.</p>
        </div>
    `;
    updateTokenCounter();
    renderChatsList();
    setStatus('idle');
}

function deleteCurrentChat() {
    if (!currentChatId) return;
    deleteChat(currentChatId);
    saveChats().then(() => {
        saveCurrentChatId();
        renderChatsList();
        startNewChat();
    });
}

async function startNewChat() {
    const surface = currentChatSurface();
    const chat = createNewChat(surface === 'coding' ? 'coding' : 'general');
    currentChatId = chat.id;
    chatTitle.value = chat.title;
    renderGroupSelect();
    await saveChats();
    await saveCurrentChatId();
    // Рендерим пустой новый чат (без очистки старых!)
    chatMessages.innerHTML = `
        <div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon">AMT</div>
            <h3>Чем я могу помочь?</h3>
            <p>Задай вопрос — я отвечу на основе подключённой модели.</p>
        </div>
    `;
    pinnedSection?.classList.add('hidden');
    renderChatsList();
    updateTokenCounter();
    toggleComposerVisibility();
    setStatus('idle');
}

async function openChat(chat) {
    currentChatId = chat.id;
    chatTitle.value = chat.title;
    renderGroupSelect(chat);
    await saveCurrentChatId();
    renderMessages(chat);
    renderChatsList();
    setStatus('idle');
    showPage('chat');
}

// ===== Chat actions =====
async function uploadAttachments() {
    const results = [];
    for (const item of attachedFiles) {
        try {
            const b64 = await readFileAsBase64(item.file);
            const res = await fetch(`${API_BASE}/api/files/upload`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: item.name, content: b64, mime_type: item.type || '' }),
            });
            const data = await res.json();
            if (data.status === 'ok') {
                results.push({ path: data.path, filename: item.name, mime_type: item.type || '' });
            }
        } catch { /* пропускаем при ошибке */ }
    }
    // Освобождаем objectURL для картинок
    attachedFiles.forEach(f => { if (f.thumb) URL.revokeObjectURL(f.thumb); });
    return results;
}


async function sendMessage() {
    const rawText = messageInput.value.trim();
    const hasFiles = attachedFiles.length > 0;
    if ((!rawText && !hasFiles) || isStreaming) return;

    messageInput.value = '';
    adjustTextareaHeight();
    hideWelcome();

    // ПРОВЕРЯЕМ SLASH-КОМАНДЫ
    let finalText = rawText;
    let commands = [];
    
    if (rawText.startsWith('/')) {
        const parsed = window.AMTCommands.parseCommands(rawText);
        commands = parsed.commands;
        finalText = parsed.text;
        
        // Навигационные и help-команды выполняются на фронтенде, НЕ отправляются в API
        const navCmds = commands.filter(c => c.id && c.id.startsWith('nav_'));
        const helpCmds = commands.filter(c => c.id === 'help');
        
        if (navCmds.length > 0) {
            for (const nc of navCmds) {
                const target = nc.id.replace('nav_', ''); // nav_home → home
                if (window.showPage) window.showPage(target);
            }
        }
        
        if (helpCmds.length > 0) {
            if (window.AMTHelp) {
                window.AMTHelp.show();
            } else {
                // Fallback: AMTHelp ещё не инициализирован — показываем alert
                alert('Список команд: /nav_home, /nav_chat, /nav_settings, /nav_docs, /nav_storage, /nav_logs, /rag, /agent, /orchestrator, /jailbreak, /web_agent, /system, /memory, /gen, /help');
            }
        }
        
        // Удаляем nav и help из списка команд для отправки
        commands = commands.filter(c => !c.id.startsWith('nav_') && c.id !== 'help');

        // Кодинг-команды выполняются локально на странице «Код» и не отправляются в API
        const codingCmds = commands.filter(c => c.id && c.id.startsWith('code'));
        for (const cc of codingCmds) {
            if (window.AMTCommands.executeCodingCommand) {
                await window.AMTCommands.executeCodingCommand(cc.id, cc.args ? Object.values(cc.args).flat() : [], rawText);
            }
        }
        commands = commands.filter(c => !(c.id && c.id.startsWith('code')));

        // Если были ТОЛЬКО nav/help/coding без текста — не отправляем запрос
        if (commands.length === 0 && !finalText) {
            messageInput.value = '';
            adjustTextareaHeight();
            return;
        }
        
        // Если остались только feature-команды без текста — используем описание
        if (!finalText && commands.length > 0) {
            finalText = 'Выполни команду: ' + commands.map(c => '/' + c.id).join(' + ');
        }
        
        // Если /gen file и MCP Writer доступен — показываем выбор (базовая модель vs MCP)
        const genCmd = commands.find(c => c.id === 'gen' && c.args && c.args.type === 'file');
        if (genCmd && window.AMTFileGenChoice) {
            const mcpAvailable = await isMcpWriterAvailable();
            if (mcpAvailable) {
                const choice = await window.AMTFileGenChoice.show();
                if (choice === null) return; // отмена — прерываем отправку
                // Передаём выбор в команду: mcp → writer, base → create_office
                if (choice === 'mcp') {
                    genCmd.args.mode = 'mcp';
                } else {
                    genCmd.args.mode = 'base';
                }
            }
        }
    }
    
    // Если есть файлы — они уже видны как карточки в attachment-area.
    let attachmentsPayload = [];
    if (hasFiles) {
        // Если текст пустой, показываем в пуле кратку�� подпись о файлах
        if (!finalText) {
            finalText = attachedFiles.map(f => f.name).join(', ');
        }
        renderAttachments(); // очистим после отправки
    }

    // Добавляем метаданные команд в сообщение (для отображения)
    const userMsgContent = commands.length > 0 
        ? `[Команды: ${commands.map(c => '/' + c.id).join(' + ')}]\n${finalText}`
        : finalText;
    
    addUserMessage(userMsgContent, true, hasFiles ? attachedFiles.map(f => f.name) : null);

    const chat = getCurrentChat();
    const historyForApi = chat.messages.slice(0, -1).map(m => ({ role: m.role, content: m.content }));

    // Ключ может быть в поле настроек ЛИБО в многоключевом хранилище (keys.json)
    if (!apiKeyInput.value.trim() && !(await hasUsableKey())) {
        const el = addBotPlaceholder();
        setBotError(el, 'Нет API Key. Заполните поле на вкладке «Настройки» или добавьте ключ в «Хранилище» (раздел Ключи).');
        setStatus('error');
        attachedFiles = [];
        return;
    }

    // Загружаем файлы на бэкенд (если е��ть)
    if (hasFiles) {
        attachmentsPayload = await uploadAttachments();
    }

    // Запоминаем приложенные к ЭТОМУ сообщению файлы, чтобы токены [[GEN:...]]
    // могли передать файл в генерацию медиа (ref_image_b64).
    _lastChatAttachments = hasFiles ? attachedFiles.slice() : [];

    isStreaming = true;
    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    setStatus('connecting');

    let assistantText = '';
    try {
        // Передаём команды в WebSocket
        assistantText = await streamViaWebSocket(
            finalText, 
            historyForApi, 
            currentAgentId, 
            attachmentsPayload,
            commands  // Новый параметр: список команд
        );
        setStatus('connected');
    } catch (e) {
        assistantText = await fallbackRest(
            finalText, 
            historyForApi, 
            currentAgentId, 
            attachmentsPayload,
            commands
        );
        setStatus('idle');
    }

    if (assistantText && assistantText !== 'Ошибка соединения') {
        updateCurrentChatMessage(assistantText, 'assistant');
        // Генерация медиа/файлов прямо в чате (токены [[GEN:...]])
        await processGenTokens(assistantText);
    }

    // Кнопки действий на живых элементах (чтобы не ждать релоада):
    // последнее сообщение — ответ ИИ, предыдущее — наш вопрос.
    {
        const c2 = getCurrentChat();
        if (c2) {
            const els = chatMessages.querySelectorAll('.message');
            const lastEl = els[els.length - 1];
            const prevEl = els[els.length - 2];
            if (lastEl) attachPinButton(lastEl, c2.messages.length - 1, false, 'assistant');
            if (prevEl) attachPinButton(prevEl, c2.messages.length - 2, false, 'user');
        }
    }

    isStreaming = false;
    sendBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    attachedFiles = [];
}

function stopStreaming() {
    if (currentWs) {
        currentWs.close();
        currentWs = null;
    }
    if (currentStreamingEl && currentFullText) {
        setBotContent(currentStreamingEl, currentFullText);
        updateCurrentChatMessage(currentFullText, 'assistant');
    }
    currentStreamingEl = null;
    currentFullText = '';
    isStreaming = false;
    sendBtn.classList.remove('hidden');
    stopBtn.classList.add('hidden');
    setStatus('idle');
}

async function streamViaWebSocket(message, history, agentId = '', attachments = [], commands = []) {
    return new Promise((resolve, reject) => {
        const el = addBotPlaceholder();
        currentStreamingEl = el;
        currentFullText = '';
        currentWs = new WebSocket(WS_URL);

        currentWs.onopen = () => {
            const payload = {
                message,
                history: history,
                settings: toBackendSettings({ ...buildSettingsFromInputs(), apiKey: (apiKeyInput ? apiKeyInput.value : '').trim() }),
                agent_id: agentId,
                key_id: currentKeyId,
                commands: commands,  // Передаём список команд
                chat_mode: getCurrentChat()?.chat_mode || 'general',
                project_root: getCurrentChat()?.projectRoot || '',
                tool_policy: getCurrentChat()?.toolPolicy || []
            };
            // Ядровые агенты + мульти-выбор агентов в шапке чата → core_agents
            const coreList = agentMselCurrent();
            if (coreList.length) payload.core_agents = coreList;
            // Мульти-выбор ключей: полный набор для ротации (первый уже в key_id)
            if (selectedKeyIds.length) payload.key_ids = selectedKeyIds.slice();
            if (currentSystemPromptOverride || (currentSession && currentSession.systemPromptOverride)) {
                payload.systemPromptOverride = currentSystemPromptOverride || currentSession.systemPromptOverride;
            }
            payload.sysinteraction = sysInteractionActive;
            if (attachments && attachments.length) {
                payload.attachments = attachments;
            }
            currentWs.send(JSON.stringify(payload));
        };

        currentWs.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === 'chunk') {
                currentFullText += data.content;
                appendBotContent(el, data.content);
            } else if (data.type === 'done') {
                const contentEl = el.querySelector('.message-content');
                contentEl.classList.remove('streaming');
                // Скриншоты: Electron-браузер делает capturePage() для каждого [[SCREENSHOT:url]]
                // в тексте, шлёт PNG на /api/screenshots/bridge, бэкенд кладёт в очередь.
                // Фронтенд сам не знает, какие URL были — бэкенд их уже заменил на
                // реальные ![скриншот](/api/screenshots/<stored>). Но если в тексте
                // остались сырые [[SCREENSHOT:url]] (бэкенд не успел обработать),
                // фронтенд запускает Electron-скриншот в фоне и обновляет карточку.
                (async () => {
                    const shotRe = /\[\[SCREENSHOT:(https?:\/\/[^\s\]]+)\]\]/g;
                    let shotMatch;
                    const shotPromises = [];
                    while ((shotMatch = shotRe.exec(currentFullText)) !== null) {
                        const url = shotMatch[1];
                        if (window.api && window.api.screenshot) {
                            shotPromises.push(
                                window.api.screenshot(url).then(async r => {
                                    if (r && r.ok && r.b64) {
                                        // Бэкенд уже сохранил PNG; обновляем text на реальный URL
                                        const stored = await fetch(`${API_BASE}/api/screenshots/bridge`, {
                                            method: 'POST',
                                            headers: {'Content-Type': 'application/json'},
                                            body: JSON.stringify({ url, b64: r.b64 }),
                                        }).then(x => x.json()).catch(() => null);
                                        if (stored && stored.stored) {
                                            currentFullText = currentFullText.replace(
                                                shotMatch[0],
                                                `\n![скриншот](${API_BASE + stored.url})\n`
                                            );
                                        }
                                    }
                                })
                            );
                        }
                    }
                    if (shotPromises.length) await Promise.allSettled(shotPromises);
                })().then(() => {
                    // Перерисовываем с медиа-URL (видео/фото/аудио)
                    renderMediaInText(contentEl, currentFullText);
                    // Превращаем YouTube/Twitch ссылки в кликабельные карточки
                    enhanceStreamCards(el);
                    currentWs.close();
                    currentWs = null;
                    currentStreamingEl = null;
                    // Обновляем счётчик токенов реальными данными
                    if (data.usage && data.usage.total_tokens) {
                        tokenCounter.textContent = `${data.usage.total_tokens.toLocaleString('ru')} токенов`;
                    }
                    resolve(currentFullText);
                });
            } else if (data.type === 'error') {
                currentWs.close();
                currentWs = null;
                currentStreamingEl = null;
                setBotError(el, data.content || 'Ошибка бэкенда.');
                reject(new Error(data.content));
            } else if (data.type === 'tool_call_start') {
                // Карточка вызова инструмента: появляется в чате до результатов
                const card = document.createElement('div');
                card.className = 'tool-call-card running';
                card.dataset.tool = data.tool || 'tool';
                card.dataset.callId = data.callId || '';
                card.innerHTML = `<span class="tool-icon">🔧</span> ${escapeHtml(data.tool || 'tool')}… <span class="tool-spinner" aria-hidden="true"></span>`;
                const contentEl = el.querySelector('.message-content');
                if (contentEl) contentEl.appendChild(card);
                scrollToBottomIfNear();
            } else if (data.type === 'tool_approval_request') {
                showCodingApproval(data);
            } else if (data.type === 'tool_call_result') {
                // Результат инструмента: ищем running-карточку с таким tool и обновляем её
                const contentEl = el.querySelector('.message-content');
                if (!contentEl) return;
                const card = contentEl.querySelector(`.tool-call-card[data-tool="${CSS.escape(data.tool || 'tool')}"].running`);
                if (card) {
                    const result = data.result;
                    const preview = typeof result === 'string' ? result.slice(0, 200) : JSON.stringify(result).slice(0, 200);
                    card.classList.remove('running');
                    card.classList.add('done');
                    card.innerHTML = `<span class="tool-icon">��</span> ${escapeHtml(data.tool || 'tool')} → ${escapeHtml(preview)}`;
                    // Для нативных медиа-инструментов (generate_image, generate_video, generate_audio, generate_file)
                    // результат — JSON {type:'media', kind, data} или {type:'error', error}. Рендерим медиа/файл inline,
                    // НЕ вызывая renderGenInChat (он сгенерирует заново).
                    if ((data.tool || '').startsWith('generate_')) {
                        let media = null;
                        try { media = typeof result === 'string' ? JSON.parse(result) : result; } catch { /* not json */ }
                        if (media && media.type === 'media') {
                            const mwrap = document.createElement('div');
                            mwrap.className = 'tool-result-media';
                            const kind = media.kind || '';
                            const dataStr = media.data || '';
                            if (kind === 'image' && dataStr) {
                                mwrap.innerHTML = `<img src="${dataStr}" alt="tool result" style="max-width:100%;border-radius:8px">`;
                            } else if (kind === 'audio' && dataStr) {
                                mwrap.innerHTML = `<audio controls src="${dataStr}" style="max-width:100%"></audio>`;
                            } else if (kind === 'video' && dataStr) {
                                mwrap.innerHTML = `<video controls src="${dataStr}" style="max-width:100%;border-radius:8px"></video>`;
                            } else if (kind === 'file' && dataStr) {
                                const a = document.createElement('a');
                                a.href = dataStr;
                                a.textContent = 'Скачать файл';
                                a.download = '';
                                a.target = '_blank';
                                mwrap.appendChild(a);
                            }
                            card.appendChild(mwrap);
                        } else if (media && media.type === 'error') {
                            card.innerHTML = `<span class="tool-icon">⚠️</span> ${escapeHtml(data.tool || 'tool')} → ${escapeHtml(media.error || 'ошибка')}`;
                        }
                    }
                    scrollToBottomIfNear();
                }
            }
        };

        currentWs.onerror = (err) => {
            currentWs = null;
            currentStreamingEl = null;
            // Не оставляем «висящий» пузырь с ошибкой: fallbackRest создаст
            // своё сообщение. Убираем этот placeholder, чтобы ошибка не
            // показывалась «сама по себе» после закрытия/релоада.
            if (el && el.parentNode) el.parentNode.removeChild(el);
            reject(err);
        };
    });
}

async function fallbackRest(message, history, agentId = '', attachments = [], commands = []) {
    const el = addBotPlaceholder();
    currentStreamingEl = el;
    currentFullText = '';
    try {
        const body = {
            message,
            history: history,
            settings: toBackendSettings({ ...buildSettingsFromInputs(), apiKey: (apiKeyInput ? apiKeyInput.value : '').trim() }),
            agent_id: agentId,
            key_id: currentKeyId,
            systemPromptOverride: currentSystemPromptOverride || (currentSession && currentSession.systemPromptOverride) || '',
            sysinteraction: sysInteractionActive,
            commands: commands,  // Добавляем команды
            chat_mode: getCurrentChat()?.chat_mode || 'general',
            project_root: getCurrentChat()?.projectRoot || '',
            tool_policy: getCurrentChat()?.toolPolicy || [],
        };
        // Ядровые агенты + мульти-выбор агентов в шапке чата → core_agents
        const coreList = agentMselCurrent();
        if (coreList.length) body.core_agents = coreList;
        // Мульти-выбор ключей: полный набор для ротации (первый уже в key_id)
        if (selectedKeyIds.length) body.key_ids = selectedKeyIds.slice();
        if (attachments && attachments.length) body.attachments = attachments;
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            const text = errData.detail || `HTTP ${res.status}`;
            setBotError(el, text);
            currentStreamingEl = null;
            return text;
        }
        const data = await res.json();
        const text = data.response || data.message || '';
        currentFullText = text;
        setBotContent(el, text);
        currentStreamingEl = null;
        return text;
    } catch (err) {
        currentStreamingEl = null;
        setBotError(el, 'Ошибка: не удалось получить ответ. Убедитесь, что сервер запущен (python backend/main.py).');
        // Перепроверить статус бэкенда — при недоступности покажем баннер
        if (typeof checkBackendStatus === 'function') checkBackendStatus();
        return 'Ошибка соединения';
    }
}

// ===== Закреплённые сообщения =====
function togglePinMessage(chatMsgIdx) {
    const chat = getCurrentChat();
    if (!chat || !chat.messages[chatMsgIdx]) return;
    chat.messages[chatMsgIdx].pinned = !chat.messages[chatMsgIdx].pinned;
    saveChats();
    // обновить иконки закрепа на соответствующих сообщениях
    const allMsgEls = chatMessages.querySelectorAll('.message');
    if (allMsgEls[chatMsgIdx]) {
        attachPinButton(allMsgEls[chatMsgIdx], chatMsgIdx, chat.messages[chatMsgIdx].pinned);
    }
    renderPinned();
}

function renderPinned() {
    if (!pinnedSection || !pinnedList) return;
    const chat = getCurrentChat();
    const pinned = chat ? chat.messages.filter(m => m.pinned) : [];
    if (pinned.length === 0) {
        pinnedSection.classList.add('hidden');
        return;
    }
    pinnedSection.classList.remove('hidden');
    pinnedList.innerHTML = '';
    pinned.forEach(m => {
        const div = document.createElement('div');
        div.className = 'pinned-item';
        const text = m.content.length > 160 ? m.content.slice(0, 160) + '…' : m.content;
        div.innerHTML = `
            <span class="pin-role">${m.role === 'user' ? 'Вы' : 'AMT'}</span>
            <span class="pin-text">${escapeHtml(text)}</span>
            <button class="pin-unpin" title="Открепить">✕</button>
        `;
        div.querySelector('.pin-unpin').addEventListener('click', () => {
            const idx = chat.messages.indexOf(m);
            if (idx >= 0) togglePinMessage(idx);
        });
        pinnedList.appendChild(div);
    });
}

// ===== Поиск по чатам (поле в центре шапки, постоянно видно) =====
function closeSearchResults() {
    if (chatSearchResults) chatSearchResults.classList.add('hidden');
    if (chatSearchInput) chatSearchInput.value = '';
}
async function doChatSearch() {
    const q = (chatSearchInput?.value || '').trim();
    if (!chatSearchResults) return;
    if (!q) { chatSearchResults.classList.add('hidden'); return; }
    chatSearchResults.classList.remove('hidden');
    chatSearchResults.innerHTML = '<div class="search-loading">Ищу...</div>';
    let matches = [];
    try {
        const res = await fetch(`${API_BASE}/api/chats/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        matches = data.matches || [];
    } catch {}
    if (!matches.length) {
        matches = chats.flatMap(c => c.messages
            .filter(m => (m.content || '').toLowerCase().includes(q.toLowerCase()))
            .map(m => ({ chatId: c.id, chatTitle: c.title, role: m.role, snippet: (m.content || '').slice(0, 120) })));
    }
    // доищем по заголовкам локально
    const localTitle = chats
        .filter(c => c.title.toLowerCase().includes(q.toLowerCase()) && !matches.some(m => m.chatId === c.id))
        .map(c => ({ chatId: c.id, chatTitle: c.title, role: 'title', snippet: c.title }));
    matches = [...matches, ...localTitle];
    chatSearchResults.innerHTML = '';
    if (!matches.length) {
        chatSearchResults.innerHTML = '<div class="search-empty">Ничего не найдено</div>';
        return;
    }
    matches.slice(0, 50).forEach(mt => {
        const div = document.createElement('div');
        div.className = 'search-result';
        const roleCls = mt.role === 'user' ? 'user' : (mt.role === 'title' ? 'title' : 'assistant');
        div.innerHTML = `
            <div class="sr-title">${escapeHtml(mt.chatTitle || mt.chatId || 'Чат')}
                <span class="sr-role ${roleCls}">${mt.role === 'title' ? 'заголовок' : (mt.role === 'user' ? 'вы' : 'AMT')}</span>
            </div>
            <div class="sr-snippet">${escapeHtml(mt.snippet || '')}</div>
        `;
        div.addEventListener('click', async () => {
            const chat = chats.find(c => c.id === mt.chatId);
            if (chat) { openChat(chat); closeSearchResults(); showPage('chat'); }
        });
        chatSearchResults.appendChild(div);
    });
}

// ===== Сессии =====
function openSessionModal() {
    if (!sessionModal) return;
    sessionModal.classList.remove('hidden');
}
function closeSessionModal() {
    if (!sessionModal) return;
    sessionModal.classList.add('hidden');
}
async function createSession() {
    const mode = sessionMode?.value || 'continue';
    const keyId = sessionKey?.value || '';
    const agentId = sessionAgent?.value || '';
    const promptOv = (sessionPrompt?.value || '').trim();
    const name = (sessionName?.value || '').trim();
    try {
        const res = await fetch(`${API_BASE}/api/sessions`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name, mode, key_id: keyId, agent_id: agentId,
                base_chat_id: currentChatId || '', systemPromptOverride: promptOv,
            })
        });
        const data = await res.json();
        if (data.status === 'created') {
            currentSession = data.session;
            currentKeyId = keyId;
            if (chatKeySelect) chatKeySelect.value = keyId;
            setChatAgent(agentId);
            flashStatus('Сессия создана');
        }
    } catch { /* бэкенд недоступен */ }
    closeSessionModal();
}

// ===== Импорт агентов/скиллов из файла =====
async function handleAgentsImport(files) {
    if (!files?.length) return;
    let imported = { skills: 0, agents: 0 };
    for (const file of files) {
        const text = await file.text();
        try {
            const res = await fetch(`${API_BASE}/api/import/batch-from-text`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ text }),
            });
            const d = await res.json();
            imported.skills += (d.imported_skills || 0);
            imported.agents += (d.imported_agents || 0);
        } catch {}
    }
    loadAgents();
    flashStatus(`Импорт: агентов ${imported.agents}, скиллов ${imported.skills}`);
}

// ===== Схлопывание кнопок шапки в одну =====
function toggleChatActions() {
    const extras = document.getElementById('chatHeaderExtras');
    if (!extras) return;
    const willExpand = !extras.classList.contains('expanded');
    extras.classList.toggle('expanded', willExpand);
    const btn = document.getElementById('chatMoreBtn');
    if (btn) {
        btn.setAttribute('aria-expanded', String(willExpand));
        btn.classList.toggle('open', willExpand);
    }
}

// ===== Logs =====
async function loadLogs() {
    if (logViewMode === 'raw') {
        loadRawLogs();
    } else {
        loadDashboard();
    }
}

async function loadRawLogs() {
    if (!logViewer) return;
    let lines = [];
    try {
        const res = await fetch(`${API_BASE}/api/logs`);
        const data = await res.json();
        lines = data.lines || [];
    } catch {
        logViewer.innerHTML = '<div class="log-empty">Бэкенд недоступен. Запустите: <code>cd backend &amp;&amp; python -m uvicorn main:app</code></div>';
        return;
    }
    renderLogs(lines);
}

async function loadDashboard() {
    let dash = null;
    try {
        const res = await fetch(`${API_BASE}/api/logs/dashboard`);
        dash = await res.json();
    } catch {
        if (dashTable) dashTable.innerHTML = '';
        if (dashEmpty) { dashEmpty.hidden = false; dashEmpty.textContent = 'Бэкенд недоступен'; }
        if (dashStats) dashStats.innerHTML = '';
        return;
    }
    dashData = dash;
    renderDashStats(dash.stats || {});
    renderDashTable(dash.tasks || []);
}

function renderDashStats(st) {
    if (!dashStats) return;
    const cards = [
        { label: 'Всего задач', value: st.total ?? 0 },
        { label: 'Ошибки', value: st.errors ?? 0, danger: st.errors > 0 },
        { label: 'Средн. задержка', value: (st.avg_latency_s ?? 0) + 'с' },
        { label: 'Запуски агентов', value: st.agent_runs ?? 0 },
        { label: 'Вызовов агентов', value: st.agent_call_count ?? 0 },
    ];
    dashStats.innerHTML = cards.map(c =>
        `<div class="dash-card${c.danger ? ' dash-card--danger' : ''}">
            <div class="dash-card-val">${escapeHtml(String(c.value))}</div>
            <div class="dash-card-label">${escapeHtml(c.label)}</div>
        </div>`).join('');
}

function _matchesDashFilter(t) {
    if (dashFilter === 'all') return true;
    if (dashFilter === 'orchestrator') return t.events.some(e => e.kind === 'orch');
    if (dashFilter === 'agents') return !!(t.agent || t.agent_name);
    if (dashFilter === 'skills') return (t.skills || []).length > 0;
    if (dashFilter === 'error') return t.status === 'failed';
    return true;
}

function renderDashTable(tasks) {
    if (!dashTable) return;
    const visible = tasks.filter(_matchesDashFilter).slice().reverse(); // новые сверху
    if (!visible.length) {
        dashTable.innerHTML = '';
        if (dashEmpty) { dashEmpty.hidden = false; dashEmpty.textContent = dashFilter === 'all' ? 'Нет задач за сегодня' : 'Нет задач по фильтру'; }
        return;
    }
    if (dashEmpty) dashEmpty.hidden = true;
    dashTable.innerHTML = visible.map((t, i) => {
        const badge = t.status === 'completed' ? 'COMPLETED' : (t.status === 'failed' ? 'FAILED' : 'RUNNING');
        const cls = t.status;
        // ВСЕ агенты (в т.ч. несколько core_agents) — из calls[]
        const calls = t.calls || [];
        const agentNames = calls.length
            ? calls.map(c => c.agent_name || c.agent).filter(Boolean)
            : ((t.agent_name || t.agent) ? [t.agent_name || t.agent] : []);
        const agentCell = agentNames.length
            ? agentNames.map(n => `<span class="agent-chip" title="${escapeHtml(n)}">${escapeHtml(n)}</span>`).join(' ')
            : '<span class="muted">—</span>';
        const skillCell = (t.skills && t.skills.length)
            ? t.skills.map(s => `<span class="skill-chip">${escapeHtml(s)}</span>`).join(' ') : '<span class="muted">—</span>';
        return `<tr class="task-row" data-idx="${i}" data-taskid="${escapeHtml(t.id)}">
            <td class="task-prompt" title="${escapeHtml(t.prompt)}">${escapeHtml(t.prompt || '—')}</td>
            <td><span class="status-badge st-${cls}">${badge}</span></td>
            <td class="task-meta"><div>${agentCell}</div><div class="task-skills">${skillCell}</div></td>
            <td>${t.duration_s > 0 ? t.duration_s.toFixed(1) + 'с' : '—'}</td>
            <td class="task-created">${escapeHtml(t.created || '')}</td>
            <td><button class="dash-view-btn" data-idx="${i}">View</button></td>
        </tr>`;
    }).join('');
    // сохраням видимые задачи в порядке, чтобы View-кнопка нашла свою
    window.__dashVisible = visible;
    dashTable.querySelectorAll('.dash-view-btn').forEach(btn => {
        btn.addEventListener('click', () => showTaskEvent(+btn.dataset.idx));
    });
}

// Рендер дерева вызовов задачи: корень (оркестратор) → агенты → скиллы
function _callTreeHtml(node, depth = 0) {
    const kindCls = node.kind === 'orchestrator' ? 'ct-orch' : (node.kind === 'agent' ? 'ct-agent' : (node.kind === 'skill' ? 'ct-skill' : 'ct-event'));
    const roleTag = (node.kind === 'agent' && node.role === 'primary') ? '<span class="ct-role">основной</span>' : '';
    const timeTag = node.time ? `<span class="ct-time">${escapeHtml(node.time)}</span>` : '';
    const detailTag = (node.kind === 'event' && node.detail) ? `<span class="ct-detail">${escapeHtml(node.detail)}</span>` : '';
    const kids = (node.children && node.children.length)
        ? `<div class="ct-children" style="margin-left:${depth > 0 ? 16 : 0}px">${node.children.map(ch => _callTreeHtml(ch, depth + 1)).join('')}</div>`
        : '';
    return `<div class="ct-node">
        <div class="ct-line">
            <span class="ct-dot ${kindCls}"></span>
            <span class="ct-label">${escapeHtml(node.label)}</span>
            ${roleTag}${timeTag}${detailTag}
        </div>
        ${kids}
    </div>`;
}
function renderCallTree(tree) {
    if (!tree) return '';
    const body = tree.children && tree.children.length ? tree.children.map(ch => _callTreeHtml(ch, 0)).join('') : '';
    return `<div class="ct-tree">
        <div class="ct-node">
            <div class="ct-line">
                <span class="ct-dot ct-orch"></span>
                <span class="ct-label">${escapeHtml(tree.label)}</span>
            </div>
            <div class="ct-children">${body || '<div class="ct-line ct-empty"><span class="ct-dot ct-event"></span><span class="ct-label muted">Нет вызовов агентов</span></div>'}</div>
        </div>
    </div>`;
}

/** Форматирует kv-строку "k=v  k2=v2" в читабельный "k: v · k2: v2" */
function fmtKvDetail(detail) {
    if (!detail) return '—';
    return detail
        .split(/\s{2,}/)
        .filter(Boolean)
        .map(kv => {
            const [k, ...rest] = kv.split('=');
            return rest.length ? `${k}: ${rest.join('=')}` : kv;
        })
        .join('  ·  ');
}

function showTaskEvent(idx) {
    const t = window.__dashVisible && window.__dashVisible[idx];
    if (!t || !dashEvent) return;

    // --- Prompt section ---
    const promptHtml = t.prompt
        ? `<div class="td-section"><div class="td-section-title">Prompt</div><div class="td-prompt">${escapeHtml(t.prompt)}</div></div>`
        : '';

    // --- Pipeline: build expandable steps from events ---
    const pipelineSteps = [];
    let stepNum = 0;
    for (const e of (t.events || [])) {
        const evKind = e.kind; // 'chat' | 'agent' | 'orch'
        const isTool = e.tag === 'TOOL_USE' || e.tag === 'TOOL_RESULT';
        const isPlanStep = e.tag === 'SYSINTERACTION_PLAN_STEP';
        const isPlanStart = e.tag === 'SYSINTERACTION_PLAN';
        const isPlanDone = e.tag === 'SYSINTERACTION_PLAN_DONE';
        const isTaskSpec = e.tag === 'SYSINTERACTION_TASK_SPEC';
        const isAgentGen = e.tag === 'SYSINTERACTION_AGENT_GEN';
        // Новые: sys-token resolution events (open_url, launch_app, page_recon, read_file, write_file, list_dir, run_command, window_*)
        const isSysDone = e.tag === 'SYS_OPEN_URL_DONE' || e.tag === 'SYS_LAUNCH_APP_DONE'
            || e.tag === 'SYS_PAGE_RECON_DONE' || e.tag === 'SYS_READ_FILE_DONE'
            || e.tag === 'SYS_WRITE_FILE_DONE' || e.tag === 'SYS_LIST_DIR_DONE'
            || e.tag === 'SYS_RUN_COMMAND_DONE'
            || e.tag === 'SYS_WINDOW_FOCUS_DONE' || e.tag === 'SYS_WINDOW_SEND_KEYS_DONE'
            || e.tag === 'SYS_WINDOW_CLICK_DONE' || e.tag === 'SYS_WINDOW_SCREENSHOT_DONE';
        const isPlanAny = isPlanStep || isPlanStart || isPlanDone || isTaskSpec || isAgentGen || isSysDone;
        const tagLabel = isTool ? (e.tag === 'TOOL_USE' ? 'tool_use' : 'tool_result')
            : isPlanStep ? 'plan_step'
            : isPlanStart ? 'plan_start'
            : isPlanDone ? 'plan_done'
            : isTaskSpec ? 'task_spec'
            : isAgentGen ? 'agent_gen'
            : isSysDone ? e.tag.replace('SYS_', '').replace('_DONE', '').toLowerCase()
            : (evKind === 'agent' ? 'agent' : (evKind === 'orch' ? 'orchestrator' : 'chat'));
        const toolName = isTool ? ((e.detail.match(/tool=(\S+)/) || [])[1] || 'unknown') : '';
        stepNum++;
        const isExpandable = isTool || isPlanStep || isSysDone;
        // Для plan-step: извлекаем tool и status из kv
        let planTool = '', planStatus = '';
        if (isPlanStep) {
            const kv = e.detail || '';
            const mT = kv.match(/tool=(\S+)/);
            const mS = kv.match(/status=(\S+)/);
            planTool = mT ? mT[1] : '';
            planStatus = mS ? mS[1] : '';
        }
        const detailFormatted = isTool ? fmtKvDetail(e.detail)
            : isPlanStep ? `${planTool} → ${planStatus}`
            : isPlanAny ? e.tag
            : e.tag;
        const inputHtml = isExpandable
            ? `<div class="td-step-input" style="display:none"><pre class="td-code">${escapeHtml(fmtKvDetail(e.detail))}</pre></div>`
            : '';
        pipelineSteps.push(
            `<div class="td-pipeline-step" data-step="${stepNum}">
                <div class="td-step-head" data-step="${stepNum}">
                    <span class="td-step-dot ${isTool ? 'td-dot-tool' : (isSysDone ? ((e.detail.match(/status=(\S+)/) || [])[1] === 'ok' ? 'td-dot-ok' : 'td-dot-fail') : (isPlanAny ? (planStatus === 'ok' ? 'td-dot-ok' : 'td-dot-fail') : (evKind === 'agent' ? 'td-dot-agent' : 'td-dot-chat')))}"></span>
                    <span class="td-step-tag ${isTool ? 'td-tag-tool' : (isPlanAny ? 'td-tag-plan' : (evKind === 'agent' ? 'td-tag-agent' : 'td-tag-chat'))}">${tagLabel}</span>
                    <span class="td-step-label">${escapeHtml(isTool ? toolName : detailFormatted)}</span>
                    <span class="td-step-num">#${stepNum}</span>
                    <button class="td-step-toggle" data-step="${stepNum}">${isExpandable ? '▸' : ''}</button>
                </div>
                ${inputHtml}
            </div>`
        );
    }
    const pipelineHtml = pipelineSteps.length
        ? `<div class="td-section"><div class="td-section-title">Pipeline</div><div class="td-pipeline">${pipelineSteps.join('')}</div></div>`
        : '';

    // --- Agent/Key info ---
    const agentCount = (t.calls && t.calls.length) || ((t.agent_name || t.agent) ? 1 : 0);
    const keyInfo = t.key ? `<div class="td-info-row"><span class="td-info-label">Ключ</span><span class="td-info-value">${escapeHtml(t.key)}</span></div>` : '';
    const agentInfo = agentCount
        ? `<div class="td-info-row"><span class="td-info-label">Агентов</span><span class="td-info-value">${agentCount}</span></div>`
        : '';

    // --- Status badge ---
    const statusCls = t.status === 'completed' ? 'st-completed' : (t.status === 'failed' ? 'st-failed' : 'st-running');
    const statusBadge = `<span class="status-badge ${statusCls}">${t.status === 'completed' ? 'COMPLETED' : (t.status === 'failed' ? 'FAILED' : 'RUNNING')}</span>`;

    dashEvent.hidden = false;
    dashEvent.innerHTML = `
        <div class="td-header">
            <div class="td-breadcrumb"><span class="td-crumb-active">Dashboard</span> / ${statusBadge}</div>
            <h3 class="td-title">Task Detail</h3>
            <button class="dash-event-close td-close" title="Закрыть">×</button>
        </div>
        ${promptHtml}
        ${pipelineHtml}
        <div class="td-meta">
            ${agentInfo}
            ${keyInfo}
        </div>
        <div class="td-actions">
            <button class="td-live-logs">View Live Logs</button>
            <button class="td-cancel-task">Cancel Task</button>
        </div>`;

    // --- Wire up interactions ---
    const close = dashEvent.querySelector('.td-close');
    if (close) close.addEventListener('click', () => { dashEvent.hidden = true; });

    // Expandable pipeline steps
    dashEvent.querySelectorAll('.td-pipeline-step.expanded .td-step-head').forEach(head => {
        head.addEventListener('click', () => {
            const step = head.closest('.td-pipeline-step');
            const input = step.querySelector('.td-step-input');
            if (input) {
                const visible = input.style.display !== 'none';
                input.style.display = visible ? 'none' : 'block';
                const toggle = step.querySelector('.td-step-toggle');
                if (toggle) toggle.textContent = visible ? '▸' : '▾';
            }
        });
    });

    // View Live Logs → switch to raw logs tab
    const liveLogs = dashEvent.querySelector('.td-live-logs');
    if (liveLogs) liveLogs.addEventListener('click', () => {
        dashEvent.hidden = true;
        setDashTab('raw');
    });

    // Cancel Task → mark as cancelled (client-side)
    const cancel = dashEvent.querySelector('.td-cancel-task');
    if (cancel) cancel.addEventListener('click', async () => {
        if (!await amtConfirm({ text: 'Отменить эту задачу?' })) return;
        t.status = 'cancelled';
        dashEvent.hidden = true;
        if (dashData) renderDashTable(dashData.tasks || []);
    });

    dashEvent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function setDashTab(mode) {
    logViewMode = mode;
    if (dashTabs) dashTabs.querySelectorAll('.dash-tab').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
    if (dashWrap) dashWrap.hidden = (mode !== 'dash');
    if (structuredLogsWrap) structuredLogsWrap.hidden = (mode !== 'structured');
    if (rawLogsWrap) rawLogsWrap.hidden = (mode !== 'raw');
    if (mode === 'structured') {
        loadStructuredLogs();
    } else {
        loadLogs();
    }
}

async function loadStructuredLogs() {
    if (!structuredLogsContainer) return;
    structuredLogsContainer.innerHTML = '<div class="structured-logs-loading">Загрузка...</div>';
    try {
        const res = await fetch(`${API_BASE}/api/logs/structured?limit=100`);
        const data = await res.json();
        const events = data.events || [];
        const dashboard = data.dashboard || {};
        
        if (events.length === 0) {
            structuredLogsContainer.innerHTML = '<div class="log-empty">Нет структурированных событий</div>';
            return;
        }
        
        let html = '';
        // Виджеты
        const totalEvents = dashboard.total_events || events.length;
        const errors = (dashboard.by_level || {}).ERROR || 0;
        const mcpCalls = (dashboard.by_category || {}).mcp_call || 0;
        const aiCalls = (dashboard.by_category || {}).ai_call || 0;
        
        html += `<div class="structured-widgets">
            <div class="widget"><span class="widget-value">${totalEvents}</span><span class="widget-label">Событий</span></div>
            <div class="widget"><span class="widget-value" style="color:#e74c3c">${errors}</span><span class="widget-label">Ошибок</span></div>
            <div class="widget"><span class="widget-value">${aiCalls}</span><span class="widget-label">AI вызовов</span></div>
            <div class="widget"><span class="widget-value">${mcpCalls}</span><span class="widget-label">MCP вызовов</span></div>
        </div>`;
        
        // Таблица событий
        html += '<table class="structured-table"><thead><tr><th>Время</th><th>Уровень</th><th>Категория</th><th>Сообщение</th><th>Длительность</th></tr></thead><tbody>';
        for (const ev of events.slice(0, 50)) {
            const ts = new Date(ev.timestamp).toLocaleTimeString();
            const levelClass = {DEBUG:'level-debug',INFO:'level-info',WARN:'level-warn',ERROR:'level-error'}[ev.level] || 'level-info';
            const duration = ev.duration_ms != null ? ev.duration_ms.toFixed(0) + 'ms' : '';
            html += `<tr>
                <td>${ts}</td>
                <td><span class="level-badge ${levelClass}">${ev.level}</span></td>
                <td><code>${ev.category || '—'}</code></td>
                <td class="structured-msg" title="${escapeHtml(ev.message || '')}">${escapeHtml((ev.message || '').substring(0, 80))}</td>
                <td>${duration}</td>
            </tr>`;
        }
        html += '</tbody></table>';
        
        structuredLogsContainer.innerHTML = html;
    } catch (e) {
        structuredLogsContainer.innerHTML = '<div class="log-empty">Ошибка загрузки: ' + e.message + '</div>';
    }
}

function setDashFilter(f) {
    dashFilter = f;
    if (dashFilterChips) dashFilterChips.querySelectorAll('.chip').forEach(b => b.classList.toggle('active', b.dataset.dashfilter === f));
    if (dashData) renderDashTable(dashData.tasks || []);
}

async function clearLogs() {
    if (!(await amtConfirm({ text: 'Очистить все логи за сегодня? Действие необратимо.', yesLabel: 'Очистить' }))) return;
    try {
        const res = await fetch(`${API_BASE}/api/logs/clear`, { method: 'POST' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        loadLogs();
    } catch (e) {
        if (logViewer) logViewer.innerHTML = '<div class="log-empty">Ошибка очистки логов: ' + e.message + '</div>';
    }
}

// Парсит строку вида "HH:MM:SS  [EVENT] key=value  key=value" в карточку
function parseLogLine(line) {
    const m = line.match(/^(\d{2}:\d{2}:\d{2})\s+\[?([^\]]+)\]?\s*(.*)$/);
    if (!m) {
        return { raw: line, time: '', tag: 'LOG', detail: line };
    }
    const time = m[1];
    let tag = m[2].trim();
    let detail = m[3].trim();
    const isOrch = tag.toLowerCase() === 'orchestrator';
    if (isOrch) {
        // второй уровень: [Orchestrator] [EVENT]
        const sub = detail.match(/^\[([^\]]+)\]\s*(.*)$/);
        if (sub) { detail = sub[2]; tag = 'Orchestrator·' + sub[1]; }
        else { detail = detail; }
    }
    // detail: "key=value  key=value" → читабельно
    return { raw: line, time, tag, detail: fmtKvDetail(detail), isOrch };
}

function renderLogs(lines) {
    if (!logViewer) return;
    logViewer.innerHTML = '';
    if (!lines.length) {
        logViewer.innerHTML = '<div class="log-empty">Нет логов за сегодня</div>';
        return;
    }
    // Последние → первые (новые сверху)
    const parsed = lines.slice().reverse().map(parseLogLine);
    parsed.forEach(entry => {
        if (activeLogFilter === 'orchestrator' && !entry.isOrch) return;
        if (activeLogFilter === 'error' && !/error|fail|connect_error|rate_limit/i.test(entry.tag) && !/error/i.test(entry.detail)) return;
        if (activeLogFilter === 'chat' && entry.isOrch) return;
        const div = document.createElement('div');
        div.className = 'log-entry ' + 'type-' + entry.tag.replace(/[^a-z_]/gi, '');
        if (entry.isOrch) div.classList.add('tag-orchestrator');
        div.innerHTML = `
            <span class="log-time">${entry.time}</span>
            <span class="log-tag">${escapeHtml(entry.tag)}</span>
            <span class="log-detail">${escapeHtml(entry.detail)}</span>
        `;
        logViewer.appendChild(div);
    });
}

function setLogFilter(filter) {
    activeLogFilter = filter;
    logFilterBtns.forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
    loadLogs();
}

// ===== Memory =====
async function wipeMemory() {
    if (!memoryResult) return;
    if (!(await amtConfirm({ text: 'Удалить всю память AI? Это действие нельзя отменить.', yesLabel: 'Удалить' }))) return;
    try {
        const res = await fetch(`${API_BASE}/api/memory/wipe`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'wiped') {
            memoryResult.textContent = 'Память очищена. AI начнёт с чистого листа.';
            memoryResult.className = 'test-result success';
        } else {
            memoryResult.textContent = 'Ошибка при очистке памяти';
            memoryResult.className = 'test-result error';
        }
    } catch {
        memoryResult.textContent = 'Бэкенд недоступен. Не удалось очистить память.';
        memoryResult.className = 'test-result error';
    }
}

// ===== File Attachment =====
function addFiles(files) {
    Array.from(files).forEach(file => {
        // Дедупликация: не добавлять файл с тем же именем и размером
        if (attachedFiles.some(f => f.name === file.name && f.size === file.size)) return;
        const item = { file, name: file.name, size: file.size, type: file.type };
        if (file.type && file.type.startsWith('image/')) {
            item.thumb = URL.createObjectURL(file);
        }
        attachedFiles.push(item);
    });
    renderAttachments();
}
function handleFileSelect(files) { addFiles(files); }

function handlePaste(e) {
    const files = e.clipboardData && e.clipboardData.files;
    if (files && files.length) {
        e.preventDefault();
        addFiles(files);
    }
}

function renderAttachments() {
    if (!attachmentArea) return;
    attachmentArea.innerHTML = '';
    attachedFiles.forEach((item, idx) => {
        const div = document.createElement('div');
        div.className = 'attachment-item';
        let thumbHtml = '';
        if (item.thumb) {
            thumbHtml = `<img class="attachment-thumb" src="${item.thumb}" alt="">`;
        }
        div.innerHTML = `
            ${thumbHtml}
            <span class="attachment-name">${item.name} (${formatFileSize(item.size)})</span>
            <span class="attachment-remove" data-idx="${idx}" title="Удалить">✕</span>
        `;
        attachmentArea.appendChild(div);
    });
    attachmentArea.querySelectorAll('.attachment-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.dataset.idx);
            const item = attachedFiles[idx];
            if (item && item.thumb) URL.revokeObjectURL(item.thumb);
            attachedFiles.splice(idx, 1);
            renderAttachments();
        });
    });
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

async function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const base64 = e.target.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// ===== Model Test =====
async function testModels() {
    if (!testModelsBtn || !modelsList) return;
    testModelsBtn.disabled = true;
    modelsList.innerHTML = '<div class="model-item">Загружаю...</div>';
    
    try {
        const res = await fetch(`${API_BASE}/api/models/test`, { method: 'POST' });
        const data = await res.json();
        
        if (data.ok) {
            modelsList.innerHTML = '';
            data.models.forEach(m => {
                const div = document.createElement('div');
                div.className = 'model-item';
                const caps = m.capabilities.map(c => `<span class="capability-badge">${c}</span>`).join('');
                div.innerHTML = `
                    <div class="model-name">${m.id}</div>
                    <div class="model-capabilities">${caps || '<span class="capability-badge">unknown</span>'}</div>
                `;
                modelsList.appendChild(div);
            });
        } else {
            modelsList.innerHTML = `<div class="model-item" style="color: #f87171">${data.message}</div>`;
        }
    } catch (e) {
        modelsList.innerHTML = '<div class="model-item" style="color: #f87171">Ошибка: бэкенд недоступен</div>';
    }
    testModelsBtn.disabled = false;
}

// ===== Orchestrator =====
async function loadOrchConfig() {
    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/config`);
        const data = await res.json();
        const c = data.config || {};
        if (orchEnabled) orchEnabled.checked = c.enabled !== false;
        if (orchAuto) orchAuto.checked = c.auto_mode !== false;
        if (orchRoleDrift) orchRoleDrift.checked = c.role_drift_check !== false;
        if (orchKeepContext) orchKeepContext.checked = c.keep_full_context !== false;
        if (orchAutoSave) orchAutoSave.value = c.auto_save_threshold ?? 10;
    } catch { /* backend offline */ }
}

async function saveOrchConfig() {
    const payload = {
        enabled: orchEnabled ? orchEnabled.checked : true,
        auto_mode: orchAuto ? orchAuto.checked : true,
        role_drift_check: orchRoleDrift ? orchRoleDrift.checked : true,
        keep_full_context: orchKeepContext ? orchKeepContext.checked : true,
        auto_save_threshold: parseInt(orchAutoSave?.value) || 10,
    };
    if (orchLogVerbosity) payload.log_verbosity = orchLogVerbosity.value;
    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        flashStatus(data.status === 'updated' ? 'Оркестратор обновлён' : 'Ошибка');
    } catch {
        flashStatus('Бэкенд недоступен');
    }
}

async function showOrchHealth() {
    if (!orchHealth) return;
    orchHealth.textContent = 'Загружаю...';
    orchHealth.className = 'test-result';
    try {
        const res = await fetch(`${API_BASE}/api/orchestrator/health`);
        const h = await res.json();
        orchHealth.innerHTML =
            `Запросов: ${h.total_requests}  •  Ошибок: ${h.total_errors}  •  ` +
            `Средняя задержка: ${h.avg_latency_s}с  •  ` +
            `Дрейфов роли: ${h.role_drift_events}  •  ` +
            `Сжатий контекста: ${h.context_compactions}`;
        orchHealth.className = 'test-result success';
    } catch {
        orchHealth.textContent = 'Бэкенд недоступен';
        orchHealth.className = 'test-result error';
    }
}

// ===== Агенты и скиллы =====
/**
 * Проверить, доступен ли локальный бэкенд (FastAPI на API_BASE).
 * Обновляет индикатор в шапке чата и баннер о недоступности.
 * @returns {Promise<boolean>} true, если бэкенд отвечает
 */
let _backendRetryCount = 0;
const BACKEND_MAX_RETRIES = 6;
const BACKEND_RETRY_MS = 2500;

async function checkBackendStatus() {
    if (!backendStatus) return false;
    _backendRetryCount = 0;
    return _backendCheckOnce();
}

async function _backendCheckOnce() {
    if (!backendStatus) return false;
    if (_backendRetryCount < BACKEND_MAX_RETRIES) {
        const n = _backendRetryCount + 1;
        backendStatus.className = 'backend-status checking';
        if (backendStatusLabel) backendStatusLabel.textContent = `Проверка… (${n}/${BACKEND_MAX_RETRIES})`;
        if (backendOfflineBanner) backendOfflineBanner.classList.add('hidden');
    } else {
        backendStatus.className = 'backend-status down';
        if (backendStatusLabel) backendStatusLabel.textContent = 'Бэкенд ✗';
        if (backendOfflineBanner) backendOfflineBanner.classList.remove('hidden');
        return false;
    }

    let ok = false;
    try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 5000);
        const res = await fetch(`${API_BASE}/health`, { method: 'GET', signal: ctl.signal });
        clearTimeout(t);
        ok = res.ok;
    } catch {
        ok = false;
    }

    if (ok) {
        _backendRetryCount = 0;
        backendStatus.className = 'backend-status ok';
        if (backendStatusLabel) backendStatusLabel.textContent = 'Бэкенд ✓';
        if (backendOfflineBanner) backendOfflineBanner.classList.add('hidden');
    } else {
        _backendRetryCount++;
        if (_backendRetryCount < BACKEND_MAX_RETRIES) {
            setTimeout(_backendCheckOnce, BACKEND_RETRY_MS);
        } else {
            backendStatus.className = 'backend-status down';
            if (backendStatusLabel) backendStatusLabel.textContent = 'Бэкенд ✗';
            if (backendOfflineBanner) backendOfflineBanner.classList.remove('hidden');
        }
    }
    return ok;
}

async function loadAgents() {
    try {
        const res = await fetch(`${API_BASE}/api/agents`);
        const data = await res.json();
        agentsCache = data.agents || [];
        skillsCache = data.skills || [];
        renderAgents();
        renderSkills(skillsCache);
        renderAgentSelect();
        fillHomePage();
    } catch { agentsCache = []; }
}

function renderAgents() {
    if (!agentList) return;
    const filter = (entityGroupFilter?.value || '').toLowerCase().trim();
    agentList.innerHTML = '';
    const list = filter
        ? agentsCache.filter(a => (a.group || '').toLowerCase().includes(filter))
        : agentsCache;
    if (!list.length) {
        agentList.innerHTML = '<div class="entity-empty">Нет агентов' + (filter ? ' в этой группе' : '') + '</div>';
        return;
    }
    // Группируем по group
    const byGroup = {};
    list.forEach(a => {
        const g = a.group || 'Без группы';
        (byGroup[g] = byGroup[g] || []).push(a);
    });
    Object.keys(byGroup).sort().forEach(gname => {
        if (filter) { /* уже отфильтровано, не дублируем заголовки */ }
        const ghead = document.createElement('div');
        ghead.className = 'entity-group-head';
        ghead.textContent = gname;
        agentList.appendChild(ghead);
        byGroup[gname].forEach(a => agentList.appendChild(renderAgentItem(a)));
    });
}

function renderAgentItem(a) {
    const enabled = a.enabled !== false;
    const div = document.createElement('div');
    div.className = 'entity-item' + (enabled ? '' : ' disabled');
    const letter = (a.name || a.id || '?').trim().charAt(0).toUpperCase() || '?';
    const colors = ['c1','c2','c3','c4','c5','c6'];
    const h = Array.from(a.name || a.id || '').reduce((x, ch) => (x + ch.charCodeAt(0)) % 997, 0);
    const color = colors[h % colors.length];
    div.innerHTML = `
        <span class="entity-badge ${color}">${escapeHtml(letter)}</span>
        <div class="entity-main">
            <span class="entity-title">${escapeHtml(a.name || a.id)}
                ${enabled ? '' : '<span class="entity-off">выкл</span>'}
            </span>
            <span class="entity-sub">${escapeHtml(a.description || '')} ${a.skills && a.skills.length ? `• скиллов: ${a.skills.length}` : ''}</span>
        </div>
        <div class="entity-actions">
            <button class="ghost" data-act="edit" data-id="${a.id}">Изменить</button>
            <button class="ghost" data-act="toggle" data-id="${a.id}">${enabled ? 'Выкл' : 'Вкл'}</button>
            <button class="ghost danger" data-act="del" data-id="${a.id}">Удалить</button>
        </div>
    `;
    div.querySelector('[data-act="del"]').addEventListener('click', () => deleteAgent(a.id));
    div.querySelector('[data-act="edit"]').addEventListener('click', () => editAgent(a.id));
    div.querySelector('[data-act="toggle"]').addEventListener('click', async () => {
        const ag = agentsCache.find(x => x.id === a.id);
        if (!ag) return;
        ag.enabled = ag.enabled === false;
        await fetch(`${API_BASE}/api/agents/${a.id}`, {
            method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ name: ag.name, description: ag.description, systemPrompt: ag.systemPrompt,
                model: ag.model, skills: ag.skills, enabled: ag.enabled, group: ag.group }),
        });
        loadAgents();
    });
    return div;
}

function renderSkills(skills) {
    if (!skillList) return;
    const filter = (entityGroupFilter?.value || '').toLowerCase().trim();
    skillList.innerHTML = '';
    const list = filter
        ? (skills || []).filter(s => (s.group || '').toLowerCase().includes(filter))
        : (skills || []);
    if (!list.length) {
        skillList.innerHTML = '<div class="entity-empty">Нет скиллов' + (filter ? ' в этой группе' : '') + '</div>';
        return;
    }
    const byGroup = {};
    list.forEach(s => {
        const g = s.group || 'Без группы';
        (byGroup[g] = byGroup[g] || []).push(s);
    });
    Object.keys(byGroup).sort().forEach(gname => {
        const ghead = document.createElement('div');
        ghead.className = 'entity-group-head';
        ghead.textContent = gname;
        skillList.appendChild(ghead);
        byGroup[gname].forEach(s => {
            const enabled = s.enabled !== false;
            const div = document.createElement('div');
            div.className = 'entity-item' + (enabled ? '' : ' disabled');
            const sletter = (s.name || s.id || '?').trim().charAt(0).toUpperCase() || '?';
            const colors = ['c1','c2','c3','c4','c5','c6'];
            const sh = Array.from(s.name || s.id || '').reduce((x, ch) => (x + ch.charCodeAt(0)) % 997, 0);
            const scolor = colors[sh % colors.length];
            div.innerHTML = `
                <span class="entity-badge ${scolor}">${escapeHtml(sletter)}</span>
                <div class="entity-main">
                    <span class="entity-title">${escapeHtml(s.name || s.id)}
                        ${enabled ? '' : '<span class="entity-off">выкл</span>'}
                    </span>
                    <span class="entity-sub">${escapeHtml((s.description || s.prompt || '').slice(0, 60))}</span>
                </div>
                <div class="entity-actions">
                    <button class="ghost" data-act="edit" data-id="${s.id}">Изменить</button>
                    <button class="ghost" data-act="toggle" data-id="${s.id}">${enabled ? 'Выкл' : 'Вкл'}</button>
                    <button class="ghost danger" data-act="del" data-id="${s.id}">Удалить</button>
                </div>
            `;
            div.querySelector('[data-act="del"]').addEventListener('click', () => deleteSkill(s.id));
            div.querySelector('[data-act="edit"]').addEventListener('click', () => editSkill(s.id));
            div.querySelector('[data-act="toggle"]').addEventListener('click', async () => {
                const sk = (skills || []).find(x => x.id === s.id);
                const next = sk.enabled === false;
                await fetch(`${API_BASE}/api/skills/${s.id}`, {
                    method: 'PUT', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ name: sk.name, description: sk.description, prompt: sk.prompt, enabled: next, group: sk.group }),
                });
                loadAgents();
            });
            skillList.appendChild(div);
        });
    });
}

function renderAgentSelect() {
    if (chatAgentSelect) {
        chatAgentSelect.innerHTML = '<option value="">Без агента</option>';
        agentsCache.forEach(a => {
            const o = document.createElement('option');
            o.value = a.id;
            o.textContent = a.name || a.id;
            chatAgentSelect.appendChild(o);
        });
    }
    if (sessionAgent) {
        sessionAgent.innerHTML = '<option value="">Без агента</option>';
        agentsCache.forEach(a => {
            const o = document.createElement('option');
            o.value = a.id;
            o.textContent = a.name || a.id;
            sessionAgent.appendChild(o);
        });
    }
    syncAgentMsel();
}

async function addAgent() {
    const payload = {
        name: agentName?.value.trim(),
        description: agentDesc?.value.trim(),
        systemPrompt: agentPrompt?.value.trim(),
        model: agentModel?.value.trim(),
        skills: editingAgentId ? (agentsCache.find(a => a.id === editingAgentId)?.skills || []) : [],
        group: agentGroup?.value.trim() || '',
    };
    if (agentTemp?.value) payload.temperature = parseFloat(agentTemp.value);
    if (editingAgentId) {
        payload.id = editingAgentId;
        await fetch(`${API_BASE}/api/agents/${editingAgentId}`, {
            method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        flashStatus('Агент обновлён');
    } else {
        await fetch(`${API_BASE}/api/agents`, {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        flashStatus('Агент добавлен');
    }
    agentName.value = agentDesc.value = agentPrompt.value = agentModel.value = agentTemp.value = '';
    if (agentGroup) agentGroup.value = '';
    clearAgentEdit();
    loadAgents();
}

// Режим редактирования агента (предзаполняем форму «Личность»)
let editingAgentId = null;
let editingSkillId = null;
function editAgent(id) {
    // id == null → режим «добавить нового» (чистая форма)
    if (id == null) {
        editingAgentId = null;
        clearAgentEdit();
        if (agentName) agentName.value = '';
        if (agentDesc) agentDesc.value = '';
        if (agentPrompt) agentPrompt.value = '';
        if (agentModel) agentModel.value = '';
        if (agentTemp) agentTemp.value = '';
        if (agentGroup) agentGroup.value = '';
        showPage('settings');
        showSettingsPage('sec-personality');
        agentName?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        flashStatus('Добавление агента');
        return;
    }
    const a = agentsCache.find(x => x.id === id);
    if (!a) return;
    editingAgentId = id;
    if (agentName) agentName.value = a.name || '';
    if (agentDesc) agentDesc.value = a.description || '';
    if (agentPrompt) agentPrompt.value = a.systemPrompt || '';
    if (agentModel) agentModel.value = a.model || '';
    if (agentTemp) agentTemp.value = a.temperature ?? '';
    if (agentGroup) agentGroup.value = a.group || '';
    if (addAgentBtn) addAgentBtn.textContent = 'Сохранить изменения';
    showPage('settings');
    showSettingsPage('sec-personality');
    agentName?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    flashStatus('Редактирование: ' + (a.name || a.id));
}
function clearAgentEdit() {
    editingAgentId = null;
    if (addAgentBtn) addAgentBtn.textContent = 'Добавить агента';
}
function editSkill(id) {
    // id == null → режим «добавить новый»
    if (id == null) {
        editingSkillId = null;
        clearSkillEdit();
        if (skillName) skillName.value = '';
        if (skillPrompt) skillPrompt.value = '';
        if (skillGroup) skillGroup.value = '';
        showPage('settings');
        showSettingsPage('sec-personality');
        skillName?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        flashStatus('Добавление скилла');
        return;
    }
    const s = skillsCache.find(x => x.id === id);
    if (!s) return;
    editingSkillId = id;
    if (skillName) skillName.value = s.name || '';
    if (skillPrompt) skillPrompt.value = s.prompt || '';
    if (skillGroup) skillGroup.value = s.group || '';
    if (addSkillBtn) addSkillBtn.textContent = 'Сохранить изменения';
    showPage('settings');
    showSettingsPage('sec-personality');
    skillName?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    flashStatus('Редактирование скилла: ' + (s.name || s.id));
}
function clearSkillEdit() {
    editingSkillId = null;
    if (addSkillBtn) addSkillBtn.textContent = 'Добавить скилл';
}

async function deleteAgent(id) {
    const res = await fetch(`${API_BASE}/api/agents/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (res.ok || res.status === 204) {
        loadAgents();
        loadStorage();
        flashStatus('Агент удалён');
    } else {
        flashStatus('Не удалось удалить агента');
    }
}

async function addSkill() {
    const payload = { name: skillName?.value.trim(), prompt: skillPrompt?.value.trim(), enabled: true, group: skillGroup?.value.trim() || '' };
    if (editingSkillId) {
        payload.id = editingSkillId;
        await fetch(`${API_BASE}/api/skills/${editingSkillId}`, {
            method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        flashStatus('Скилл обновлён');
    } else {
        await fetch(`${API_BASE}/api/skills`, {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        flashStatus('Скилл добавлен');
    }
    skillName.value = skillPrompt.value = '';
    if (skillGroup) skillGroup.value = '';
    clearSkillEdit();
    loadAgents();
}

async function deleteSkill(id) {
    const res = await fetch(`${API_BASE}/api/skills/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (res.ok || res.status === 204) {
        loadAgents();
        loadStorage();
        flashStatus('Скилл удалён');
    } else {
        flashStatus('Не удалось удалить скилл');
    }
}

function setChatAgent(agentId) {
    currentAgentId = agentId || '';
    syncAgentMselLabel();
}

// ===== Мульти-селект (чекбокс-поповер) для шапки чата =====
// Универсальный контрол: кнопка + всплывающий список чекбоксов.
// items: [{id, label}], emptyLabel: подпись когда ничего не выбрано.
function createMsel(cfg) {
    const wrap = cfg.wrap, btn = cfg.btn, pop = cfg.pop;
    let current = cfg.current || [];
    pop.innerHTML = '';
    const list = document.createElement('div');
    list.className = 'msel-list';
    pop.appendChild(list);
    const refresh = () => {
        list.innerHTML = '';
        (cfg.items || []).forEach(it => {
            const row = document.createElement('label');
            row.className = 'msel-row' + (current.includes(it.id) ? ' checked' : '');
            row.innerHTML = `<input type="checkbox" ${current.includes(it.id) ? 'checked' : ''}><span class="msel-row-label">${escapeHtml(it.label)}</span>`;
            row.querySelector('input').addEventListener('change', (e) => {
                if (e.target.checked) { if (!current.includes(it.id)) current.push(it.id); }
                else current = current.filter(x => x !== it.id);
                row.classList.toggle('checked', e.target.checked);
                updateLabel();
                (cfg.onToggle || function () {})(it.id, e.target.checked);
                (cfg.onChange || (() => {}))(current.slice());
            });
            list.appendChild(row);
        });
        updateLabel();
    };
    const updateLabel = () => {
        const lbl = btn.querySelector('.msel-label');
        if (!lbl) return;
        const emptyLabel = cfg.emptyLabel || (wrap && wrap.dataset.empty) || '';
        if (!current.length) { lbl.textContent = emptyLabel || '—'; return; }
        const names = (cfg.items || []).filter(it => current.includes(it.id)).map(it => it.label);
        lbl.textContent = names.length <= 2 ? names.join(', ') : `${names[0]} +${names.length - 1}`;
    };
    const close = () => { pop.classList.add('hidden'); btn.setAttribute('aria-expanded', 'false'); };
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = !pop.classList.contains('hidden');
        document.querySelectorAll('.msel-pop:not(.hidden)').forEach(p => p.classList.add('hidden'));
        if (!open) { refresh(); pop.classList.remove('hidden'); btn.setAttribute('aria-expanded', 'true'); }
        else close();
    });
    return {
        get: () => current.slice(),
        set: (next) => { current = next.slice(); refresh(); },
        refresh,
        close,
        // Обновить список элементов (когда кэш агентов/ключей изменился)
        updateItems: (items) => { cfg.items = items; refresh(); },
    };
}
// Закрытие поповеров по клику вне
document.addEventListener('click', () => {
    document.querySelectorAll('.msel-pop:not(.hidden)').forEach(p => p.classList.add('hidden'));
});

// --- Агент-мульти-селект: текущий набор = core-тумблеры + selectedAgentIds ---
function agentMselItems() {
    return agentsCache.map(a => ({ id: a.id, label: a.name || a.id }));
}
function agentMselCurrent() {
    // объединяем выбранное в core_agents: ядро-тумблеры + обычные агенты
    const arr = [];
    if (coreWebActive) arr.push('core_web');
    if (coreThinkerActive) arr.push('core_thinker');
    if (coreJailbreakActive) arr.push('core_jailbreak');
    selectedAgentIds.forEach(id => { if (!arr.includes(id)) arr.push(id); });
    return arr;
}
let _agentMsel = null;
function syncAgentMsel() {
    if (!_agentMsel && chatAgentMsel) _agentMsel = createMsel({
        wrap: chatAgentMsel, btn: chatAgentMselBtn, pop: chatAgentMselPop,
        current: agentMselCurrent(),
        items: agentMselItems(),
        emptyLabel: chatAgentMsel && chatAgentMsel.dataset.empty || 'Без агента',
        onToggle: (id, on) => {
            // обычный (не-ядро) агент → в selectedAgentIds
            const coreIds = ['core_web', 'core_thinker', 'core_jailbreak'];
            if (coreIds.includes(id)) return; // ядро управляется тумблерами
            if (on) { if (!selectedAgentIds.includes(id)) selectedAgentIds.push(id); }
            else selectedAgentIds = selectedAgentIds.filter(x => x !== id);
            applyAgentSelection();
        },
        onChange: (cur) => { /* refresh уже отрисовал */ },
    });
    // Обновляем список элементов каждый раз (кэш агентов мог измениться)
    _agentMsel.updateItems(agentMselItems());
    _agentMsel.set(agentMselCurrent());
}
function syncAgentMselLabel() {
    // обновить подпись кнопки (когда core-тумблеры переключаются из композера)
    if (_agentMsel) { _agentMsel.updateItems(agentMselItems()); _agentMsel.set(agentMselCurrent()); }
}
// Применение выбора: первый выбранный агент = "основной" (model params), остальные → core_agents
function applyAgentSelection() {
    const cur = agentMselCurrent();
    // основной = первый НЕ-ядровой агент (он несёт модель/параметры), иначе первый ядро
    const firstNamed = cur.find(id => !['core_web','core_thinker','core_jailbreak'].includes(id));
    currentAgentId = firstNamed || (cur[0] || '');
}

// --- Ключ-мульти-селект ---
function keyMselItems() {
    return (_knownKeys || []).map(k => ({ id: k.id, label: k.label || k.id }));
}
let _keyMsel = null;
function syncKeyMsel() {
    if (!_keyMsel && chatKeyMsel) _keyMsel = createMsel({
        wrap: chatKeyMsel, btn: chatKeyMselBtn, pop: chatKeyMselPop,
        current: selectedKeyIds,
        items: keyMselItems(),
        emptyLabel: chatKeyMsel && chatKeyMsel.dataset.empty || 'Активный ключ',
        onToggle: (id, on) => {
            if (on) { if (!selectedKeyIds.includes(id)) selectedKeyIds.push(id); }
            else selectedKeyIds = selectedKeyIds.filter(x => x !== id);
            applyKeySelection();
        },
    });
    // Обновляем список элементов каждый раз (кэш ключей мог измениться)
    _keyMsel.updateItems(keyMselItems());
    _keyMsel.set(selectedKeyIds);
}
function applyKeySelection() {
    // первый выбранный ключ = явный key_id (приоритет); остальные — через 429-ротацию
    currentKeyId = selectedKeyIds[0] || '';
}

// --- Системный промпт: мультиселект + свободный ввод ---
const BUILTIN_PROMPTS = [
    { id: 'p_kratko', label: 'Краткие ответы', text: 'Отвечай максимально кратко и по делу, без вступлений.' },
    { id: 'p_perevod', label: 'Переводчик', text: 'Переводи вводимые тексты. Если язык не указан — определяй и переведи с него. Сохраняй тон и формат.' },
    { id: 'p_kod', label: 'Помощник с кодом', text: 'Ты — опытный разработчик. Помогай с кодом: находи баги, объясняй, предлагай улучшения. Отвечай конкретно, с примерами.' },
    { id: 'p_sumann', label: 'Суммаризация', text: 'Сжимай вводимые тексты в краткий список главных пунктов и выводов.' },
    { id: 'p_obuch', label: 'Объясни просто', text: 'Объясняй сложные темы простыми словами, с аналогиями и примерами. Как для новичка.' },
    { id: 'p_analiz', label: 'Аналитик', text: 'Анализируй данные и тексты подробно: выводи ключевые метрики, тренды, аномалии, риски. Структурируй ответ.' },
    { id: 'p_tvor', label: 'Творческий', text: 'Отвечай креативно и живо. Используй метафоры, примеры, неожиданные обороты. Сохраняй структуру.' },
    { id: 'p_strict', label: 'Строгий режим', text: 'Будь формальным и точным. Без лишних слов. Только факты, без оценок и эмодзи.' },
];
let selectedPromptIds = [];
let currentSystemPromptOverride = '';
let _promptMsel = null;
function promptMselItems() {
    return BUILTIN_PROMPTS.map(p => ({ id: p.id, label: p.label }));
}
function syncPromptMsel() {
    if (!_promptMsel && chatPromptMsel) _promptMsel = createMsel({
        wrap: chatPromptMsel, btn: chatPromptMselBtn, pop: chatPromptMselPop,
        current: selectedPromptIds,
        items: promptMselItems(),
        emptyLabel: 'Без промпта',
        onToggle: (id, on) => {
            if (on) { if (!selectedPromptIds.includes(id)) selectedPromptIds.push(id); }
            else selectedPromptIds = selectedPromptIds.filter(x => x !== id);
            applyPromptSelection();
        },
    });
    _promptMsel.updateItems(promptMselItems());
    _promptMsel.set(selectedPromptIds);
}
function applyPromptSelection() {
    // если есть выбранные промпты → их текст; иначе → свой текст из input
    const chosen = BUILTIN_PROMPTS.filter(p => selectedPromptIds.includes(p.id));
    const customText = chatPromptCustom ? chatPromptCustom.value.trim() : '';
    if (chosen.length) {
        currentSystemPromptOverride = chosen.map(p => p.text).join('\n\n');
    } else if (customText) {
        currentSystemPromptOverride = customText;
    } else {
        currentSystemPromptOverride = '';
    }
}

// ===== Настройки: переключение страниц (внутренние табы) =====
function showSettingsPage(secId) {
    document.querySelectorAll('.settings-page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(secId);
    if (page) page.classList.add('active');
    settingsSubnavLinks.forEach(l => l.classList.toggle('active', l.dataset.sec === secId));
    // Скрываем «Сохранить все настройки» на Docs (там нечего сохранять)
    const footer = document.querySelector('.settings-footer');
    if (footer) footer.style.display = (secId === 'sec-docs') ? 'none' : '';
    // при открытии страницы личностя/документов обновить селекты
    if (secId === 'sec-personality') fillPersonalitySelects();
    if (secId === 'sec-tools') loadToolsConfig();
    if (secId === 'sec-media') loadMediaKeysUI();
    if (secId === 'sec-mcp' && typeof renderMcpSettings === 'function') renderMcpSettings();
    if (secId === 'sec-hotkeys' && window.AMTHotkeys) {
        const container = document.getElementById('hotkeySettingsContainer');
        if (container) window.AMTHotkeys.renderHotkeySettings(container);
    }
    if (secId === 'sec-coding') loadCodingSettingsUI();
}
function loadCodingSettingsUI() {
    const s = JSON.parse(localStorage.getItem('amt_coding_settings') || '{}');
    const vis = document.getElementById('codingPageVisibility');
    const root = document.getElementById('codingProjectRoot');
    const preset = document.getElementById('codingPolicyPreset');
    if (vis) vis.checked = s.visibility !== false;
    if (root) root.value = s.projectRoot || '';
    if (preset) preset.value = s.policy || 'balanced';
    applyCodingPageVisibility(vis ? vis.checked : true);
}
function saveCodingSettingsUI() {
    const s = {
        visibility: document.getElementById('codingPageVisibility')?.checked ?? true,
        projectRoot: document.getElementById('codingProjectRoot')?.value || '',
        policy: document.getElementById('codingPolicyPreset')?.value || 'balanced',
    };
    localStorage.setItem('amt_coding_settings', JSON.stringify(s));
    applyCodingPageVisibility(s.visibility);
    const chat = getCurrentChat();
    if (chat && s.projectRoot) {
        chat.projectRoot = s.projectRoot;
        saveChats();
    }
    flashStatus('Коддинг-настройки сохранены');
}
function applyCodingPageVisibility(visible) {
    const nav = document.getElementById('codePageNav');
    if (nav) nav.style.display = visible ? '' : 'none';
}
if (document.getElementById('codingSettingsSaveBtn')) document.getElementById('codingSettingsSaveBtn').addEventListener('click', saveCodingSettingsUI);
loadCodingSettingsUI();

// ===== Справка (Docs page): под-навигация + хаб расширений =====
const docsSubnavLinks = () => document.querySelectorAll('#docsSubnav a');
function showDocsPage(secId) {
    document.querySelectorAll('#docsPage .settings-page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(secId);
    if (page) page.classList.add('active');
    docsSubnavLinks().forEach(l => l.classList.toggle('active', l.dataset.docsSec === secId));
    if (secId === 'docs-ext') loadExtHub();
    if (secId === 'docs-updates') loadChangelog();
}

// Чейнджлог: список версий + «проверить обновления»
async function loadChangelog() {
    const listEl = document.getElementById('changelogList');
    const verEl = document.getElementById('changelogVersion');
    if (!listEl) return;
    let data = { releases: [] };
    try {
        const r = await fetch(`${API_BASE}/api/changelog`);
        data = await r.json();
    } catch { /* бэкенд недоступен */ }
    if (verEl) verEl.textContent = data.version || '…';
    listEl.innerHTML = '';
    const releases = data.releases || [];
    if (!releases.length) {
        listEl.innerHTML = '<div class="test-result">Нет данных об обновлениях</div>';
        return;
    }
    releases.forEach(rel => {
        const item = document.createElement('div');
        item.className = 'gen-result';
        item.innerHTML =
            `<div class="gen-result-head">` +
            `<span class="gen-result-name">v${escapeHtml(rel.version)} — ${escapeHtml(rel.title || '')}</span>` +
            `</div>` +
            `<div class="block-desc">${escapeHtml(rel.date || '')}</div>` +
            `<ul class="docs-list">` +
            (rel.changes || []).map(c => `<li>${escapeHtml(c)}</li>`).join('') +
            `</ul>`;
        listEl.appendChild(item);
    });
    const refBtn = document.getElementById('changelogRefreshBtn');
    if (refBtn) refBtn.textContent = '↻ Проверить обновления';
}

// Хаб расширений: список + вкл/выкл + добавление + удаление
async function loadExtHub() {
    const listEl = document.getElementById('extHubList');
    if (!listEl) return;
    let data = { extensions: [], dir: '' };
    try {
        const r = await fetch(`${API_BASE}/api/extensions/list`);
        data = await r.json();
    } catch { /* бэкенд недоступен */ }
    // Показываем реальный путь к каталогу расширений
    const dp = document.getElementById('extDirPath');
    if (dp) dp.textContent = data.dir ? `Каталог расширений: ${data.dir}` : '';
    listEl.innerHTML = '';
    if (!data.extensions || !data.extensions.length) {
        listEl.innerHTML = '<p class="block-desc">Расширения не найдены. Нажмите «Добавить расширение» или положите папку с manifest.json в каталог extensions/.</p>';
    }
    for (const ext of data.extensions) {
        const row = document.createElement('div');
        row.className = 'ext-hub-row';
        const title = document.createElement('div');
        title.className = 'ext-hub-title';
        title.textContent = ext.name + ' ' + ext.version;
        const desc = document.createElement('div');
        desc.className = 'ext-hub-desc';
        desc.textContent = ext.description || '';
        const caps = document.createElement('div');
        caps.className = 'ext-hub-caps';
        caps.innerHTML =
            (ext.frontend ? '<span class="ext-cap on">frontend</span>' : '') +
            (ext.backend ? '<span class="ext-cap on">backend</span>' : '');
        if (!ext.ok) caps.innerHTML += '<span class="ext-cap off">ошибка загрузки</span>';
        const toggle = document.createElement('label');
        toggle.className = 'ext-hub-toggle';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = ext.enabled !== false;
        cb.addEventListener('change', () => toggleExt(ext.name, cb.checked));
        toggle.appendChild(cb);
        toggle.appendChild(document.createTextNode(' вкл'));
        row.appendChild(title);
        row.appendChild(desc);
        row.appendChild(caps);
        row.appendChild(toggle);
        const delBtn = document.createElement('button');
        delBtn.className = 'ghost danger';
        delBtn.textContent = 'Удалить';
        delBtn.addEventListener('click', () => removeExt(ext.name));
        row.appendChild(delBtn);
        listEl.appendChild(row);
    }
}

async function removeExt(name) {
    if (!(await amtConfirm({ text: `Удалить расширение «${name}»? Папка будет стёрта из каталога extensions/.` }))) return;
    try {
        const r = await fetch(`${API_BASE}/api/extensions/${encodeURIComponent(name)}/remove`, { method: 'POST' });
        const d = await r.json();
        if (d.ok) {
            flashStatus(`Расширение «${name}» удалено`);
            loadExtHub();
        } else {
            flashStatus(d.error || 'Ошибка удаления');
        }
    } catch (e) {
        flashStatus('Ошибка: ' + (e.message || e));
    }
}

async function toggleExt(name, enabled) {
    try {
        const r = await fetch(`${API_BASE}/api/extensions/${encodeURIComponent(name)}/toggle`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled }),
        });
        const d = await r.json();
        if (d.ok) {
            // Перерисовываем frontend-расширения (включённые/выключенные)
            if (window.AMTExtensions && window.AMTExtensions.refresh) {
                await window.AMTExtensions.refresh();
            }
            flashStatus(`Расширение «${name}» ${enabled ? 'включено' : 'выключено'}`);
        } else {
            flashStatus(d.error || 'Ошибка');
        }
    } catch (e) {
        flashStatus('Ошибка: ' + (e.message || e));
    }
}

async function refreshExtList() {
    // Попросить бэкенд перечитать каталог расширений (перезапуск через env-флаг)
    try {
        await fetch(`${API_BASE}/api/extensions/reload`, { method: 'POST' });
    } catch { /* опц. */ }
    loadExtHub();
}

// ===== Медиа-ключи: загрузить в поля (loadSettings уже) + сохранить =====
function loadMediaKeysUI() {
    // поля уже заполнены loadSettings(); просто актуализируем из settings
    const s = settings || {};
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v || ''; };
    setVal('imageKey', s.imageKey); setVal('imageBaseUrl', s.imageBaseUrl); setVal('imageModel', s.imageModel);
    setVal('videoKey', s.videoKey); setVal('videoBaseUrl', s.videoBaseUrl); setVal('videoModel', s.videoModel);
    setVal('audioKey', s.audioKey); setVal('audioBaseUrl', s.audioBaseUrl); setVal('audioModel', s.audioModel); setVal('audioVoiceId', s.audioVoiceId);
    setVal('mediaPathText', s.mediaPathText); setVal('mediaPathImage', s.mediaPathImage);
    setVal('mediaPathTextImage', s.mediaPathTextImage); setVal('mediaPathVoice', s.mediaPathVoice); setVal('mediaPathVideo', s.mediaPathVideo);
    setVal('sttModel', s.sttModel);
}
async function saveMediaKeys() {
    settings = buildSettingsFromInputs();
    await SecureStore.set(STORAGE_SETTINGS, settings);
    await saveSettingsToServer();
    // Refresh the media MCP server's credentials file so it picks up the new keys/paths
    try { await fetch(`${API_BASE}/api/mcp/presets/media/creds`, { method: 'POST' }); } catch {}
    flashStatus('Медиа-ключи сохранены');
}

// ===== БЕЗОПАСНЫЕ ИНСТРУМЕНТЫ =====
let toolPending = null; // {tool, args, resultEl}
let codingApprovalReq = null; // {id, tool, risk, args, preview}
async function loadToolsConfig() {
    try {
        const r = await fetch(`${API_BASE}/api/tools/config`);
        const c = await r.json();
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
        const chk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = !!v; };
        chk('toolsEnabled', c.enabled);
        chk('toolsAutoApprove', c.auto_approve);
        set('toolsAllowedDirs', (c.allowed_dirs || []).join('\n'));
        set('toolsCmdWhitelist', (c.command_whitelist || []).join('\n'));
        set('toolsCmdTimeout', c.command_timeout || 30);
    } catch {}
    refreshToolsLog();
}
async function saveToolsConfig() {
    const dirsEl = document.getElementById('toolsAllowedDirs');
    const wlEl = document.getElementById('toolsCmdWhitelist');
    const payload = {
        enabled: document.getElementById('toolsEnabled')?.checked || false,
        auto_approve: document.getElementById('toolsAutoApprove')?.checked || false,
        allowed_dirs: (dirsEl?.value || '').split('\n').map(s => s.trim()).filter(Boolean),
        command_whitelist: (wlEl?.value || '').split('\n').map(s => s.trim()).filter(Boolean),
        command_timeout: parseInt(document.getElementById('toolsCmdTimeout')?.value) || 30,
    };
    await fetch(`${API_BASE}/api/tools/config`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });
    flashStatus('Инструменты сохранены');
}
async function refreshToolsLog() {
    const box = document.getElementById('toolsLogList');
    if (!box) return;
    try {
        const r = await fetch(`${API_BASE}/api/tools/log?limit=40`);
        const d = await r.json();
        const log = d.log || [];
        if (!log.length) { box.innerHTML = '<div class="storage-empty">Журнал пуст</div>'; return; }
        box.innerHTML = log.slice().reverse().map(l =>
            `<div class="tools-log-item">
                <div class="tl-tool">${new Date(l.ts*1000).toLocaleString('ru')} · ${escapeHtml(l.tool)}</div>
                <div class="tl-detail">${escapeHtml(JSON.stringify(l.detail))}</div>
                <div class="tl-res">→ ${escapeHtml(l.result)}</div>
            </div>`).join('');
    } catch {}
}
// Запрос инструмента с подтверждением (если не auto_approve)
async function requestTool(tool, args, resultEl) {
    let cfg = {};
    try { cfg = await (await fetch(`${API_BASE}/api/tools/config`)).json(); } catch {}
    const doExec = (approved) => {
        return fetch(`${API_BASE}/api/tools/execute`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tool, args, approved }),
        }).then(r => r.json());
    };
    if (cfg.auto_approve || !cfg.enabled) {
        const res = await doExec(true);
        if (resultEl) showToolResult(res, resultEl);
        return res;
    }
    // Нужно подтверждение
    toolPending = { tool, args, resultEl, res: await doExec(false) };
    showToolConfirm(tool, args);
    return toolPending.res;
}
function showToolConfirm(tool, args) {
    const det = document.getElementById('toolConfirmDetail');
    if (det) det.textContent = `Инструмент: ${tool}\n\nАргументы:\n${JSON.stringify(args, null, 2)}`;
    document.getElementById('toolConfirmModal').classList.remove('hidden');
}
function showCodingApproval(data) {
    codingApprovalReq = data || null;
    const det = document.getElementById('toolConfirmDetail');
    if (det) {
        det.textContent = `Коддинг-инструмент: ${data?.tool || 'tool'}\n\n` +
            (data?.preview ? `Предпросмотр:\n${data.preview}\n\n` : '') +
            `Аргументы:\n${JSON.stringify(data?.args || {}, null, 2)}`;
    }
    document.getElementById('toolConfirmModal').classList.remove('hidden');
}
function respondCodingApproval(decision) {
    if (!codingApprovalReq) return;
    const req = codingApprovalReq;
    codingApprovalReq = null;
    document.getElementById('toolConfirmModal').classList.add('hidden');
    if (currentWs && currentWs.readyState === WebSocket.OPEN) {
        currentWs.send(JSON.stringify({ type: 'tool_approval_response', id: req.id, decision }));
    }
}
async function approveToolConfirm() {
    if (codingApprovalReq) {
        respondCodingApproval('once');
        return;
    }
    if (!toolPending) return;
    document.getElementById('toolConfirmModal').classList.add('hidden');
    const { tool, args, resultEl } = toolPending;
    const res = await fetch(`${API_BASE}/api/tools/execute`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ tool, args, approved: true }),
    }).then(r => r.json());
    if (resultEl) showToolResult(res, resultEl);
    toolPending = null;
}
function denyToolConfirm() {
    if (codingApprovalReq) {
        respondCodingApproval('reject');
        return;
    }
    document.getElementById('toolConfirmModal').classList.add('hidden');
    const el = toolPending?.resultEl;
    if (el) showToolResult({ ok: false, error: 'Действие отклонено пользователем' }, el);
    toolPending = null;
}
if (document.getElementById('toolConfirmApprove')) document.getElementById('toolConfirmApprove').addEventListener('click', approveToolConfirm);
if (document.getElementById('toolConfirmDeny')) document.getElementById('toolConfirmDeny').addEventListener('click', denyToolConfirm);
const _tcModal = document.getElementById('toolConfirmModal');
if (_tcModal) _tcModal.addEventListener('click', e => { if (e.target === _tcModal) denyToolConfirm(); });
function showToolResult(res, el) {
    if (!el) return;
    const line = document.createElement('div');
    line.className = 'message bot';
    const ok = res.ok;
    let text = ok
        ? `✔ ${res.tool || 'инструмент'}: ${res.path || res.url || res.stdout || res.result || 'выполнено'}`
        : `✖ ${res.error || 'ошибка'}`;
    line.innerHTML = `<div class="message-content">${escapeHtml(text)}</div>`;
    el.appendChild(line);
    scrollToBottom();
}

// ===== Проекты: рабочая папка ИИ-инструментов =====
async function loadProjectCurrent() {
    const el = document.getElementById('projCurrent');
    if (!el) return;
    try {
        const r = await fetch(`${API_BASE}/api/projects`);
        const d = await r.json();
        const root = d.project && d.project.root;
        el.textContent = root ? root : '(нет проекта — дефолтные папки)';
    } catch { el.textContent = '(ошибка загрузки)'; }
}
function showProjResult(res) {
    const el = document.getElementById('projResult');
    if (!el) return;
    if (res.ok) { el.textContent = res.project ? `Проект выбран: ${res.project}` : 'Проект снят'; el.className = 'test-result success'; }
    else { el.textContent = res.error || 'Ошибка'; el.className = 'test-result error'; }
    setTimeout(() => { if (el) el.textContent = ''; }, 4000);
}

// ===== Инструменты: picker в чате =====
function toggleToolPicker() {
    const p = document.getElementById('toolPicker');
    if (!p) return;
    p.classList.toggle('hidden');
}
async function runToolFromPicker(tool) {
    document.getElementById('toolPicker')?.classList.add('hidden');
    let args = {};
    if (tool === 'read_file') {
        const path = await amtPrompt('Путь к файлу (read-only, в разрешённых каталогах):', '');
        if (!path) return;
        args = { path };
    } else if (tool === 'list_dir') {
        const path = await amtPrompt('Каталог (read-only):', '.');
        if (path === null) return;
        args = { path };
    } else if (tool === 'run_command') {
        const cmd = await amtPrompt('Команда (только из белого списка):', '');
        if (!cmd) return;
        args = { command: cmd };
    } else if (tool === 'open_url') {
        const url = await amtPrompt('Ссылка (http/https):', 'https://');
        if (!url) return;
        args = { url };
    } else if (tool === 'write_file') {
        const path = await amtPrompt('Путь к файлу (только в разрешённых каталогах):', '');
        if (!path) return;
        const content = await amtPrompt('Содержимое файла:', '');
        if (content === null) return;
        args = { path, content };
    } else if (tool === 'create_dir') {
        const path = await amtPrompt('Путь к папке (только в разрешённых каталогах):', '');
        if (!path) return;
        args = { path };
    }
    const res = await requestTool(tool, args, chatMessages);
    refreshToolsLogSoon();
    if (!res || res.ok === false) {
        const line = document.createElement('div');
        line.className = 'message bot';
        line.innerHTML = `<div class="message-content">${escapeHtml('✖ ' + (res?.error || 'не удалось выполнить'))}</div>`;
        chatMessages.appendChild(line);
        scrollToBottom();
    }
}
let toolsLogTimer = null;
function refreshToolsLogSoon() {
    clearTimeout(toolsLogTimer);
    toolsLogTimer = setTimeout(() => { if (document.getElementById('sec-tools')?.classList.contains('active')) refreshToolsLog(); }, 400);
}

// ===== Быстрые сценарии: хранилище (localStorage) =====
const SCENARIOS_KEY = 'amt_scenarios';
const DEFAULT_SCENARIOS = [
    { id: 'sc_default_chat', name: 'Просто чат', group: 'Чат', desc: 'Обычный разговор без личности и промптов', type: 'plain' },
    { id: 'sc_default_qa', name: 'Быстрый вопрос', group: 'Чат', desc: 'Короткий вопрос — краткий ответ', type: 'plain', systemPrompt: 'Отвечай максимально кратко и по делу, без вступлений.' },
    { id: 'sc_default_summary', name: 'Суммаризация', group: 'Чат', desc: 'Сократи текст до ключевых пунктов', type: 'custom', systemPrompt: 'Сжимай вводимые тексты в краткий список главных пунктов и выводов.' },
    { id: 'sc_default_code', name: 'Помощь с кодом', group: 'Чат', desc: 'Оцени/исправь код, объясни кратко', type: 'custom', systemPrompt: 'Ты — опытный разработчик. Помогай с кодом: нахо��ить баги, объяснять, предлагать улучшения. Отвечай конкретно, с примерами.' },
    { id: 'sc_default_translate', name: 'Перевод', group: 'Чат', desc: 'Перевести текст на другой язык', type: 'custom', systemPrompt: 'Переводи вводимые тексты. Если язык не указан — определяй и переведи с него. Сохраняй тон и формат.' },
];
function loadScenarios() {
    try {
        const raw = localStorage.getItem(SCENARIOS_KEY);
        if (raw) return JSON.parse(raw);
        // Первый запуск: сажаем 5 настроенных сценариев
        localStorage.setItem(SCENARIOS_KEY, JSON.stringify(DEFAULT_SCENARIOS));
        return DEFAULT_SCENARIOS.slice();
    } catch { return DEFAULT_SCENARIOS.slice(); }
}
function saveScenarios(list) {
    localStorage.setItem(SCENARIOS_KEY, JSON.stringify(list));
}
function newScenarioId() { return 'sc_' + Math.random().toString(36).slice(2, 9); }

// ===== Главная страница: создание чата (личность/агент/скилл/промпт) =====
function fillHomePage() {
    // Агенты
    if (homeAgentSel) {
        homeAgentSel.innerHTML = '<option value="">— без агента —</option>';
        agentsCache.filter(a => a.enabled !== false).forEach(a => {
            const o = document.createElement('option');
            o.value = a.id; o.textContent = a.name || a.id;
            homeAgentSel.appendChild(o);
        });
    }
    // Скиллы (чипы)
    fetch(`${API_BASE}/api/agents`).then(r => r.json()).then(d => {
        if (!homeSkillsPicker) return;
        homeSkillsPicker.innerHTML = '';
        const sk = d.skills || [];
        if (!sk.length) {
            homeSkillsPicker.innerHTML = '<div class="picker-empty">Нет скиллов — добавьте «+»</div>';
            return;
        }
        sk.forEach(s => {
            const chip = document.createElement('label');
            chip.className = 'picker-chip' + (s.enabled === false ? ' dimmed' : '');
            chip.dataset.id = s.id;
            chip.innerHTML = `<input type="checkbox"> <span>${escapeHtml(s.name || s.id)}${s.enabled === false ? ' (выкл)' : ''}</span>`;
            chip.querySelector('input').addEventListener('change', e => chip.classList.toggle('selected', e.target.checked));
            homeSkillsPicker.appendChild(chip);
        });
    }).catch(() => {});
    // Ключи
    fetch(`${API_BASE}/api/keys`).then(r => r.json()).then(d => {
        if (!homeKeySel) return;
        homeKeySel.innerHTML = '<option value="">Активный</option>';
        (d.keys || []).forEach(k => {
            const o = document.createElement('option');
            o.value = k.id; o.textContent = k.label || k.id;
            homeKeySel.appendChild(o);
        });
    }).catch(() => {});
    // Base URL — дефолт из настроек
    loadSettings().then(s => {
        if (homeBaseUrlInput && !homeBaseUrlInput.value) homeBaseUrlInput.value = s.base_url || '';
        if (homeModelInput && !homeModelInput.value) homeModelInput.value = s.model || '';
    }).catch(() => {});
    // Фильтр групп сценариев
    fillScenarioGroupFilter();
    applyHomeType(homeChatType);
    renderHomeQuick();
}

function applyHomeType(type) {
    homeChatType = type;
    if (homeTypeSeg) homeTypeSeg.querySelectorAll('.seg-btn').forEach(b => b.classList.toggle('active', b.dataset.homeType === type));
    if (homePersonalityBlock) homePersonalityBlock.style.display = (type === 'personality') ? '' : 'none';
    if (homeCustomBlock) homeCustomBlock.style.display = (type === 'custom') ? '' : 'none';
}

// ===== Модалка «прописать» агента/скилла =====
function openEntityModal(kind) {
    homeEntityKind = kind;
    if (!homeEntityModal) return;
    document.getElementById('homeEntityTitle').textContent = kind === 'agent' ? 'Прописать агента' : 'Прописать скилл';
    document.getElementById('homeEntityName').value = '';
    document.getElementById('homeEntityDesc').value = '';
    document.getElementById('homeEntityModel').value = '';
    document.getElementById('homeEntityModelRow').style.display = kind === 'agent' ? '' : 'none';
    homeEntityModal.classList.remove('hidden');
}
function closeEntityModal() { if (homeEntityModal) homeEntityModal.classList.add('hidden'); }
async function saveEntityFromModal() {
    const name = document.getElementById('homeEntityName').value.trim();
    const desc = document.getElementById('homeEntityDesc').value.trim();
    if (!name) { flashStatus('Введите название'); return; }
    if (homeEntityKind === 'agent') {
        const model = document.getElementById('homeEntityModel').value.trim();
        const payload = { name, description: desc, systemPrompt: desc, model };
        let id = null;
        // если агент с таким именем уже есть — обновим, иначе создадим
        const exists = agentsCache.find(a => (a.name || '') === name);
        if (exists) {
            payload.id = exists.id;
            await fetch(`${API_BASE}/api/agents/${exists.id}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
            id = exists.id;
        } else {
            const r = await fetch(`${API_BASE}/api/agents`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
            id = (await r.json()).id;
        }
        if (id && homeAgentSel) homeAgentSel.value = id;
    } else {
        const payload = { name, prompt: desc };
        const exists = skillsCache.find(s => (s.name || '') === name);
        if (exists) {
            await fetch(`${API_BASE}/api/skills/${exists.id}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ ...payload, id: exists.id }) });
        } else {
            const r = await fetch(`${API_BASE}/api/skills`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
        }
    }
    closeEntityModal();
    await loadAgents();
    fillHomePage();
    flashStatus(homeEntityKind === 'agent' ? 'Агент сохранён' : 'Скилл сохранён');
}

// Заполняет фильтр групп сценариев
function fillScenarioGroupFilter() {
    if (!homeQuickGroup) return;
    const groups = [...new Set(loadScenarios().map(s => s.group).filter(Boolean))].sort();
    const prev = homeQuickGroup.value;
    homeQuickGroup.innerHTML = '<option value="">Все группы</option>';
    groups.forEach(g => {
        const o = document.createElement('option');
        o.value = g; o.textContent = g;
        homeQuickGroup.appendChild(o);
    });
    homeQuickGroup.value = groups.includes(prev) ? prev : '';
}

// Состояние сценарий-модалки
let scEditingId = null;
function openScenarioModal(scenarioId) {
    scEditingId = scenarioId || null;
    const list = loadScenarios();
    const sc = scenarioId ? list.find(s => s.id === scenarioId) : null;
    document.getElementById('scenarioModalTitle').textContent = sc ? 'Редактировать сценарий' : 'Новый сценарий';
    document.getElementById('scName').value = sc?.name || '';
    document.getElementById('scGroup').value = sc?.group || '';
    document.getElementById('scDesc').value = sc?.desc || '';
    document.getElementById('scType').value = sc?.type || 'plain';
    document.getElementById('scModel').value = sc?.model || '';
    document.getElementById('scBaseUrl').value = sc?.baseUrl || '';
    document.getElementById('scPrompt').value = sc?.systemPrompt || '';
    // агенты в select
    const sel = document.getElementById('scAgent');
    sel.innerHTML = '<option value="">— без агента —</option>';
    agentsCache.filter(a => a.enabled !== false).forEach(a => {
        const o = document.createElement('option');
        o.value = a.id; o.textContent = a.name || a.id;
        sel.appendChild(o);
    });
    sel.value = sc?.agentId || '';
    document.getElementById('scenarioModal').classList.remove('hidden');
}
function closeScenarioModal() {
    document.getElementById('scenarioModal').classList.add('hidden');
    scEditingId = null;
}
function saveScenarioModal() {
    const name = document.getElementById('scName').value.trim();
    if (!name) { flashStatus('Введите название сценария'); return; }
    const type = document.getElementById('scType').value;
    const payload = {
        name,
        group: document.getElementById('scGroup').value.trim(),
        desc: document.getElementById('scDesc').value.trim(),
        type,
        agentId: type === 'personality' ? (document.getElementById('scAgent').value || '') : '',
        systemPrompt: document.getElementById('scPrompt').value.trim(),
        model: document.getElementById('scModel').value.trim(),
        baseUrl: document.getElementById('scBaseUrl').value.trim(),
    };
    const list = loadScenarios();
    if (scEditingId) {
        const sc = list.find(s => s.id === scEditingId);
        if (sc) Object.assign(sc, payload);
    } else {
        list.push(Object.assign({ id: newScenarioId() }, payload));
    }
    saveScenarios(list);
    closeScenarioModal();
    fillScenarioGroupFilter();
    renderHomeQuick();
    flashStatus(scEditingId ? 'Сценарий обновлён' : 'Сценарий создан');
}
function deleteScenario(id) {
    saveScenarios(loadScenarios().filter(s => s.id !== id));
    fillScenarioGroupFilter();
    renderHomeQuick();
}

// ===== Хранилище: взаимодействия с расширениями и темами =====
async function toggleExtFromStorage(name, currentlyOn) {
    const r = await fetch(`${API_BASE}/api/extensions/${encodeURIComponent(name)}/toggle`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentlyOn }),
    }).then(x => x.json()).catch(() => ({ ok: false, error: 'ошибка сети' }));
    if (r.ok) { if (window.AMTExtensions) AMTExtensions.refresh(); flashStatus(currentlyOn ? 'Расширение выключено' : 'Расширение включено'); loadStorage(); }
    else flashStatus(r.error || 'Не удалось переключить');
}
function applyThemeFromStorage(themeId) {
    try {
        const custom = JSON.parse(localStorage.getItem('amt_custom_themes') || '{}');
        const t = custom[themeId];
        if (t && window.AMTThemes && window.AMTThemes.applyTheme) {
            window.AMTThemes.applyTheme(themeId);
            flashStatus('Тема применена: ' + t.label);
            loadStorage();
        } else flashStatus('Тема не найдена');
    } catch { flashStatus('Ошибка применения темы'); }
}
function deleteThemeFromStorage(themeId) {
    try {
        const custom = JSON.parse(localStorage.getItem('amt_custom_themes') || '{}');
        delete custom[themeId];
        localStorage.setItem('amt_custom_themes', JSON.stringify(custom));
        if (window.AMTThemes && window.AMTThemes.current && window.AMTThemes.current().theme === themeId) {
            window.AMTThemes.applyTheme('ocean');
        }
        flashStatus('Тема удалена');
        loadStorage();
    } catch { flashStatus('Ошибка удаления темы'); }
}

// Применить сценарий к форме «Главная»
function applyScenario(sc) {
    if (sc.agentId && homeAgentSel) homeAgentSel.value = sc.agentId;
    if (sc.type) { homeChatType = sc.type; applyHomeType(sc.type); }
    if (sc.systemPrompt && homeSystemPrompt) homeSystemPrompt.value = sc.systemPrompt;
    if (sc.model && homeModelInput) homeModelInput.value = sc.model;
    if (sc.baseUrl && homeBaseUrlInput) homeBaseUrlInput.value = sc.baseUrl;
    // скиллы
    if (Array.isArray(sc.skills) && homeSkillsPicker) {
        homeSkillsPicker.querySelectorAll('.picker-chip').forEach(chip => {
            const on = sc.skills.includes(chip.dataset.id);
            chip.classList.toggle('selected', on);
            const cb = chip.querySelector('input'); if (cb) cb.checked = on;
        });
    }
}

function renderHomeQuick() {
    if (!homeQuickList) return;
    homeQuickList.innerHTML = '';
    const filter = (homeQuickGroup?.value || '').trim();
    let list = loadScenarios().filter(s => !filter || s.group === filter);

    // Встроенный «Простой чат» — как ещё один сценарий (если без фильтра)
    if (!filter && !list.some(s => s.id === 'sc_default_chat')) {
        list = list.concat(loadScenarios().filter(s => s.id === 'sc_default_chat'));
    }

    if (!list.length) {
        homeQuickList.innerHTML = `<div class="scenario-empty">Сценариев нет. Нажмите «＋ Сценарий», чтобы создать свой набор (можно группировать и редактировать).</div>`;
        return;
    }
    // Группировка: каждый сценарий — карточка в едином адаптивном grid
    const byGroup = {};
    list.forEach(sc => { const g = sc.group || 'Без группы'; (byGroup[g] = byGroup[g] || []).push(sc); });
    Object.keys(byGroup).sort().forEach(gname => {
        const wrap = document.createElement('div');
        wrap.className = 'scenario-group';
        const head = document.createElement('div');
        head.className = 'scenario-group-head';
        head.textContent = gname;
        wrap.appendChild(head);
        const cards = document.createElement('div');
        cards.className = 'scenario-cards';
        byGroup[gname].forEach(sc => {
            const c = document.createElement('button');
            c.className = 'quick-item scenario-card';
            c.innerHTML = `<span class="quick-label">${escapeHtml(sc.name)}</span><span class="quick-desc">${escapeHtml(sc.desc || 'набор параметров')}</span>`;
            c.addEventListener('click', () => { applyScenario(sc); flashStatus('Применено: ' + sc.name); });
            c.addEventListener('contextmenu', async e => { e.preventDefault(); if (await amtConfirm({ text: 'Удалить сценарий «' + sc.name + '»?' })) deleteScenario(sc.id); });
            const ed = document.createElement('span');
            ed.className = 'scenario-edit';
            ed.innerHTML = '<svg class="ic" viewBox="0 0 24 24" width="12" height="12"><path d="M14 6l4 4-8 8-4-4zM14 6l-3-3-3 3M10 10l3 3" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>';
            ed.title = 'Редактировать сценарий';
            ed.addEventListener('click', ev => { ev.stopPropagation(); openScenarioModal(sc.id); });
            c.appendChild(ed);
            cards.appendChild(c);
        });
        wrap.appendChild(cards);
        homeQuickList.appendChild(wrap);
    });
}

// ===== ХРАНИЛИЩЕ: все данные пользователя в одном месте =====
async function loadStorage() {
    if (!storageSections) return;
    storageStats.innerHTML = '';
    storageSections.innerHTML = '<div class="storage-empty">Загрузка…</div>';
    let agents = [], skills = [], keys = [], sessions = [], codingSessions = [], files = [], memory = { facts: [], user_prefs: {} };
    let localChats = [];
    let extensions = [];
    let customThemes = {};
    let sysinteraction = null;
    try {
        const [agRes, keyRes, sesRes, codingSesRes, filesRes, memRes, extRes, sysRes] = await Promise.all([
            fetch(`${API_BASE}/api/agents`).then(r => r.json()),
            fetch(`${API_BASE}/api/keys`).then(r => r.json()),
            fetch(`${API_BASE}/api/sessions`).then(r => r.json()),
            fetch(`${API_BASE}/api/sessions/coding`).then(r => r.json()),
            fetch(`${API_BASE}/api/files`).then(r => r.json()),
            fetch(`${API_BASE}/api/memory`).then(r => r.json()),
            fetch(`${API_BASE}/api/extensions/list`).then(r => r.json()),
            fetch(`${API_BASE}/api/sysinteraction`).then(r => r.ok ? r.json() : null).catch(() => null),
        ]);
        agents = agRes.agents || [];
        skills = agRes.skills || [];
        keys = keyRes.keys || [];
        sessions = sesRes.sessions || [];
        codingSessions = codingSesRes.coding_sessions || [];
        files = filesRes.files || [];
        memory = memRes;
        extensions = extRes.extensions || [];
        sysinteraction = sysRes;
    } catch (e) { /* сеть недоступна — покажем локальное */ }
    // локальные чаты + сценарии + темы (из localStorage)
    localChats = chats.slice();
    const scenarios = loadScenarios();
    try { customThemes = JSON.parse(localStorage.getItem('amt_custom_themes') || '{}'); } catch { customThemes = {}; }

    renderStorageInteractive(agents, skills, keys, sessions, files, memory, localChats, scenarios, extensions, customThemes, sysinteraction, codingSessions);
}

// Рендер интерактивного хранилища
function renderStorageInteractive(agents, skills, keys, sessions, files, memory, localChats, scenarios, extensions = [], customThemes = {}, sysinteraction = null, codingSessions = []) {
    const sections = [
        { key: 'chats', title: 'Чаты', icon: 'chat', c: 'c1',
            items: localChats.map(c => ({ id: c.id, t: c.title, s: `${c.messages?.length || 0} сообщ.` })),
            add: true, addFn: () => { startNewChat(); flashStatus('Новый чат создан'); },
            itemActions: c => [
                { label: 'Открыть', cls: '', act: () => openChat(localChats.find(x => x.id === c.id)) },
                { label: 'Изменить', cls: '', act: () => openChatMetaModal(c.id) },
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить чат?', text: 'Чат будет удалён без возможности восстановления.' }).then(ok => { if (ok) { deleteChat(c.id); saveChats().then(() => { renderChatsList(); loadStorage(); }); } }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('chats', c) },
            ] },
        { key: 'agents', title: 'Агенты', icon: 'agent', c: 'c5',
            items: agents.map(a => ({ id: a.id, t: a.name || a.id, s: a.description || (a.skills?.length ? a.skills.length + ' скиллов' : ''), on: a.enabled !== false, data: a, folder: a.folder || '' })),
            add: true, addFn: () => { showPage('settings'); showSettingsPage('sec-personality'); editAgent(null); },
            itemActions: a => [
                { label: 'Применить', cls: 'on', act: () => { setChatAgent(a.id); flashStatus('Агент применён к чату'); showPage('chat'); } },
                { label: a.on ? 'Выкл' : 'Вкл', cls: a.on ? '' : 'on', act: () => toggleAgentEnabled(a) },
                { label: 'Изменить', cls: '', act: () => editAgent(a.id) },
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить агента?', text: 'Агент и его настройки будут удалены.' }).then(ok => { if (ok) deleteAgent(a.id).then(loadStorage); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('agents', a) },
            ] },
        { key: 'skills', title: 'Скиллы', icon: 'skill', c: 'c3',
            items: skills.map(s => ({ id: s.id, t: s.name || s.id, s: (s.description || s.prompt || '').slice(0, 60), on: s.enabled !== false, data: s, folder: s.folder || '' })),
            add: true, addFn: () => { showPage('settings'); showSettingsPage('sec-personality'); editSkill(null); },
            itemActions: s => [
                { label: s.on ? 'Выкл' : 'Вкл', cls: s.on ? '' : 'on', act: () => toggleSkillEnabled(s) },
                { label: 'Изменить', cls: '', act: () => editSkill(s.id) },
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить скилл?', text: 'Скилл будет удалён.' }).then(ok => { if (ok) deleteSkill(s.id).then(loadStorage); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('skills', s) },
            ] },
        { key: 'keys', title: 'API-ключи', icon: 'key', c: 'c4',
            items: keys.map(k => ({ id: k.id, t: k.label || k.id, s: `${k.baseUrl || ''} · ${k.model || ''}`, on: k.hasKey !== false, data: k })),
            add: true, addFn: () => { showPage('settings'); showSettingsPage('sec-keys'); flashStatus('Добавление ключа — вкладка «Настройки»'); },
            itemActions: k => [
                { label: 'Активировать', cls: 'on', act: () => fetch(`${API_BASE}/api/keys/${k.id}/activate`, { method: 'POST' }).then(() => { loadAgents(); loadStorage(); flashStatus('Ключ активен'); }) },
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить ключ?', text: 'API-ключ будет удалён из хранилища.' }).then(ok => { if (ok) fetch(`${API_BASE}/api/keys/${k.id}`, { method: 'DELETE' }).then(() => loadStorage()); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('keys', k) },
            ] },
        { key: 'sessions', title: 'Сессии', icon: 'session', c: 'c2',
            items: sessions.map(s => ({ id: s.id, t: s.title || s.id, s: `${s.messages?.length || 0} сообщ.` })),
            add: false,
            clearAll: sessions.length ? { label: 'Очистить всё', act: async () => { const ok = await amtConfirm({ title: 'Удалить все сессии?', text: `Будут удалены сессии (${sessions.length}).`, yesLabel: 'Удалить всё' }); if (!ok) return; for (const s of sessions) { try { await fetch(`${API_BASE}/api/sessions/${s.id}`, { method: 'DELETE' }); } catch {} } loadStorage(); } } : null,
            itemActions: s => [
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить сессию?', text: 'Сессия будет удалена.' }).then(ok => { if (ok) fetch(`${API_BASE}/api/sessions/${s.id}`, { method: 'DELETE' }).then(() => loadStorage()); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('sessions', s) },
            ] },
        { key: 'memory', title: 'Память', icon: 'memory', c: 'c6',
            items: [
                ...(memory.facts || []).map((f, i) => ({ id: 'f' + i, t: f.topic || 'факт', s: (f.statement || f.text || JSON.stringify(f)).slice(0, 70) })),
                ...(memory.user_prefs ? Object.entries(memory.user_prefs).map(([k, v], i) => ({ id: 'p' + i, t: k, s: String(v).slice(0, 70) })) : []),
            ],
            add: false,
            clearAll: { label: 'Очистить всё', act: () => amtConfirm({ title: 'Стереть память?', text: 'Все факты и предпочтения будут удалены без возможности восстановления.', yesLabel: 'Стереть' }).then(ok => { if (ok) fetch(`${API_BASE}/api/memory/wipe`, { method: 'POST' }).then(() => loadStorage()); }) },
            itemActions: () => [
                { label: 'Стереть память', cls: 'danger', act: () => amtConfirm({ title: 'Стереть память?', text: 'Все факты и предпочтения будут удалены.', yesLabel: 'Стереть' }).then(ok => { if (ok) fetch(`${API_BASE}/api/memory/wipe`, { method: 'POST' }).then(() => loadStorage()); }) },
            ] },
        { key: 'files', title: 'Файлы', icon: 'file', c: 'c1',
            items: files.map(f => ({ id: f.name, t: f.name, s: fmtSize(f.size) })),
            add: false,
            clearAll: files.length ? { label: 'Очистить всё', act: async () => { const ok = await amtConfirm({ title: 'Удалить все файлы?', text: `Будут удалены файлы (${files.length}).`, yesLabel: 'Удалить всё' }); if (!ok) return; for (const f of files) { try { await fetch(`${API_BASE}/api/files/${encodeURIComponent(f.id)}`, { method: 'DELETE' }); } catch {} } loadStorage(); } } : null,
            itemActions: f => [
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить файл?', text: `«${f.t}» будет удалён.`, yesLabel: 'Удалить' }).then(ok => { if (ok) fetch(`${API_BASE}/api/files/${encodeURIComponent(f.id)}`, { method: 'DELETE' }).then(() => loadStorage()); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('files', f) },
            ] },
        { key: 'scenarios', title: 'Сценарии', icon: 'scenario', c: 'c5',
            items: scenarios.map(sc => ({ id: sc.id, t: sc.name, s: sc.group ? 'группа: ' + sc.group : (sc.desc || ''), data: sc })),
            add: true, addFn: () => openScenarioModal(null),
            itemActions: sc => [
                { label: 'Применить', cls: 'on', act: () => { showPage('home'); applyScenario(sc.data || sc); flashStatus('Сценарий применён'); } },
                { label: 'Изменить', cls: '', act: () => openScenarioModal(sc.id) },
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить сценарий?', text: `«${sc.t}» будет удалён.`, yesLabel: 'Удалить' }).then(ok => { if (ok) deleteScenario(sc.id).then(() => loadStorage()); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('scenarios', sc) },
            ] },
        { key: 'extensions', title: 'Расширения', icon: 'ext', c: 'c4',
            items: extensions.map(x => ({ id: x.name, t: x.name, s: (x.description || '') + (x.version ? ' · v' + x.version : ''), on: x.enabled !== false, data: x })),
            add: true, addFn: () => { showPage('docs'); showDocsPage('docs-ext'); document.getElementById('extAddBtn')?.click(); },
            itemActions: x => [
                { label: x.on ? 'Выключить' : 'Включить', cls: x.on ? '' : 'on', act: () => toggleExtFromStorage(x.name, x.on) },
                { label: 'Удалить', cls: 'danger', act: () => removeExt(x.name) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('extensions', x) },
            ] },
        { key: 'themes', title: 'Темы', icon: 'theme', c: 'c6',
            items: Object.values(customThemes).map(t => ({ id: t.id, t: t.label || t.id, s: 'кастомная', data: t })),
            add: true, addFn: () => { showPage('settings'); showSettingsPage('sec-themes'); },
            itemActions: t => [
                { label: 'Применить', cls: 'on', act: () => applyThemeFromStorage(t.id) },
                { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить тему?', text: 'Кастомная тема будет удалена.', yesLabel: 'Удалить' }).then(ok => { if (ok) deleteThemeFromStorage(t.id); }) },
                { label: 'В папку', cls: 'folder-move', title: 'Переместить в папку', act: () => moveItemToFolder('themes', t) },
            ] },
        { key: 'coding', title: 'Коддинг', icon: 'code', c: 'c5',
            items: [
                ...localChats.filter(c => c.chat_mode === 'coding').map(c => ({
                    id: 'chat:' + c.id,
                    t: c.title || c.id,
                    s: c.projectRoot ? 'проект: ' + c.projectRoot : 'чаты без проекта',
                    data: c,
                    kind: 'chat',
                })),
                ...codingSessions.map(s => ({
                    id: 'ses:' + s.id,
                    t: s.name || s.id,
                    s: s.root ? 'сессия: ' + s.root : 'кодинг-сессия',
                    data: s,
                    kind: 'session',
                })),
            ],
            add: true, addFn: () => { startNewChat(); flashStatus('Новый кодинг-чат создан'); },
            itemActions: it => {
                if (it.kind === 'chat') {
                    const chat = localChats.find(c => c.id === it.data.id);
                    return [
                        { label: 'Откры��ь', cls: 'on', act: () => { if (chat) openChat(chat); } },
                        { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить кодинг-чат?', text: 'Локальный кодинг-чат будет удалён.' }).then(ok => { if (ok) { deleteChat(it.data.id); saveChats().then(() => { renderChatsList(); loadStorage(); }); } }) },
                    ];
                }
                const ses = it.data;
                const currentCoding = localChats.find(c => c.chat_mode === 'coding' && c.id === currentChatId) || null;
                return [
                    { label: 'Продолжить', cls: 'on', act: () => window.AMTCommands?.codingSessionAction?.('continue', { id: ses.id, base_chat_id: currentCoding?.id || '' }).then(() => loadStorage()) },
                    { label: 'Дублировать', cls: '', act: () => window.AMTCommands?.codingSessionAction?.('duplicate', { id: ses.id }).then(() => loadStorage()) },
                    { label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить кодинг-сессию?', text: 'Сессия будет удалена из хранилища.' }).then(ok => { if (ok) window.AMTCommands?.codingSessionAction?.('delete', { id: ses.id }).then(() => loadStorage()); }) },
                ];
            } },
        ...(sysinteraction ? [{ key: 'sysinteraction', title: 'Взаимодействие с системой', icon: 'sysinteraction', c: 'c2',
            items: [
                { id: 'orchestrator', t: 'Оркестратор', s: sysinteraction.enabled ? 'ак��ивен' : 'выключен', on: sysinteraction.enabled, data: sysinteraction.orchestrator || {} },
                ...(sysinteraction.agents || []).map(a => ({ id: a.id, t: a.name || a.id, s: `${(a.skills || []).length}/5 скиллов`, on: true, data: a })),
            ],
            add: true, addFn: () => { showPage('settings'); showSettingsPage('sec-tools'); flashStatus('Настройка инструментов — вкладка «Инструменты»'); },
            itemActions: a => {
                const acts = [];
                if (a.id === 'orchestrator') {
                    acts.push({ label: a.on ? 'Выключить' : 'Включить', cls: a.on ? '' : 'on', act: () => { fetch(`${API_BASE}/api/sysinteraction`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !a.on }) }).then(() => loadStorage()); } });
                } else {
                    acts.push({ label: 'Удалить', cls: 'danger', act: () => amtConfirm({ title: 'Удалить агента?', text: 'Агент и его скиллы будут удалены.' }).then(ok => { if (ok) fetch(`${API_BASE}/api/sysinteraction`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ delete_agent: a.id }) }).then(() => loadStorage()); }) });
                }
                return acts;
            } }] : []),
    ];

    storageSections.innerHTML = sections.map(sec => {
        const icon = `<div class="ss-icon ${sec.c}">${svgIcon(sec.icon)}</div>`;
        const addBtn = sec.add ? `<button class="ss-add" data-add="${sec.key}">＋ Добавить</button>` : '';
        const clearBtn = sec.clearAll ? `<button class="ss-clear" data-clear="${sec.key}" title="${sec.clearAll.label}">Очистить всё</button>` : '';
        // Фолдеры из localStorage
        const folders = JSON.parse(localStorage.getItem('amt_folders_' + sec.key) || '[]');
        // Переприсваиваем items folder из localStorage (amt_item_folder_{key}_{id})
        sec.items.forEach(it => {
            if (it.id) {
                const stored = localStorage.getItem(`amt_item_folder_${sec.key}_${it.id}`);
                if (stored !== null) it.folder = stored;
            }
        });
        const folderBtn = `<button class="ss-folder" data-folder-key="${sec.key}" title="Создать папку"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> Папка</button>`;
        const folderHtml = folders.length ? `<div class="storage-folders">${folders.map(f => `<div class="storage-folder" data-folder="${escapeHtml(f)}" data-key="${sec.key}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> ${escapeHtml(f)} <button class="folder-del" data-key="${sec.key}" data-folder="${escapeHtml(f)}" title="Удалить папку">✕</button></div>`).join('')}</div>` : '';
        // Группируем items по папкам
        const itemFolder = (it) => (it.folder || '').trim();
        const grouped = {};
        sec.items.forEach(it => {
            const f = itemFolder(it) || 'Без папки';
            (grouped[f] = grouped[f] || []).push(it);
        });
        const itemsHtml = sec.items.length ? Object.entries(grouped).map(([folderName, items]) => {
            const isNamed = folderName !== 'Без папки';
            const labelSvg = `<svg class="sf-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>`;
            const list = items.slice(0, 40).map(it => {
                const acts = (sec.itemActions ? sec.itemActions(it) : []).map(a =>
                    `<button class="${a.cls || ''}" data-act="${escapeHtml(a.label)}" data-id="${escapeHtml(String(it.id || ''))}">${a.label}</button>`).join('');
                return `<div class="storage-item" data-key="${sec.key}" data-id="${escapeHtml(String(it.id || ''))}">
                    <div class="si-icon">${svgIcon(sec.icon)}</div>
                    <div class="si-body">
                        <div class="si-title">${escapeHtml(it.t || '—')}</div>
                        <div class="si-sub">${escapeHtml(it.s || '')}</div>
                    </div>
                    <div class="si-actions">${acts}</div>
                </div>`;
            }).join('');
            if (isNamed) {
                // Именованная папка: свёрнута по умолчанию, клик по заголовку раскрывает/скрывает.
                return `<div class="storage-folder-group">
                    <div class="storage-folder-label" data-folder="${escapeHtml(folderName)}" data-key="${sec.key}">${labelSvg} ${escapeHtml(folderName)} <span class="sf-count">${items.length}</span> <svg class="sf-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"></path></svg></div>
                    <div class="storage-folder-items collapsed">${list}</div>
                </div>`;
            }
            // «Без папки» — обычный заголовок, элементы видны сразу.
            return `<div class="storage-folder-group"><div class="storage-folder-label plain">${labelSvg} Без папки <span class="sf-count">${items.length}</span></div><div class="storage-folder-items">${list}</div></div>`;
        }).join('') : '<div class="storage-empty">Пусто</div>';
        return `<div class="storage-section">
            <div class="storage-section-head">${icon}<h3>${sec.title}</h3><span class="ss-count">${sec.items.length}</span>${clearBtn}${addBtn}${folderBtn}</div>
            ${folderHtml}
            <div class="storage-items">${itemsHtml}</div>
        </div>`;
    }).join('');

    // Кнопка создания папки
    document.querySelectorAll('.ss-folder').forEach(b => {
        b.addEventListener('click', async () => {
            const key = b.dataset.folderKey;
            const name = await amtPrompt('Имя папки:');
            if (!name?.trim()) return;
            const cur = JSON.parse(localStorage.getItem('amt_folders_' + key) || '[]');
            if (!cur.includes(name.trim())) cur.push(name.trim());
            localStorage.setItem('amt_folders_' + key, JSON.stringify(cur));
            loadStorage();
        });
    });
    // Удаление папки
    document.querySelectorAll('.folder-del').forEach(b => {
        b.addEventListener('click', e => {
            e.stopPropagation();
            const key = b.dataset.key, folder = b.dataset.folder;
            const cur = JSON.parse(localStorage.getItem('amt_folders_' + key) || '[]');
            const idx = cur.indexOf(folder);
            if (idx !== -1) cur.splice(idx, 1);
            localStorage.setItem('amt_folders_' + key, JSON.stringify(cur));
            loadStorage();
        });
    });
    // Раскрытие/сворачивание именованной папки по клику на заголовок
    document.querySelectorAll('.storage-folder-group > .storage-folder-label:not(.plain)').forEach(lb => {
        lb.style.cursor = 'pointer';
        lb.addEventListener('click', () => {
            const items = lb.nextElementSibling;
            if (!items || !items.classList.contains('storage-folder-items')) return;
            items.classList.toggle('collapsed');
            lb.parentElement.classList.toggle('expanded', !items.classList.contains('collapsed'));
        });
    });

    // Привязка: кнопки «добавить» + действия элементов
    document.querySelectorAll('.ss-add').forEach(b => {
        b.addEventListener('click', () => {
            const sec = sections.find(s => s.key === b.dataset.add);
            if (sec?.addFn) sec.addFn();
        });
    });
    document.querySelectorAll('.ss-clear').forEach(b => {
        b.addEventListener('click', () => {
            const sec = sections.find(s => s.key === b.dataset.clear);
            if (sec?.clearAll?.act) sec.clearAll.act();
        });
    });
    document.querySelectorAll('.storage-item .si-actions button').forEach(btn => {
        btn.addEventListener('click', e => {
            e.stopPropagation();
            const item = btn.closest('.storage-item');
            const key = item.dataset.key, id = item.dataset.id;
            const sec = sections.find(s => s.key === key);
            const it = sec.items.find(x => String(x.id) === id);
            const acts = sec.itemActions ? sec.itemActions(it) : [];
            const match = acts.find(a => a.label === btn.dataset.act);
            if (match) match.act();
        });
    });
    // MCP-серверы: асинхронная секция (данные с бэкенда)
    if (typeof renderMcpStorage === 'function') {
        const mcpWrap = document.createElement('div');
        mcpWrap.innerHTML = `
            <div class="storage-section">
                <div class="storage-section-head">
                    <div class="ss-icon c4">${svgIcon('plug')}</div>
                    <h3>MCP-серверы</h3>
                    <span class="ss-count" id="mcp-ss-count">…</span>
                    <button class="ss-add" data-mcp-add="1">＋ Добавить</button>
                </div>
                <div class="storage-items"><div id="mcp-storage-list" class="storage-items-mcp"></div></div>
            </div>`;
        storageSections.appendChild(mcpWrap.firstElementChild);
        document.querySelector('.storage-section-head [data-mcp-add]')?.addEventListener('click', () => {
            showPage('settings'); showSettingsPage('sec-mcp'); mcpShowAddForm();
        });
        // Загружаем список и обновляем счётчик
        fetch(`${API_BASE}/api/mcp/servers`).then(r => r.json()).then(sv => {
            const c = document.getElementById('mcp-ss-count');
            if (c) c.textContent = Array.isArray(sv) ? sv.length : 0;
        }).catch(() => {});
        renderMcpStorage();
    }
}

// Вкл/выкл агента и скилла (для хранилища)
async function toggleAgentEnabled(a) {
    const ag = agentsCache.find(x => x.id === a.id) || a.data;
    ag.enabled = ag.enabled === false;
    await fetch(`${API_BASE}/api/agents/${a.id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: ag.name, description: ag.description, systemPrompt: ag.systemPrompt, model: ag.model, skills: ag.skills || [], enabled: ag.enabled, group: ag.group }),
    });
    loadAgents(); loadStorage();
    flashStatus('Агент ' + (ag.enabled === false ? 'выключен' : 'включён'));
}
async function toggleSkillEnabled(s) {
    const sk = skillsCache.find(x => x.id === s.id) || s.data;
    sk.enabled = sk.enabled === false;
    await fetch(`${API_BASE}/api/skills/${s.id}`, {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: sk.name, description: sk.description, prompt: sk.prompt, enabled: sk.enabled, group: sk.group }),
    });
    loadAgents(); loadStorage();
    flashStatus('Скилл ' + (sk.enabled === false ? 'выключен' : 'включён'));
}
function fmtSize(b) {
    if (b == null) return '';
    if (b < 1024) return b + ' Б';
    if (b < 1024 * 1024) return (b / 1024).toFixed(1) + ' КБ';
    return (b / 1024 / 1024).toFixed(1) + ' МБ';
}

// ===== Универсальный стилизованный input (вместо системного prompt()) =====
// Возвращает Promise<string|null>. null = отмена/пустое.
function amtPrompt(title, defaultValue) {
    const modal = document.getElementById('amtInputModal');
    if (!modal) return Promise.resolve(prompt(title)); // fallback
    const t = document.getElementById('amtInputTitle');
    const lbl = document.getElementById('amtInputLabel');
    const val = document.getElementById('amtInputValue');
    const okBtn = document.getElementById('amtInputOk');
    const cancelBtn = document.getElementById('amtInputCancel');
    if (t) t.textContent = title || 'Введите значение';
    if (lbl) lbl.textContent = 'Значение';
    if (val) val.value = defaultValue || '';
    modal.classList.remove('hidden');
    if (val) { val.focus(); val.select(); }
    return new Promise(resolve => {
        let done = false;
        const finish = (result) => {
            if (done) return; done = true;
            modal.classList.add('hidden');
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            document.removeEventListener('keydown', onKey);
            resolve(result);
        };
        const onKey = (e) => { if (e.key === 'Enter') finish(val ? val.value : null); if (e.key === 'Escape') finish(null); };
        document.addEventListener('keydown', onKey);
        okBtn.onclick = () => finish(val ? val.value.trim() : null);
        cancelBtn.onclick = () => finish(null);
    });
}

// Переместить элемент в папку (для хранилища)
async function moveItemToFolder(sectionKey, item) {
    const folders = JSON.parse(localStorage.getItem('amt_folders_' + sectionKey) || '[]');
    if (!folders.length) {
        flashStatus('Сначала создайте папку (кнопка «Папка»)');
        return;
    }
    // Показываем список папок в заголовке, пользователь вводит номер
    const listText = folders.map((f, i) => `${i + 1}. ${f}`).join('\n') + '\n0. Без папки';
    const val = await amtPrompt(`Переместить «${item.t}»\n${listText}\n\nВведите номер папки:`, '');
    if (!val) return;
    const idx = parseInt(val.trim()) - 1;
    if (idx >= 0 && idx < folders.length) {
        localStorage.setItem(`amt_item_folder_${sectionKey}_${item.id}`, folders[idx]);
        flashStatus(`Перемещено в папку «${folders[idx]}»`);
        loadStorage();
    } else if (val.trim() === '0') {
        localStorage.removeItem(`amt_item_folder_${sectionKey}_${item.id}`);
        flashStatus('Убрано из папки');
        loadStorage();
    }
}

// ===== Универсальный стилизованный confirm (вместо системного confirm()) =====
// Возвращает Promise<boolean>. Заголовок/текст/подпись «Да» настраиваются.
function amtConfirm(opts) {
    const o = (typeof opts === 'string') ? { text: opts } : (opts || {});
    const title = o.title || 'Подтвердите';
    const text = o.text || '';
    const yesLabel = o.yesLabel || 'Удалить';
    const modal = document.getElementById('amtConfirmModal');
    if (!modal) return Promise.resolve(confirm(text)); // fallback
    const t = document.getElementById('amtConfirmTitle');
    const tx = document.getElementById('amtConfirmText');
    const yes = document.getElementById('amtConfirmYes');
    const no = document.getElementById('amtConfirmNo');
    if (t) t.textContent = title;
    if (tx) tx.textContent = text;
    if (yes) yes.textContent = yesLabel;
    modal.classList.remove('hidden');
    return new Promise(resolve => {
        const done = (val) => {
            modal.classList.add('hidden');
            yes?.removeEventListener('click', onYes);
            no?.removeEventListener('click', onNo);
            modal.removeEventListener('click', onOverlay);
            resolve(val);
        };
        function onYes() { done(true); }
        function onNo() { done(false); }
        function onOverlay(e) { if (e.target === modal) done(false); }
        yes?.addEventListener('click', onYes);
        no?.addEventListener('click', onNo);
        modal.addEventListener('click', onOverlay);
    });
}
// Экспорт всего в JSON (скачивание)
async function exportAllData() {
    const data = { exported_at: new Date().toISOString(), chats: chats, scenarios: loadScenarios() };
    try {
        data.agents = (await fetch(`${API_BASE}/api/agents`).then(r => r.json()));
        data.keys = (await fetch(`${API_BASE}/api/keys`).then(r => r.json()));
        data.sessions = (await fetch(`${API_BASE}/api/sessions`).then(r => r.json()));
        data.files = (await fetch(`${API_BASE}/api/files`).then(r => r.json()));
        data.memory = (await fetch(`${API_BASE}/api/memory`).then(r => r.json()));
    } catch {}
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `amt-export-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    flashStatus('Данные экспортированы');
}


function addMediaOpenBtn(wrap, label, onclick) {
    const btn = document.createElement('button');
    btn.className = 'media-open-btn';
    btn.textContent = label;
    btn.addEventListener('click', onclick);
    wrap.appendChild(btn);
}

function parseCustom(id) {
    const el = document.getElementById(id);
    if (!el || !el.value.trim()) return null;
    try { return JSON.parse(el.value); } catch { return null; }
}
// ===== МЕДИА / ФАЙЛЫ ПРЯМО В ЧАТЕ (токены [[GEN:...]] или [GEN:...]) =====
// LLM иногда пишет один bracket вместо двух — принимаем оба варианта.
const GEN_TOKEN_RE = /\[+GEN:([a-z_]+)\|([\s\S]+)\]\]/gi;
const GEN_TOKEN_RE_SINGLE = /\[GEN:([a-z_]+)\|([\s\S]+)\]/gi;
function _parseGenMatch(m) {
    const kind = m[1];
    const rest = m[2];
    if (kind === 'image') {
        const [aspect, prompt] = splitGenArgs(rest, 2);
        return { kind: 'image', prompt: prompt || rest, aspect: aspect || '1:1' };
    } else if (kind === 'video') {
        const [aspect, prompt] = splitGenArgs(rest, 2);
        return { kind: 'video', prompt: prompt || rest, aspect: aspect || '16:9' };
    } else if (kind === 'audio') {
        return { kind: 'audio', prompt: rest };
    } else if (kind === 'file') {
        // Разделяем только на ПЕРВОМ | — остаток (включая все последующие |) = содержимое
        const firstPipe = rest.indexOf('|');
        const ftype = firstPipe > 0 ? rest.slice(0, firstPipe).trim() : 'txt';
        const desc = firstPipe > 0 ? rest.slice(firstPipe + 1) : rest;
        return { kind: 'file', prompt: desc || rest, ftype: ftype || 'txt' };
    } else {
        return { kind, prompt: rest };
    }
}
function parseGenTokens(text) {
    const out = [];
    let m;
    GEN_TOKEN_RE.lastIndex = 0;
    while ((m = GEN_TOKEN_RE.exec(text))) {
        out.push(_parseGenMatch(m));
    }
    // fallback: single-bracket [GEN:kind|args] (rare LLM output)
    if (out.length === 0) {
        GEN_TOKEN_RE_SINGLE.lastIndex = 0;
        while ((m = GEN_TOKEN_RE_SINGLE.exec(text))) {
            out.push(_parseGenMatch(m));
        }
    }
    // remove tokens from display text
    const cleanText = text.replace(GEN_TOKEN_RE, '').replace(GEN_TOKEN_RE_SINGLE, '').trim();
    return { items: out, cleanText };
}
function splitGenArgs(s, n) {
    const parts = s.split('|');
    return parts;
}
async function processGenTokens(fullText) {
    const { items, cleanText } = parseGenTokens(fullText);
    if (!items.length) return;
    // обновить текст без токенов
    const chat = getCurrentChat();
    if (chat) {
        const last = chat.messages[chat.messages.length - 1];
        if (last && last.role === 'assistant') last.content = cleanText;
    }
    // обновить последний отрендеренный bot-элемент
    const botEls = chatMessages.querySelectorAll('.message.bot');
    const target = botEls[botEls.length - 1];
    if (target) {
        const contentEl = target.querySelector('.message-content');
        if (contentEl) contentEl.textContent = cleanText;
    }
    for (const it of items) {
        await renderGenInChat(it, target);
    }
}
async function renderGenInChat(item, hostEl) {
    const container = hostEl?.querySelector('.message-content') || chatMessages;
    const wrap = document.createElement('div');
    wrap.className = 'gen-inline';
    const kind = item.kind;
    const post = async (body) => fetch(`${API_BASE}/api/media/generate`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    }).then(r => r.json());
    // Если к сообщению был приложен файл — передаём первый image/видео-файл
    // в генерацию как ref_image_b64 (для вида image/video). Читает через
    // readFileAsBase64 (уже есть). Возвращает Promise<б64|''>.
    const attachedRefB64 = () => {
        if (!/^(image|video)$/.test(kind)) return Promise.resolve('');
        const att = _lastChatAttachments.find(a => a && a.file && /^image\//.test(a.type || ''));
        if (!att) return Promise.resolve('');
        return readFileAsBase64(att.file).catch(() => '');
    };
    if (kind === 'image') {
        wrap.innerHTML = '<div class="gen-inline-note">Генерирую картинку…</div>';
        container.appendChild(wrap);
        const ref = await attachedRefB64();
        const res = await post({ kind: 'image', prompt: item.prompt, size: '1024x1024', use_settings_key: true, save: true, paths: buildPathsObj(),
                                 ...(ref ? { ref_image_b64: ref } : {}) });
        wrap.innerHTML = '';
        if (res.ok && (res.b64 || res.url)) {
            const img = document.createElement('img');
            img.className = 'gen-inline-img';
            img.src = res.b64 ? b64ToDataUrl(res.b64, res.mime) : res.url;
            img.addEventListener('click', () => { if (window.openMediaOverlay) window.openMediaOverlay('image', img.src); });
            wrap.appendChild(img);
            addMediaOpenBtn(wrap, '🔍 Открыть', () => { if (window.openMediaOverlay) window.openMediaOverlay('image', img.src); });
            addMediaDownload(wrap, res, 'картинка');
        } else {
            wrap.innerHTML = `<div class="gen-inline-err">Ваш ключ не поддерживает картинки. Укажите другой (Настройки → Медиа-ключи): ${escapeHtml(res.error || '')}</div>`;
        }
    } else if (kind === 'audio') {
        wrap.innerHTML = '<div class="gen-inline-note">Генерирую голос…</div>';
        container.appendChild(wrap);
        const res = await post({ kind: 'audio', prompt: item.prompt, use_settings_key: true, save: true, paths: buildPathsObj() });
        wrap.innerHTML = '';
        if (res.ok && res.b64) {
            const a = document.createElement('audio');
            a.controls = true; a.className = 'gen-inline-audio';
            a.src = b64ToDataUrl(res.b64, res.mime || 'audio/mpeg');
            wrap.appendChild(a);
            addMediaOpenBtn(wrap, '▶ Прослушать', () => { if (window.openMediaOverlay) window.openMediaOverlay('audio', a.src); });
            addMediaDownload(wrap, res, 'голос');
        } else {
            wrap.innerHTML = `<div class="gen-inline-err">Ключ не поддерживает голос. Укажите другой: ${escapeHtml(res.error || '')}</div>`;
        }
    } else if (kind === 'video') {
        wrap.innerHTML = `<div class="gen-inline-note">Генерирую видео (${item.aspect})…</div>`;
        container.appendChild(wrap);
        const refV = await attachedRefB64();
        const res = await post({ kind: 'video', prompt: item.prompt, aspect_ratio: item.aspect || '16:9', duration: '5', use_settings_key: true, save: true, paths: buildPathsObj(),
                                 ...(refV ? { ref_image_b64: refV } : {}) });
        wrap.innerHTML = '';
        if (res.ok && res.url && !res.task_id) {
            // Прямой URL видео без task_id — сразу показываем
            const v = document.createElement('video');
            v.src = res.url;
            v.controls = true;
            v.className = 'gen-inline-video' + (item.aspect === '9:16' ? ' circle' : '');
            v.addEventListener('click', () => { if (window.openMediaOverlay) window.openMediaOverlay('video', res.url); });
            wrap.appendChild(v);
            addMediaOpenBtn(wrap, '⛶ Смотреть в плеере', () => { if (window.openMediaOverlay) window.openMediaOverlay('video', res.url); });
        } else if (res.ok && res.task_id) {
            const v = document.createElement('video');
            v.controls = true;
            v.className = 'gen-inline-video' + (item.aspect === '9:16' ? ' circle' : '');
            v.addEventListener('click', () => { if (v.src && window.openMediaOverlay) window.openMediaOverlay('video', v.src); });
            wrap.appendChild(v);
            addMediaOpenBtn(wrap, '⛶ Смотреть в плеере', () => { if (v.src && window.openMediaOverlay) window.openMediaOverlay('video', v.src); });
            const note = document.createElement('div');
            note.className = 'gen-inline-note'; note.textContent = 'Видео генерируется…';
            wrap.appendChild(note);
            pollVideoTaskChat(res.task_id, v, note, res.model_name || "");
        } else {
            wrap.innerHTML = `<div class="gen-inline-err">Ключ не поддерживает видео. Укажите другой: ${escapeHtml(res.error || '')}</div>`;
        }
    } else if (kind === 'file') {
        // файл: содержимое из токена уже реальный код/данные (LLM пишет его сам)
        const desc = item.prompt;
        const ftype = item.ftype || 'txt';
        let content = desc.trim();
        // Убрать markdown-обёртку (```...```) если ИИ её добавил
        if (content.startsWith('```')) {
            content = content.replace(/^```(?:json|javascript|js|python|py|html|css|csv|txt)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim();
        }
        // Для xlsx/pptx: если содержимое — не JSON, а описание → попросить ИИ переписать в JSON
        const looksLikeXlsxJson = ftype === 'xlsx' && content.startsWith('{') && content.includes('"sheets"');
        const looksLikePptxJson = ftype === 'pptx' && content.startsWith('{') && content.includes('"slides"');
        if ((ftype === 'xlsx' && !looksLikeXlsxJson) || (ftype === 'pptx' && !looksLikePptxJson)) {
            // Контент не в нужном формате — делаем второй запрос к ИИ с чёткой инструкцией
            const activeCore = activeCoreAgentList();
            let contentPrompt;
            if (ftype === 'xlsx') {
                contentPrompt = `По запросу: "${desc}" создай содержимое Excel. ` +
                    `Верни ТОЛЬКО валидный JSON: {"sheets":[{"name":"Лист","rows":[["Кол1","Кол2"],["знач1","знач2"]]}]} ` +
                    `Без пояснений, без markdown.`;
            } else {
                contentPrompt = `По запросу: "${desc}" создай презентацию. ` +
                    `Верни ТОЛЬКО валидный JSON: {"slides":[{"title":"Заголовок","body":"Текст"},...]} ` +
                    `Без пояснений, без markdown.`;
            }
            const chatBody = {
                message: contentPrompt,
                history: [],
                settings: toBackendSettings(buildSettingsFromInputs()),
                core_agents: activeCore,
            };
            if (currentKeyId) chatBody.key_id = currentKeyId;
            if (currentSystemPromptOverride) chatBody.systemPromptOverride = currentSystemPromptOverride;
            const aiRes = await fetch(`${API_BASE}/api/chat`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(chatBody),
            }).then(r => r.json());
            content = (aiRes.response || '').trim();
            if (content.startsWith('```')) {
                content = content.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '').trim();
            }
        }
        // Чистое имя файла: desc для xlsx/pptx — это JSON-спецификация, не заголовок
        let fileTitle;
        if ((ftype === 'xlsx' && (looksLikeXlsxJson || (content.startsWith('{') && content.includes('"sheets"')))) ||
            (ftype === 'pptx' && (looksLikePptxJson || (content.startsWith('{') && content.includes('"slides"'))))) {
            fileTitle = ftype === 'xlsx' ? 'Excel' : 'Презентация';
        } else {
            // Для кода/текста: первые 40 символов описания — нормально
            fileTitle = desc.slice(0, 40);
        }
        const g = await fetch(`${API_BASE}/api/filegen/generate`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filetype: ftype, content, title: fileTitle }),
        }).then(r => r.json());
        container.appendChild(wrap);
        if (g.status === 'ok') {
            const bytes = Uint8Array.from(atob(g.b64), c => c.charCodeAt(0));
            const blob = new Blob([bytes], { type: g.mime || 'application/octet-stream' });
            const url = URL.createObjectURL(blob);
            // File card (как прикреплённый файл: иконка + имя + размер, клик = скачать)
            const iconSvg = '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="M8 4h8l4 4v12a2 2 0 01-2 2H8a2 2 0 01-2-2V6a2 2 0 012-2z" fill="rgba(59,130,246,0.15)"/><path d="M16 4v4h4"/><path d="M10 13h4M10 17h4" stroke-linecap="round"/></svg>';
            const sizeLabel = g.size < 1024 ? g.size + ' B' : g.size < 1048576 ? (g.size / 1024).toFixed(1) + ' KB' : (g.size / 1048576).toFixed(1) + ' MB';
            wrap.innerHTML = `<div class="gen-file-card"><div class="gen-file-card-icon">${iconSvg}</div><div class="gen-file-card-info"><span class="gen-file-card-name">${escapeHtml(g.filename)}</span><span class="gen-file-card-size">${sizeLabel}</span></div></div>`;
            wrap.querySelector('.gen-file-card').addEventListener('click', () => {
                const a = document.createElement('a');
                a.href = url;
                a.download = g.filename;
                a.click();
            });
            setTimeout(() => URL.revokeObjectURL(url), 120000);
        } else {
            const errMsg = g.message || g.status || 'неизвестная ошибка';
            console.error('[filegen] Error:', g);
            wrap.innerHTML = `<div class="gen-inline-err">Ошибка файла: ${escapeHtml(errMsg)}<br><small style="opacity:0.6">Данные: ${escapeHtml(ftype)} · ${content.length} символов</small></div>`;
        }
    }
}
async function pollVideoTaskChat(taskId, videoEl, noteEl, modelName = "") {
    const MAX_POLLS = 60; // 60 × 5s = 5 минут (Agnes-видео генерируется 2-5 мин)
    const POLL_MS = 5000;
    for (let i = 0; i < MAX_POLLS; i++) {
        await new Promise(r => setTimeout(r, POLL_MS));
        let st;
        try {
            const body = { task_id: taskId, use_settings_key: true };
            if (modelName) body.model_name = modelName;
            st = await fetch(`${API_BASE}/api/media/task`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            }).then(x => x.json());
        } catch (netErr) {
            // Сетевая ошибка — не считаем это попыткой, просто повторяем
            if (noteEl) noteEl.textContent = 'Генерация видео… (нет связи с сервером, повторяю)';
            i--;
            continue;
        }
        if (st.status === 'succeed' && st.url) {
            videoEl.src = st.url;
            if (noteEl) noteEl.textContent = '';
            return;
        }
        if (st.status === 'completed') {
            // Agnes: задача завершена. Если есть URL — показать, иначе честная подсказка.
            if (st.url) { videoEl.src = st.url; if (noteEl) noteEl.textContent = ''; return; }
            if (noteEl) noteEl.textContent = 'Видео готово на стороне провайдера (задача ' + taskId + '). Ссылка на скачивание не доступна автоматически — проверьте учётную запись провайдера.';
            return;
        }
        if (st.status === 'failed' || st.status === 'error') {
            if (noteEl) noteEl.textContent = 'Ошибка видео: ' + (st.error || st.status);
            return;
        }
        // queued / processing — обновляем прогресс
        if (noteEl) {
            const prog = st.progress && st.progress !== '' ? ` (${st.progress})` : '';
            noteEl.textContent = 'Генерация видео…' + prog;
        }
    }
    if (noteEl) noteEl.textContent = 'Таймаут видео (5 мин). Видео может ещё генерироваться на стороне провайдера — проверьте учётную запись или повторите запрос.';
}

// ===== «Создать чат» с выбранным режимом =====
async function startChatWithMode() {
    if (!chatModeResult) return;
    const mode = chatModeSelect?.value || 'plain';
    const persId = chatModePersonality?.value;
    let agentId = '';
    if (mode === 'personality' || mode === 'agents_only') {
        if (mode === 'personality' && !persId) {
            chatModeResult.textContent = 'Выберите личность из списка (создайте её на этой же странице)';
            chatModeResult.className = 'test-result error';
            return;
        }
        agentId = mode === 'personality' ? persId : persId;
    }
    // создаём новый чат
    const chat = createNewChat();
    currentChatId = chat.id;
    chatTitle.value = chat.title;
    renderGroupSelect();
    if (agentId) { currentAgentId = agentId; if (chatAgentSelect) chatAgentSelect.value = agentId; }
    saveChats(); saveCurrentChatId(); renderChatsList(); clearHistory();
    showPage('chat');
    const labels = { plain: 'без личности', personality: `с личностью «${agentsCache.find(a=>a.id===agentId)?.name||agentId}»`,
        skills_only: 'только со скиллами', agents_only: 'только с агентами' };
    chatModeResult.textContent = 'Чат создан ' + labels[mode];
    chatModeResult.className = 'test-result success';
    setTimeout(() => chatModeResult.textContent = '', 3000);
}

// ===== Мульти-API-ключи =====
async function loadKeys() {
    try {
        const res = await fetch(`${API_BASE}/api/keys`);
        const data = await res.json();
        _knownKeys = data.keys || [];
        _knownActiveKey = data.activeKeyId || '';
        renderKeys(_knownKeys, data.activeKeyId);
        if (keyRoundRobin) keyRoundRobin.checked = data.roundRobin;
    } catch {}
}

// Есть ли хоть один ключ в многоключевом хранилище (для отправки без поля на странице настроек)
let _knownKeys = [];
let _knownActiveKey = '';
async function hasUsableKey() {
    try {
        const res = await fetch(`${API_BASE}/api/keys`);
        const data = await res.json();
        _knownKeys = data.keys || [];
        _knownActiveKey = data.activeKeyId || '';
        return _knownKeys.some(k => k.hasKey);
    } catch {
        return _knownKeys.some(k => k.hasKey);
    }
}

async function isMcpWriterAvailable() {
    try {
        const res = await fetch(`${API_BASE}/api/mcp/servers`);
        const servers = await res.json();
        if (!Array.isArray(servers)) return false;
        return servers.some(s => s.id === 'writer' && s.enabled !== false);
    } catch {
        return false;
    }
}

function renderKeys(keys, activeId) {
    if (!keyList) return;
    keyList.innerHTML = '';
    keys.forEach(k => {
        const div = document.createElement('div');
        div.className = 'entity-item';
        const active = k.id === activeId;
        const kletter = (k.label || k.id || '?').trim().charAt(0).toUpperCase() || '?';
        const colors = ['c1','c2','c3','c4','c5','c6'];
        const kh = Array.from(k.label || k.id || '').reduce((x, ch) => (x + ch.charCodeAt(0)) % 997, 0);
        const kcolor = colors[kh % colors.length];
        div.innerHTML = `
            <span class="entity-badge ${kcolor}">${escapeHtml(kletter)}</span>
            <div class="entity-main">
                <span class="entity-title">${escapeHtml(k.label || k.id)}
                    ${active ? '<span class="entity-active">активен</span>' : ''}
                    ${k.cooldownUntil && k.cooldownUntil > Date.now()/1000 ? '<span class="entity-cool">кулдаун</span>' : ''}
                </span>
                <span class="entity-sub">${escapeHtml(k.baseUrl || '')} • ${escapeHtml(k.model || '')} • ключ: ${k.hasKey ? 'есть' : 'нет'}</span>
            </div>
            <div class="entity-actions">
                ${active ? '' : `<button class="ghost" data-act="act" data-id="${k.id}">Активировать</button>`}
                <button class="ghost danger" data-act="del" data-id="${k.id}">Удалить</button>
            </div>
        `;
        keyList.appendChild(div);
    });
    keyList.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', async () => {
        const id = b.dataset.id;
        if (b.dataset.act === 'del') {
            await fetch(`${API_BASE}/api/keys/${id}`, { method: 'DELETE' });
        } else {
            await fetch(`${API_BASE}/api/keys/${id}/activate`, { method: 'POST' });
            flashStatus('Ключ активирован');
        }
        loadKeys();
    }));
    renderKeySelects(keys);
}

// Заполнить селекты выбора ключа (в шапке чата + в модалке сессии)
function renderKeySelects(keys) {
    if (chatKeySelect) {
        const prev = chatKeySelect.value;
        chatKeySelect.innerHTML = '<option value="">Активный ключ</option>';
        (keys || []).forEach(k => {
            const o = document.createElement('option');
            o.value = k.id;
            o.textContent = k.label || k.id;
            chatKeySelect.appendChild(o);
        });
        chatKeySelect.value = prev || currentKeyId;
    }
    if (sessionKey) {
        const prev = sessionKey.value;
        sessionKey.innerHTML = '<option value="">Использовать активный</option>';
        (keys || []).forEach(k => {
            const o = document.createElement('option');
            o.value = k.id;
            o.textContent = k.label || k.id;
            sessionKey.appendChild(o);
        });
        sessionKey.value = prev || '';
    }
    syncKeyMsel();
}

async function addKey() {
    const payload = {
        label: keyLabel?.value.trim(),
        baseUrl: keyBaseUrl?.value.trim(),
        apiKey: keyApi?.value.trim(),
        model: keyModel?.value.trim(),
        temperature: parseFloat(keyTemp?.value) || 0.7,
        makeActive: false,
    };
    await fetch(`${API_BASE}/api/keys`, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
    });
    keyLabel.value = keyBaseUrl.value = keyApi.value = keyModel.value = '';
    loadKeys();
    flashStatus('Ключ добавлен');
}

async function setRoundRobin() {
    const on = keyRoundRobin ? keyRoundRobin.checked : false;
    await fetch(`${API_BASE}/api/keys/roundrobin?enabled=${on}`, { method: 'POST' });
    flashStatus(on ? 'Round-robin включён' : 'Round-robin выключён');
}

// ===== Textarea auto-height =====
function adjustTextareaHeight() {
    messageInput.style.height = 'auto';
    messageInput.style.height = messageInput.scrollHeight + 'px';
}

// ===== Test connection =====
async function testConnection() {
    if (!testResult) return;
    testResult.textContent = 'Проверяю...';
    testResult.className = 'test-result';
    setStatus('connecting');

    const payload = toBackendSettings(buildSettingsFromInputs());
    // Передаём ключ из поля настроек — иначе бэкенд не узнает про него
    payload.apiKey = (apiKeyInput?.value || '').trim();

    try {
        const res = await fetch(`${API_BASE}/api/test-connection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ settings: payload })
        });
        const data = await res.json();
        if (data.ok) {
            testResult.textContent = data.message || 'Подключение работает';
            testResult.classList.add('success');
            settings = buildSettingsFromInputs();
            saveSettings();
            setStatus('connected');
        } else {
            testResult.textContent = data.message || 'Не удалось подключиться';
            testResult.classList.add('error');
            setStatus('error');
        }
    } catch (e) {
        testResult.textContent = 'Бэкенд недоступен. Запустите: python backend/main.py';
        testResult.classList.add('error');
        setStatus('error');
    }
}

// ===== Отсутствующие функции (ранее вызывались, но не определялись → ReferenceError ломал инициализацию) =====

// Конвертирует base64-строку в data-URL для вставки в <img>/<audio>/<video>.
function b64ToDataUrl(b64, mime) {
    if (!b64) return '';
    const clean = b64.replace(/\s+/g, '').replace(/^data:[^,]+,/, '');
    return `data:${mime || 'application/octet-stream'};base64,${clean}`;
}

// Добавляет кнопку «Скачать» под медиа-элементом в чате.
function addMediaDownload(wrap, res, label) {
    if (!res) return;
    const a = document.createElement('a');
    a.className = 'media-download-btn';
    a.textContent = '⬇ Скачать';
    a.title = `Скачать ${label}`;
    // Прямой URL (если есть) — используем href, иначе собираем blob из b64
    if (res.url) {
        a.href = res.url;
        a.target = '_blank';
        a.download = '';
    } else if (res.b64) {
        const bytes = Uint8Array.from(atob(res.b64.replace(/^data:[^,]+,/,'')), c => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: res.mime || 'application/octet-stream' });
        a.href = URL.createObjectURL(blob);
        a.download = res.filename || `amt-${Date.now()}`;
    } else {
        return;
    }
    wrap.appendChild(a);
}

// Показываем/скрываем композер в зависимости от того, есть ли в чате сообщения
// (если чат пуст — показываем welcome, если есть — показываем композер).
function toggleComposerVisibility() {
    const inputBox = document.querySelector('.chat-input-box');
    const toolPicker = document.getElementById('toolPicker');
    const chat = getCurrentChat();
    if (!inputBox) return;
    // Композер всегда видим (можно писать даже в пустом чате)
    if (toolPicker) toolPicker.classList.add('hidden');
}

// Заполняем селекты личности (ключ/агент/скилл) из кэшей.
function fillPersonalitySelects() {
    // persKey — селект ключа
    if (persKey) {
        const prev = persKey.value;
        persKey.innerHTML = '<option value="">Активный</option>';
        (_knownKeys || []).forEach(k => {
            const o = document.createElement('option');
            o.value = k.id; o.textContent = k.label || k.id;
            persKey.appendChild(o);
        });
        persKey.value = prev || '';
    }
    // persAgentsList — чипы агентов
    if (persAgentsList) {
        persAgentsList.innerHTML = '';
        agentsCache.forEach(a => {
            const chip = document.createElement('label');
            chip.className = 'picker-chip' + (a.enabled === false ? ' dimmed' : '');
            chip.dataset.id = a.id;
            chip.innerHTML = `<input type="checkbox"> <span>${escapeHtml(a.name || a.id)}${a.enabled === false ? ' (выкл)' : ''}</span>`;
            chip.querySelector('input').addEventListener('change', e => chip.classList.toggle('selected', e.target.checked));
            persAgentsList.appendChild(chip);
        });
        if (!agentsCache.length) persAgentsList.innerHTML = '<div class="picker-empty">Нет агентов</div>';
    }
    // persSkillsList — чипы скиллов
    if (persSkillsList) {
        persSkillsList.innerHTML = '';
        skillsCache.forEach(s => {
            const chip = document.createElement('label');
            chip.className = 'picker-chip' + (s.enabled === false ? ' dimmed' : '');
            chip.dataset.id = s.id;
            chip.innerHTML = `<input type="checkbox"> <span>${escapeHtml(s.name || s.id)}${s.enabled === false ? ' (выкл)' : ''}</span>`;
            chip.querySelector('input').addEventListener('change', e => chip.classList.toggle('selected', e.target.checked));
            persSkillsList.appendChild(chip);
        });
        if (!skillsCache.length) persSkillsList.innerHTML = '<div class="picker-empty">Нет скиллов</div>';
    }
}

// Собираем личность из полей и отправляем на создание (backend создаст сессию-личность).
async function createPersonality() {
    const name = (persName?.value || '').trim();
    if (!name) { flashStatus('Введите имя личности'); return; }
    const selectedAgents = [];
    const selectedSkills = [];
    if (persAgentsList) {
        persAgentsList.querySelectorAll('.picker-chip.selected').forEach(c => selectedAgents.push(c.dataset.id));
    }
    if (persSkillsList) {
        persSkillsList.querySelectorAll('.picker-chip.selected').forEach(c => selectedSkills.push(c.dataset.id));
    }
    const payload = {
        name,
        agent_id: (persUseAgent?.checked && selectedAgents.length) ? selectedAgents[0] : '',
        skills: (persUseSkills?.checked) ? selectedSkills : [],
        model: (persUseModel?.checked && persModel) ? persModel.value.trim() : '',
        key_id: (persUseKey?.checked && persKey) ? persKey.value : '',
        parallel: parseInt(persParallel?.value) || 1,
        prompt: (persPrompt?.value || '').trim(),
        orch: persOrch?.value || 'base',
        orchRules: (persOrchCustom?.value || '').trim(),
    };
    try {
        const res = await fetch(`${API_BASE}/api/sessions`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (data.status === 'created') {
            flashStatus('Личность «' + name + '» создана');
        } else {
            flashStatus('Личность создана: ' + (name));
        }
        // очищаем форму
        if (persName) persName.value = '';
        if (persAgentsList) persAgentsList.querySelectorAll('.picker-chip').forEach(c => { c.classList.remove('selected'); const cb = c.querySelector('input'); if (cb) cb.checked = false; });
        if (persSkillsList) persSkillsList.querySelectorAll('.picker-chip').forEach(c => { c.classList.remove('selected'); const cb = c.querySelector('input'); if (cb) cb.checked = false; });
    } catch (e) {
        flashStatus('Бэкенд недоступен: ' + (e.message || e));
    }
}

// Предпросмотр составленного системного промпта личности.
function previewPersonality() {
    if (!personalityPreview) return;
    const parts = [];
    const name = (persName?.value || '').trim();
    if (name) parts.push(`Личность: ${name}`);
    if (persUseKey?.checked && persKey?.value) parts.push('Ключ: ' + (_knownKeys.find(k => k.id === persKey.value)?.label || persKey.value));
    if (persUseModel?.checked && persModel?.value.trim()) parts.push('Модель: ' + persModel.value.trim());
    if (persUseAgent?.checked && persAgentsList) {
        const sel = persAgentsList.querySelectorAll('.picker-chip.selected');
        if (sel.length) parts.push('Агенты: ' + [...sel].map(c => c.dataset.id).join(', '));
    }
    if (persUseSkills?.checked && persSkillsList) {
        const sel = persSkillsList.querySelectorAll('.picker-chip.selected');
        if (sel.length) parts.push('Скиллы: ' + [...sel].map(c => c.dataset.id).join(', '));
    }
    if (persUseOrch?.checked && persOrch?.value) {
        const orchVal = persOrch.value;
        parts.push('Оркестратор: ' + (orchVal === 'base' ? 'базовый' : 'свой'));
        if (orchVal === 'custom' && persOrchCustom?.value.trim()) parts.push('Правила: ' + persOrchCustom.value.trim());
    }
    if (persPrompt?.value.trim()) parts.push('Доп. промпт: ' + persPrompt.value.trim());
    if (parts.length) {
        personalityPreview.textContent = parts.join(' · ');
        personalityPreview.className = 'personality-preview success';
    } else {
        personalityPreview.textContent = 'Ничего не выбрано — будет стандартный чат без личности.';
        personalityPreview.className = 'personality-preview';
    }
}

// ===== Главная страница: создать чат с выбранными параметрами =====
async function createHomeChat() {
    const type = homeChatType;
    // Собираем параметры
    let agentId = '';
    let skills = [];
    let model = '';
    let baseUrl = '';
    let systemPrompt = '';
    let orch = '';
    let orchRules = '';
    let keyId = '';

    if (type === 'personality') {
        if (homeAgentSel) agentId = homeAgentSel.value || '';
        if (homeSkillsPicker) {
            homeSkillsPicker.querySelectorAll('.picker-chip.selected').forEach(c => skills.push(c.dataset.id));
        }
        if (homeOrchSel) orch = homeOrchSel.value || '';
        if (homeOrchRules) orchRules = homeOrchRules.value.trim() || '';
    } else if (type === 'custom') {
        if (homeSystemPrompt) systemPrompt = homeSystemPrompt.value.trim() || '';
    }
    if (homeModelInput) model = homeModelInput.value.trim() || '';
    if (homeBaseUrlInput) baseUrl = homeBaseUrlInput.value.trim() || '';
    if (homeKeySel) keyId = homeKeySel.value || '';

    // Создаём новый чат
    const chat = createNewChat();
    currentChatId = chat.id;
    if (chatTitle) chatTitle.value = chat.title;
    renderGroupSelect();
    await saveChats();
    await saveCurrentChatId();

    // Применяем параметры к текущему чату
    if (agentId) {
        currentAgentId = agentId;
        if (chatAgentSelect) chatAgentSelect.value = agentId;
        // Если агент несёт модель/температуру — обновим локальные поля
        const a = agentsCache.find(x => x.id === agentId);
        if (a) {
            if (a.model && !model) model = a.model;
            if (a.temperature != null) { if (temperatureInput) temperatureInput.value = a.temperature; if (tempValue) tempValue.textContent = a.temperature; }
            if (a.systemPrompt && !systemPrompt) systemPrompt = a.systemPrompt;
        }
    }
    // Скиллы → добавляем к выбранному агенту (или храним отдельно)
    if (skills.length && agentId) {
        const a = agentsCache.find(x => x.id === agentId);
        if (a) {
            const merged = Array.from(new Set([...(a.skills || []), ...skills]));
            a.skills = merged;
        }
    }
    if (model && modelInput) modelInput.value = model;
    if (baseUrl && baseUrlInput) baseUrlInput.value = baseUrl;
    if (systemPrompt && systemPromptInput) systemPromptInput.value = systemPrompt;
    if (keyId) {
        currentKeyId = keyId;
        if (chatKeySelect) chatKeySelect.value = keyId;
    }

    // Переходим в чат
    renderChatsList();
    chatMessages.innerHTML = `
        <div class="welcome-screen" id="welcomeScreen">
            <div class="welcome-icon">AMT</div>
            <h3>Чат создан</h3>
            <p>${type === 'personality' ? 'С личностью' : type === 'custom' ? 'С вашим промптом' : 'Стандартный чат'} — напиши сообщение.</p>
        </div>
    `;
    updateTokenCounter();
    toggleComposerVisibility();
    setStatus('idle');
    showPage('chat');
    flashStatus('Чат создан');
}

// ===== Главная страница: сбросить форму =====
function resetHomeForm() {
    homeChatType = 'plain';
    applyHomeType('plain');
    if (homeAgentSel) homeAgentSel.value = '';
    if (homeSkillsPicker) homeSkillsPicker.querySelectorAll('.picker-chip').forEach(c => { c.classList.remove('selected'); const cb = c.querySelector('input'); if (cb) cb.checked = false; });
    if (homeOrchSel) homeOrchSel.value = '';
    if (homeOrchRules) homeOrchRules.value = '';
    if (homeSystemPrompt) homeSystemPrompt.value = '';
    if (homeModelInput) homeModelInput.value = '';
    if (homeBaseUrlInput) homeBaseUrlInput.value = '';
    if (homeKeySel) homeKeySel.value = '';
    flashStatus('Форма сброслена');
}
