// ===== Event listeners =====
document.addEventListener('DOMContentLoaded', async () => {
    // Защита: если любой из await-вызовов бросит ошибку,
    // все последующие addEventListener всё равно зарегистрируются.
    try {
        await loadChats();
        await loadGroups();
        await loadSettings();
        await loadCurrentChatId();
    } catch (e) {
        console.error('[init] load error:', e);
    }

    // Инициализировать мультиселект системных промптов
    syncPromptMsel();
    if (chatPromptCustom) {
        chatPromptCustom.addEventListener('input', () => {
            // если пользователь ввёл свой текст → сбросить выбор из списка
            if (chatPromptCustom.value.trim()) {
                selectedPromptIds = [];
                if (_promptMsel) _promptMsel.set(selectedPromptIds);
            }
            applyPromptSelection();
        });
    }

    // Открываем чат — ошибки не должны блокировать регистрацию слушателей
    try {
        if (chats.length > 0) {
            await openChat(chats[0]);
        } else {
            await startNewChat();
        }
        await renderChatsList();
    } catch (e) {
        console.error('[init] chat open error:', e);
    }

    // КРИТИЧЕСКИЕ UI-слушатели — регистрируем ПЕРВЫМИ, до любого
    // кода который может бросить ошибку (fetch, render, etc).
    // Композер: кнопка инструментов
    if (composerToolsBtn && composerToolsPop) {
        composerToolsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = composerToolsPop.classList.toggle('hidden');
            composerToolsBtn.classList.toggle('open', !open);
        });
        document.addEventListener('click', (e) => {
            if (!composerToolsPop.classList.contains('hidden') && !composerToolsPop.contains(e.target) && e.target !== composerToolsBtn) {
                composerToolsPop.classList.add('hidden');
                composerToolsBtn.classList.remove('open');
            }
        });
    }
    
    // Кнопка Help
    const composerHelpBtn = document.getElementById('composerHelpBtn');
    if (composerHelpBtn) {
        composerHelpBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (window.AMTHelp) {
                window.AMTHelp.show();
            }
        });
    }
    
    // Кнопки композера: attach, tool, web/thinker/jailbreak
    if (attachBtn) attachBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
    if (fileInput) fileInput.addEventListener('change', (e) => handleFileSelect(e.target.files));
    if (document.getElementById('toolBtn')) document.getElementById('toolBtn').addEventListener('click', (e) => { e.stopPropagation(); toggleToolPicker(); });
    if (webAgentToggle) webAgentToggle.addEventListener('click', () => {
        coreWebActive = !coreWebActive;
        webAgentToggle.classList.toggle('active', coreWebActive);
        if (coreWebActive && !currentAgentId) { currentAgentId = 'core_web'; if (chatAgentSelect) chatAgentSelect.value = 'core_web'; }
        if (!coreWebActive && currentAgentId === 'core_web') { currentAgentId = ''; if (chatAgentSelect) chatAgentSelect.value = ''; }
        syncAgentMselLabel();
    });
    if (thinkerToggle) thinkerToggle.addEventListener('click', () => {
        coreThinkerActive = !coreThinkerActive;
        thinkerToggle.classList.toggle('active', coreThinkerActive);
        if (coreThinkerActive && !currentAgentId) { currentAgentId = 'core_thinker'; if (chatAgentSelect) chatAgentSelect.value = 'core_thinker'; }
        if (!coreThinkerActive && currentAgentId === 'core_thinker') { currentAgentId = ''; if (chatAgentSelect) chatAgentSelect.value = ''; }
        syncAgentMselLabel();
    });
    if (jailbreakToggle) jailbreakToggle.addEventListener('click', () => {
        coreJailbreakActive = !coreJailbreakActive;
        jailbreakToggle.classList.toggle('active', coreJailbreakActive);
        if (coreJailbreakActive && !currentAgentId) { currentAgentId = 'core_jailbreak'; if (chatAgentSelect) chatAgentSelect.value = 'core_jailbreak'; }
        if (!coreJailbreakActive && currentAgentId === 'core_jailbreak') { currentAgentId = ''; if (chatAgentSelect) chatAgentSelect.value = ''; }
        syncAgentMselLabel();
    });
    if (sysInteractionToggle) sysInteractionToggle.addEventListener('click', () => {
        sysInteractionActive = !sysInteractionActive;
        sysInteractionToggle.classList.toggle('active', sysInteractionActive);
    });
    // Кнопка ⋯ (опции чата)
    if (typeof toggleChatActions === 'function') {
        const moreBtn = document.getElementById('chatMoreBtn');
        if (moreBtn) moreBtn.addEventListener('click', toggleChatActions);
    }
    // Поиск по чатам
    if (chatSearchClose) chatSearchClose.addEventListener('click', closeSearchResults);
    if (chatSearchInput) {
        chatSearchInput.addEventListener('input', doChatSearch);
        chatSearchInput.addEventListener('keydown', e => { if (e.key === 'Escape') closeSearchResults(); });
    }
    // Отправка / стоп
    sendBtn.addEventListener('click', sendMessage);
    stopBtn.addEventListener('click', stopStreaming);
    messageInput.addEventListener('input', adjustTextareaHeight);
    
    // Подсказки команд при вводе /
    let suggestionsEl = null;
    messageInput.addEventListener('input', async () => {
        const value = messageInput.value;
        if (value.startsWith('/')) {
            const suggestions = await window.AMTCommands.showCommandSuggestions(value);
            if (suggestions.length > 0) {
                if (!suggestionsEl) {
                    suggestionsEl = document.createElement('div');
                    suggestionsEl.className = 'command-suggestions';
                    messageInput.parentElement.appendChild(suggestionsEl);
                }
                suggestionsEl.innerHTML = suggestions.map(s => `
                    <div class="command-suggestion-item" data-cmd="${s.id}">
                        <div class="suggestion-label">${s.label}</div>
                        <div class="suggestion-desc">${s.description}</div>
                    </div>
                `).join('');
                suggestionsEl.classList.add('visible');
                
                // Обработчик выбора
                suggestionsEl.querySelectorAll('.command-suggestion-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const cmd = item.dataset.cmd;
                        messageInput.value = '/' + cmd + ' ';
                        messageInput.dispatchEvent(new Event('input'));
                        closeSuggestions();
                    });
                });
            } else {
                closeSuggestions();
            }
        } else {
            closeSuggestions();
        }
    });
    
    function closeSuggestions() {
        if (suggestionsEl) {
            suggestionsEl.classList.remove('visible');
            setTimeout(() => {
                if (suggestionsEl && !suggestionsEl.classList.contains('visible')) {
                    suggestionsEl.remove();
                    suggestionsEl = null;
                }
            }, 200);
        }
    }
    
    messageInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
        if (e.key === 'Escape' && suggestionsEl?.classList.contains('visible')) {
            closeSuggestions();
        }
    });
    // Навигация
    navLinks.forEach(a => {
        a.addEventListener('click', e => {
            e.preventDefault();
            showPage(a.dataset.page);
        });
    });
    newChatBtn.addEventListener('click', startNewChat);

    try {

    togglePass.addEventListener('click', () => {
        const showing = apiKeyInput.type === 'text';
        apiKeyInput.type = showing ? 'password' : 'text';
        togglePass.textContent = showing ? 'Показать' : 'Скрыть';
    });

    temperatureInput.addEventListener('input', () => {
        tempValue.textContent = temperatureInput.value;
    });

    // Авто-температура: при включении блокируем ручной слайдер
    function syncTempAuto() {
        temperatureInput.disabled = !!(autoTemp && autoTemp.checked);
        temperatureInput.style.opacity = temperatureInput.disabled ? '0.4' : '1';
    }
    if (autoTemp) {
        autoTemp.addEventListener('change', syncTempAuto);
        syncTempAuto();
    }

    saveSettingsBtn.addEventListener('click', async () => {
        await saveSettings();
        flashStatus('Настройки сохранены');
    });
    testConnectionBtn.addEventListener('click', testConnection);
    testModelsBtn.addEventListener('click', testModels);

    // Группы
    if (addGroupBtn) addGroupBtn.addEventListener('click', promptNewGroup);
    if (chatGroupSelect) chatGroupSelect.addEventListener('change', (e) => moveChatToGroup(e.target.value));
    // Переименование чата — по клику на заголовок (инпут)
    if (chatTitle) chatTitle.addEventListener('blur', renameCurrentChat);

    // Логи
    if (refreshLogsBtn) refreshLogsBtn.addEventListener('click', loadLogs);
    if (clearLogsBtn) clearLogsBtn.addEventListener('click', clearLogs);
    logFilterBtns.forEach(b => b.addEventListener('click', () => setLogFilter(b.dataset.filter)));
    if (dashTabs) dashTabs.querySelectorAll('.dash-tab').forEach(b => b.addEventListener('click', () => setDashTab(b.dataset.mode)));
    if (dashFilterChips) dashFilterChips.querySelectorAll('.chip').forEach(b => b.addEventListener('click', () => setDashFilter(b.dataset.dashfilter)));
    if (wipeMemoryBtn) wipeMemoryBtn.addEventListener('click', wipeMemory);

    // Композер: единая кнопка инструментов (заявлено в критическом блоке выше)
    // Файлы (заявлено в критическом блоке выше)
    // Вставка через Ctrl+V
    const msgInput = document.getElementById('messageInput');
    if (msgInput) msgInput.addEventListener('paste', handlePaste);

    // Оркестратор
    if (saveOrchBtn) saveOrchBtn.addEventListener('click', saveOrchConfig);
    if (orchHealthBtn) orchHealthBtn.addEventListener('click', showOrchHealth);
    loadOrchConfig();

    // Навигация по страницам настроек (внутренние табы)
    settingsSubnavLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const sec = link.dataset.sec;
            showSettingsPage(sec);
            // Ленивая инициализация: хоткеи + MCP
            if (sec === 'sec-hotkeys' && window.AMTHotkeys) {
                const hkContainer = document.getElementById('hotkeySettingsContainer');
                if (hkContainer && !hkContainer.dataset.rendered) {
                    window.AMTHotkeys.renderHotkeySettings(hkContainer);
                    hkContainer.dataset.rendered = '1';
                }
            }
            if (sec === 'sec-mcp' && typeof renderMcpSettings === 'function') {
                renderMcpSettings();
            }
            if (sec === 'sec-coding' && window.initCodingHelp) {
                window.initCodingHelp();
            }
        });
    });

    // Навигация по подстраницам Справки (docs)
    document.querySelectorAll('#docsSubnav a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            showDocsPage(link.dataset.docsSec);
        });
    });
    // Хаб расширений: кнопки
    const extRefreshBtn = document.getElementById('extRefreshBtn');
    if (extRefreshBtn) extRefreshBtn.addEventListener('click', refreshExtList);
    const extAddBtn = document.getElementById('extAddBtn');
    if (extAddBtn) extAddBtn.addEventListener('click', async () => {
        const hint = document.getElementById('extAddHint');
        const dirBox = document.getElementById('extDirBox');
        const dp = document.getElementById('extDirPath');
        if (hint) hint.style.display = 'block';
        if (dirBox) dirBox.style.display = 'block';
        // Показать реальный путь к каталогу расширений (из бэкенда)
        try {
            const r = await fetch(`${API_BASE}/api/extensions/list`);
            const d = await r.json();
            if (dp) dp.textContent = d.dir ? `Каталог расширений: ${d.dir}` : '';
        } catch { /* бэкенд недоступен */ }
        // Выбрать папку: в Electron — нативный диалог, в браузере — ввод пути вручную
        let srcDir = null;
        if (window.api && window.api.dialog && window.api.dialog.openDirectory) {
            const res = await window.api.dialog.openDirectory();
            srcDir = (res && typeof res === 'object') ? (res.canceled ? null : (res.path || null)) : (res || null);
        } else {
            srcDir = await amtPrompt('Путь к папке расширения (с manifest.json):', '');
        }
        if (!srcDir) return;
        const addRes = await fetch(`${API_BASE}/api/extensions/add`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_dir: srcDir }),
        }).then(r => r.json()).catch(() => ({ ok: false, error: 'Бэкенд недоступен' }));
        if (addRes.ok) {
            flashStatus(`Расширение добавлено: ${addRes.count ?? ''} всего в каталоге`);
            refreshExtList();
        } else {
            flashStatus(addRes.error || 'Не удалось добавить расширение');
        }
    });
    // Чейнджлог: проверить обновления
    const changelogRefreshBtn = document.getElementById('changelogRefreshBtn');
    if (changelogRefreshBtn) changelogRefreshBtn.addEventListener('click', loadChangelog);

    // Свой тайтлбар (frameless-окно): minimize / maximize / close
    const winBtnMin = document.getElementById('winBtnMin');
    const winBtnMax = document.getElementById('winBtnMax');
    const winBtnClose = document.getElementById('winBtnClose');
    if (winBtnMin) winBtnMin.addEventListener('click', () => {
        if (window.api && window.api.windowControl) window.api.windowControl('minimize');
    });
    if (winBtnMax) winBtnMax.addEventListener('click', () => {
        if (window.api && window.api.windowControl) window.api.windowControl('maximize');
    });
    if (winBtnClose) winBtnClose.addEventListener('click', () => {
        if (window.api && window.api.windowControl) window.api.windowControl('close');
    });

    // Контекстное меню: закрыть при клике вне / Escape / скролле
    document.addEventListener('click', e => {
        if (ctxMenuEl && !ctxMenuEl.classList.contains('hidden') && !ctxMenuEl.contains(e.target)) hideCtxMenu();
    });
    document.addEventListener('contextmenu', e => {
        // закрыть, если ПКМ не по элементу чата
        if (!(e.target.closest && e.target.closest('.chat-item'))) hideCtxMenu();
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') hideCtxMenu(); });
    window.addEventListener('scroll', hideCtxMenu, true);

    // Личность: части + создание + предпросмотр + чат-режимы
    [persUseKey, persUseModel, persUseAgent, persUseSkills, persUseOrch].forEach(cb => {
        if (cb) cb.addEventListener('change', () => {
            const row = cb.closest('.pers-part-row');
            const field = row?.querySelector('.pers-part-field');
            if (field) { field.style.opacity = cb.checked ? '1' : '0.4'; field.style.pointerEvents = cb.checked ? 'auto' : 'none'; }
        });
    });
    // Оркестратор: при "custom" показываем поле правил
    if (persOrch) persOrch.addEventListener('change', () => {
        const custom = persOrch.value === 'custom';
        if (persOrchCustom) persOrchCustom.style.display = custom ? 'block' : 'none';
    });
    if (createPersonalityBtn) createPersonalityBtn.addEventListener('click', createPersonality);
    if (previewPersonalityBtn) previewPersonalityBtn.addEventListener('click', previewPersonality);
    if (startChatWithBtn) startChatWithBtn.addEventListener('click', startChatWithMode);
    if (entityGroupFilter) entityGroupFilter.addEventListener('input', () => { renderAgents(); loadAgents(); });

    // Docs: копировать примеры
    document.querySelectorAll('[data-docs-copy]').forEach(btn => {
        btn.addEventListener('click', () => {
            const pre = document.getElementById(btn.dataset.docsCopy);
            if (pre) navigator.clipboard.writeText(pre.textContent);
        });
    });

    // Доп. параметры модели/сети/оркестратора (новый)
    ['topP','frequencyPenalty','stopSequences','responseFormat','timeout','retries','memoryMaxFacts','orchRoleDrift','orchKeepContext','orchLogVerbosity','maxIterations'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', saveSettings, { passive: true });
    });

    // Агенты / скиллы
    if (addAgentBtn) addAgentBtn.addEventListener('click', addAgent);
    if (addSkillBtn) addSkillBtn.addEventListener('click', addSkill);
    if (chatAgentSelect) chatAgentSelect.addEventListener('change', e => setChatAgent(e.target.value));
    loadAgents();

    // Индикатор статуса бэкенда: первичная проверка + ссылка «Повторить»
    // checkBackendStatus() сама делает авто-повтор (BACKEND_MAX_RETRIES × BACKEND_RETRY_MS),
    // после чего фиксирует «Бэкенд ✗». Повтор по клику / фокусу перезапускает цикл.
    let backendUp = false;
    const refreshBackendAndData = async () => {
        const ok = await checkBackendStatus();
        if (ok) {
            backendUp = true;
            loadAgents();
            loadKeys();
        }
    };
    const backendRetryLink = document.getElementById('backendRetryLink');
    if (backendRetryLink) backendRetryLink.addEventListener('click', e => {
        e.preventDefault();
        backendUp = false;
        refreshBackendAndData();
    });
    window.addEventListener('focus', () => {
        if (!backendUp) refreshBackendAndData();
    });
    refreshBackendAndData();

    // Ядровые агенты: переключатели (заявлено в критическом блоке выше)

    // Мульти-ключи
    if (addKeyBtn) addKeyBtn.addEventListener('click', addKey);
    if (keyRoundRobin) keyRoundRobin.addEventListener('change', setRoundRobin);
    loadKeys();

    // Выбор ключа в шапке чата
    if (chatKeySelect) chatKeySelect.addEventListener('change', e => {
        currentKeyId = e.target.value;
    });

    // Поиск по чатам (заявлено в критическом блоке выше)

    // Импорт агентов/скиллов из файла
    if (importAgentsBtn) importAgentsBtn.addEventListener('click', () => importAgentsFile.click());
    if (importAgentsFile) importAgentsFile.addEventListener('change', e => {
        handleAgentsImport(e.target.files);
        e.target.value = '';
    });

    // Кнопки действий в шапке чата (Сессия / Копировать / Очистить / Удалить)
    if (copyAllBtn) copyAllBtn.addEventListener('click', copyAllMessages);
    if (clearBtn) clearBtn.addEventListener('click', clearHistory);
    if (deleteBtn) deleteBtn.addEventListener('click', deleteCurrentChat);

    // Сессии
    if (newSessionBtn) newSessionBtn.addEventListener('click', openSessionModal);
    if (createSessionBtn) createSessionBtn.addEventListener('click', createSession);
    if (cancelSessionBtn) cancelSessionBtn.addEventListener('click', closeSessionModal);
    if (sessionModal) sessionModal.addEventListener('click', e => { if (e.target === sessionModal) closeSessionModal(); });

    // Редактирование сообщения
    if (document.getElementById('msgEditCancelBtn')) document.getElementById('msgEditCancelBtn').addEventListener('click', closeMessageEdit);
    if (document.getElementById('msgEditSaveBtn')) document.getElementById('msgEditSaveBtn').addEventListener('click', saveMessageEdit);
    if (document.getElementById('msgEditAddFileBtn')) document.getElementById('msgEditAddFileBtn').addEventListener('click', () => {
        const fi = document.querySelector('.msg-edit-fileinput');
        if (fi) fi.click();
    });
    if (document.querySelector('.msg-edit-fileinput')) document.querySelector('.msg-edit-fileinput').addEventListener('change', e => {
        Array.from(e.target.files).forEach(f => attachFileToEditingMessage(f));
        e.target.value = '';
    });
    const msgEditModal = document.getElementById('msgEditModal');
    if (msgEditModal) msgEditModal.addEventListener('click', e => { if (e.target === msgEditModal) closeMessageEdit(); });

    // Главная страница
    if (homeCreateBtn) homeCreateBtn.addEventListener('click', createHomeChat);
    if (homeResetBtn) homeResetBtn.addEventListener('click', resetHomeForm);
    if (homeTypeSeg) homeTypeSeg.querySelectorAll('.seg-btn').forEach(b => {
        b.addEventListener('click', () => applyHomeType(b.dataset.homeType));
    });
    if (homeOrchSel) homeOrchSel.addEventListener('change', () => {
        if (homeOrchRules) homeOrchRules.hidden = homeOrchSel.value !== 'custom';
    });
    // Модалка «прописать» агента/скилла
    document.querySelectorAll('.home-quickcreate').forEach(btn => {
        btn.addEventListener('click', () => openEntityModal(btn.dataset.open));
    });
    if (document.getElementById('homeEntityCancel')) document.getElementById('homeEntityCancel').addEventListener('click', closeEntityModal);
    if (document.getElementById('homeEntitySave')) document.getElementById('homeEntitySave').addEventListener('click', saveEntityFromModal);
    if (homeEntityModal) homeEntityModal.addEventListener('click', e => { if (e.target === homeEntityModal) closeEntityModal(); });
    // Сценарии: создание + фильтр групп
    if (homeScenarioAddBtn) homeScenarioAddBtn.addEventListener('click', () => openScenarioModal(null));
    if (homeQuickGroup) homeQuickGroup.addEventListener('change', renderHomeQuick);
    // Модалка сценария
    if (document.getElementById('scCancel')) document.getElementById('scCancel').addEventListener('click', closeScenarioModal);
    if (document.getElementById('scSave')) document.getElementById('scSave').addEventListener('click', saveScenarioModal);
    const scModal = document.getElementById('scenarioModal');
    if (scModal) scModal.addEventListener('click', e => { if (e.target === scModal) closeScenarioModal(); });
    // Модалка группы
    if (document.getElementById('groupCancel')) document.getElementById('groupCancel').addEventListener('click', closeGroupModal);
    if (document.getElementById('groupSave')) document.getElementById('groupSave').addEventListener('click', saveGroupModal);
    const groupModal = document.getElementById('groupModal');
    if (groupModal) groupModal.addEventListener('click', e => { if (e.target === groupModal) closeGroupModal(); });


    // Медиа-ключи (настройки)
    if (document.getElementById('mediaKeysSaveBtn')) document.getElementById('mediaKeysSaveBtn').addEventListener('click', saveMediaKeys);

    // ── Голосовые настройки + провайдеры ──────────────────────────────────
    // Вывод значений из settings в DOM
    function loadVoiceSettingsIntoDom() {
        const s = settings || {};
        const sttProv = document.querySelector(`input[name="sttProvider"][value="${s.sttProvider || 'local'}"]`);
        if (sttProv) sttProv.checked = true;
        const setVal = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
        setVal('wakeWordInput', s.wakeWordString || 'Астра');
        setVal('vadSilenceSlider', s.vadSilenceMs || 2000);
        setVal('vadSensitivitySlider', s.vadSensitivity || 1.8);
        setVal('cloudSttBaseUrl', s.sttBaseUrl || '');
        setVal('cloudSttModel', s.sttModelNew || '');
        setVal('localSttModelPath', s.voskModelPath || '');
        setVal('ttsProvider', s.ttsProvider || 'browser');
        setVal('ttsBaseUrl', s.ttsBaseUrl || '');
        setVal('ttsModel', s.ttsModel || '');
        setVal('ttsVoiceId', s.ttsVoiceId || '');
        // Обновить output-бейджи слайдеров
        const vo = document.getElementById('vadSilenceOut'); if (vo) vo.textContent = s.vadSilenceMs || 2000;
        const vs = document.getElementById('vadSensitivityOut'); if (vs) vs.textContent = s.vadSensitivity || 1.8;
        // Показать/скрыть группы в зависимости от STT-провайдера
        updateSttGroupsVisibility();
        updateTtsGroupsVisibility();
    }
    function updateSttGroupsVisibility() {
        const prov = document.querySelector('input[name="sttProvider"]:checked')?.value || 'local';
        const cg = document.getElementById('cloudSttGroup');
        if (cg) cg.style.display = (prov === 'cloud' || prov === 'custom') ? '' : 'none';
    }
    function updateTtsGroupsVisibility() {
        const prov = document.getElementById('ttsProvider')?.value || 'browser';
        const tg = document.getElementById('ttsCustomGroup');
        if (tg) tg.style.display = prov !== 'browser' ? '' : 'none';
    }
    document.querySelectorAll('input[name="sttProvider"]').forEach(r => r.addEventListener('change', updateSttGroupsVisibility));
    const ttsProviderSel = document.getElementById('ttsProvider');
    if (ttsProviderSel) ttsProviderSel.addEventListener('change', updateTtsGroupsVisibility);
    const vadSilenceSlider = document.getElementById('vadSilenceSlider');
    if (vadSilenceSlider) vadSilenceSlider.addEventListener('input', () => { const o = document.getElementById('vadSilenceOut'); if (o) o.textContent = vadSilenceSlider.value; });
    const vadSensSlider = document.getElementById('vadSensitivitySlider');
    if (vadSensSlider) vadSensSlider.addEventListener('input', () => { const o = document.getElementById('vadSensitivityOut'); if (o) o.textContent = vadSensSlider.value; });
    // Загрузить при старте
    loadVoiceSettingsIntoDom();

    // Кнопки сохранения
    document.getElementById('voiceSaveBtn')?.addEventListener('click', async () => {
        settings = buildSettingsFromInputs();
        await SecureStore.set(STORAGE_SETTINGS, settings);
        await saveSettingsToServer();
        flashStatus('Голосовые настройки сохранены');
        if (window.voice) window.voice.init(buildVoiceSettingsObj());
    });
    document.getElementById('providersSaveBtn')?.addEventListener('click', async () => {
        settings = buildSettingsFromInputs();
        // Сохранить non-secret в settings.json
        await SecureStore.set(STORAGE_SETTINGS, settings);
        await saveSettingsToServer();
        // API-ключи — в safeStorage (Electron) или localStorage (браузер)
        const sttKey = document.getElementById('cloudSttKey')?.value.trim() || '';
        const ttsKey = document.getElementById('ttsKey')?.value.trim() || '';
        const sttStatus = document.getElementById('cloudSttKeyStatus');
        const ttsStatus = document.getElementById('ttsKeyStatus');
        if (sttKey) {
            await window.api?.secrets?.set?.({ provider: 'stt', key: sttKey }) ||
                localStorage.setItem('amt_secret_stt', sttKey);
            if (sttStatus) sttStatus.textContent = '•••••••• Saved';
        } else if (sttStatus) sttStatus.textContent = 'Ключ не задан';
        if (ttsKey) {
            await window.api?.secrets?.set?.({ provider: 'tts', key: ttsKey }) ||
                localStorage.setItem('amt_secret_tts', ttsKey);
            if (ttsStatus) ttsStatus.textContent = '•••••••• Saved';
        } else if (ttsStatus) ttsStatus.textContent = 'Ключ не задан';
        flashStatus('Настройки провайдеров сохранены');
    });
    document.getElementById('providersResetBtn')?.addEventListener('click', async () => {
        // Сбросить DOM-поля
        const resetFields = [
            ['wakeWordInput', 'Астра'], ['vadSilenceSlider', '2000'], ['vadSensitivitySlider', '1.8'],
            ['cloudSttBaseUrl', ''], ['cloudSttModel', ''], ['cloudSttKey', ''], ['localSttModelPath', ''],
            ['ttsProvider', 'browser'], ['ttsBaseUrl', ''], ['ttsModel', ''], ['ttsVoiceId', ''], ['ttsKey', '']
        ];
        resetFields.forEach(([id, v]) => { const el = document.getElementById(id); if (el) el.value = v; });
        const localRadio = document.querySelector('input[name="sttProvider"][value="local"]');
        if (localRadio) localRadio.checked = true;
        updateSttGroupsVisibility(); updateTtsGroupsVisibility();
        const vo = document.getElementById('vadSilenceOut'); if (vo) vo.textContent = '2000';
        const vs = document.getElementById('vadSensitivityOut'); if (vs) vs.textContent = '1.8';
        const sttStatus = document.getElementById('cloudSttKeyStatus'); if (sttStatus) sttStatus.textContent = 'Ключ не задан';
        const ttsStatus = document.getElementById('ttsKeyStatus'); if (ttsStatus) ttsStatus.textContent = 'Ключ не задан';
        // Очистить ключи
        await window.api?.secrets?.clear?.({ provider: 'stt' }) || localStorage.removeItem('amt_secret_stt');
        await window.api?.secrets?.clear?.({ provider: 'tts' }) || localStorage.removeItem('amt_secret_tts');
        // Сохранить сброс
        settings = buildSettingsFromInputs();
        await SecureStore.set(STORAGE_SETTINGS, settings);
        await saveSettingsToServer();
        flashStatus('Сброшено на дефолты');
    });
    // Показать статус ключей при загрузке
    (async () => {
        try {
            const st = await window.api?.secrets?.status?.();
            if (st?.providers?.includes('stt')) {
                const el = document.getElementById('cloudSttKeyStatus');
                if (el) el.textContent = '•••••••• Saved';
            }
            if (st?.providers?.includes('tts')) {
                const el = document.getElementById('ttsKeyStatus');
                if (el) el.textContent = '•••••••• Saved';
            }
        } catch (_) { /* browser без safeStorage — молча */ }
    })();

    // beforeunload — остановить голосовой режим
    window.addEventListener('beforeunload', () => { if (window.voice) window.voice.stopAll(); });

    // Инициализация voice.js
    function buildVoiceSettingsObj() {
        return {
            sttProvider: settings?.sttProvider || 'local',
            sttBaseUrl: settings?.sttBaseUrl || '',
            sttModel: settings?.sttModelNew || '',
            ttsProvider: settings?.ttsProvider || 'browser',
            ttsBaseUrl: settings?.ttsBaseUrl || '',
            ttsModel: settings?.ttsModel || '',
            ttsVoiceId: settings?.ttsVoiceId || '',
            wakeWordString: settings?.wakeWordString || 'Астра',
            vadSilenceMs: settings?.vadSilenceMs || 2000,
            vadSensitivity: settings?.vadSensitivity || 1.8,
        };
    }
    if (window.voice) window.voice.init(buildVoiceSettingsObj());

    // Тест STT (текст → голос → STT: полный цикл)
    if (document.getElementById('sttTestBtn')) {
        document.getElementById('sttTestBtn').addEventListener('click', async () => {
            const text = await amtPrompt('Текст для теста STT (будет озвучен и распознан):', 'Привет, это тест голосового распознавания');
            if (!text?.trim()) { flashStatus('Текст пуст'); return; }
            const key = document.getElementById('audioKey')?.value.trim() || '';
            const base = document.getElementById('audioBaseUrl')?.value.trim() || '';
            const ttsModel = document.getElementById('audioModel')?.value.trim() || '';
            const sttModel = document.getElementById('sttModel')?.value.trim() || '';
            const voiceId = document.getElementById('audioVoiceId')?.value.trim() || '';
            flashStatus('Тест STT: синтезирую голос…');
            try {
                // Step 1: TTS — текст → аудио
                const ttsBody = { kind: 'audio', prompt: text, use_settings_key: true, paths: buildPathsObj() };
                if (base) ttsBody.base_url = base;
                if (key) ttsBody.api_key = key;
                if (ttsModel) ttsBody.model = ttsModel;
                if (voiceId) ttsBody.voice_id = voiceId;
                const ttsRes = await fetch(`${API_BASE}/api/media/generate`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(ttsBody),
                });
                const tj = await ttsRes.json();
                if (!tj.ok) {
                    flashStatus('TTS не работает: ' + (tj.error || 'нет ключа'));
                    return;
                }
                // Step 2: Get audio b64
                let audioB64 = tj.b64 || '';
                if (!audioB64 && tj.stored_name) {
                    // Download stored file
                    const dlRes = await fetch(`${API_BASE}${tj.download_url || '/api/files/' + tj.stored_name}`);
                    const blob = await dlRes.blob();
                    audioB64 = await new Promise(resolve => {
                        const r = new FileReader();
                        r.onload = () => resolve(r.result.split(',')[1]);
                        r.readAsDataURL(blob);
                    });
                }
                if (!audioB64) { flashStatus('Не удалось получить аудио для STT'); return; }
                // Step 3: STT — аудио → текст
                flashStatus('Тест STT: распознаю…');
                const sttBody = { audio_b64: audioB64, mime: 'audio/mpeg', use_settings_key: true };
                if (base) sttBody.base_url = base;
                if (key) sttBody.api_key = key;
                if (sttModel) sttBody.model = sttModel;
                const sttRes = await fetch(`${API_BASE}/api/stt`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sttBody),
                });
                const sj = await sttRes.json();
                if (sj.ok && sj.text) {
                    flashStatus('STT работает! Распознал: "' + sj.text.slice(0, 100) + '"');
                } else {
                    flashStatus('STT ошибка: ' + (sj.error || 'неизвестно'));
                }
            } catch (e) {
                flashStatus('Тест STT: ' + (e.message || e));
            }
        });
    }
    // Хранилище
    if (storageRefreshBtn) storageRefreshBtn.addEventListener('click', loadStorage);
    if (storageExportBtn) storageExportBtn.addEventListener('click', exportAllData);
    // Инструменты
    if (document.getElementById('toolsSaveBtn')) document.getElementById('toolsSaveBtn').addEventListener('click', saveToolsConfig);
    if (document.getElementById('toolsTestRead')) document.getElementById('toolsTestRead').addEventListener('click', async () => {
        const p = await amtPrompt('Путь к файлу (read-only):', '');
        if (!p) return;
        const box = document.getElementById('toolsLogList');
        const res = await requestTool('read_file', { path: p }, null);
        flashStatus(res.ok ? 'Файл прочитан' : (res.error || 'ошибка'));
    });
    if (document.getElementById('toolsTestCmd')) document.getElementById('toolsTestCmd').addEventListener('click', async () => {
        const c = await amtPrompt('Команда (из белого списка):', 'python -V');
        if (!c) return;
        const res = await requestTool('run_command', { command: c }, null);
        flashStatus(res.ok ? `OK (${res.exit_code})` : (res.error || 'ошибка'));
    });
    if (document.getElementById('toolsTestWrite')) document.getElementById('toolsTestWrite').addEventListener('click', async () => {
        const p = await amtPrompt('Путь к файлу (в разрешённых каталог��х):', '');
        if (!p) return;
        const content = await amtPrompt('Содержимое:', 'test');
        if (content === null) return;
        const res = await requestTool('write_file', { path: p, content }, null);
        flashStatus(res.ok ? `Записано: ${res.path}` : (res.error || 'ошибка'));
    });
    if (document.getElementById('toolsRefreshLog')) document.getElementById('toolsRefreshLog').addEventListener('click', refreshToolsLog);

    // Проекты: выбрать/снять рабочую папку для ИИ-инструментов
    const projSelectBtn = document.getElementById('projSelectBtn');
    const projClearBtn = document.getElementById('projClearBtn');
    async function selectProjectDir() {
        let dir = null;
        if (window.api && window.api.dialog && window.api.dialog.openDirectory) {
            // IPC возвращает { canceled, path } (или строку в старых версиях preload)
            const res = await window.api.dialog.openDirectory();
            if (res && typeof res === 'object') dir = res.canceled ? null : (res.path || null);
            else dir = res || null;
        } else {
            dir = await amtPrompt('Путь к папке проекта:', '');
        }
        if (!dir) return;
        const res = await fetch(`${API_BASE}/api/projects/select`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ root: dir }),
        }).then(r => r.json()).catch(() => ({ ok: false, error: 'Ошибка сети' }));
        showProjResult(res);
        loadProjectCurrent();
    }
    async function clearProject() {
        const res = await fetch(`${API_BASE}/api/projects/clear`, { method: 'POST' })
            .then(r => r.json()).catch(() => ({ ok: false, error: 'Ошибка сети' }));
        showProjResult(res);
        loadProjectCurrent();
    }
    if (projSelectBtn) projSelectBtn.addEventListener('click', selectProjectDir);
    if (projClearBtn) projClearBtn.addEventListener('click', clearProject);
    loadProjectCurrent();

    // sec-coding: folder picker for codingProjectRoot
    const codingProjectSelectBtn = document.getElementById('codingProjectSelectBtn');
    if (codingProjectSelectBtn) {
        codingProjectSelectBtn.addEventListener('click', async () => {
            const input = document.getElementById('codingProjectRoot');
            if (!input) return;
            let dir = null;
            if (window.api && window.api.dialog && window.api.dialog.openDirectory) {
                const res = await window.api.dialog.openDirectory();
                if (res && typeof res === 'object') dir = res.canceled ? null : (res.path || null);
                else dir = res || null;
            } else if (window.amtPrompt) {
                dir = await window.amtPrompt('Путь к папке проекта:', input.value || '');
            }
            if (dir) {
                input.value = dir;
                const s = JSON.parse(localStorage.getItem('amt_coding_settings') || '{}');
                s.projectRoot = dir;
                localStorage.setItem('amt_coding_settings', JSON.stringify(s));
                const chat = window.getCurrentChat ? window.getCurrentChat() : null;
                if (chat) { chat.projectRoot = dir; window.saveChats?.(); }
                if (window.flashStatus) window.flashStatus('Рабочая папка: ' + dir);
            }
        });
    }

    // sec-coding: toggle help list visibility
    const codingHelpToggleBtn = document.getElementById('codingHelpToggleBtn');
    if (codingHelpToggleBtn) {
        codingHelpToggleBtn.addEventListener('click', () => {
            const list = document.getElementById('codingHelpList');
            const desc = codingHelpToggleBtn.closest('.coding-help-block')?.querySelector('.block-desc');
            const visible = list ? !list.style.display || list.style.display === 'none' : true;
            if (list) list.style.display = visible ? 'none' : '';
            if (desc) desc.style.display = visible ? 'none' : '';
            codingHelpToggleBtn.textContent = visible ? 'Показать' : 'Скрыть';
        });
    }

    if (document.getElementById('toolConfirmApprove')) document.getElementById('toolConfirmApprove').addEventListener('click', approveToolConfirm);
    if (document.getElementById('toolConfirmDeny')) document.getElementById('toolConfirmDeny').addEventListener('click', denyToolConfirm);
    const tcModal = document.getElementById('toolConfirmModal');
    if (tcModal) tcModal.addEventListener('click', e => { if (e.target === tcModal) denyToolConfirm(); });
    // Picker инструментов в чате (toolBtn заявлено в критическом блоке выше)
    document.querySelectorAll('.tool-picker-item').forEach(b => {
        b.addEventListener('click', () => runToolFromPicker(b.dataset.tool));
    });
    document.addEventListener('click', e => {
        const p = document.getElementById('toolPicker');
        if (p && !p.classList.contains('hidden') && !e.target.closest('.tool-picker') && e.target.id !== 'toolBtn') p.classList.add('hidden');
    });

    // Модальное окно «название + группа»
    const cm = document.getElementById('chatMetaModal');
    if (cm) {
        document.getElementById('chatMetaSave').addEventListener('click', saveChatMeta);
        document.getElementById('chatMetaCancel').addEventListener('click', () => cm.classList.add('hidden'));
        cm.addEventListener('click', e => { if (e.target === cm) cm.classList.add('hidden'); });
    }

    // Шлопывание кнопок (заявлено в критическом блоке выше)

    // Автопереход на страницу логов, если туда навигация
    if (location.hash === '#logs') {
        showPage('logs');
        loadLogs();
    }

    // Сохраняем всё при закрытии/переходе
    window.addEventListener('beforeunload', () => {
        if (chats.length > 0) {
            const data = JSON.stringify({ chats: chats });
            const blob = new Blob([data], { type: 'application/json' });
            navigator.sendBeacon(`${API_BASE}/api/chats/save`, blob);
        }
        saveChats();
        saveGroups();
        saveSettings();
        saveCurrentChatId();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            if (chats.length > 0) {
                const data = JSON.stringify({ chats: chats });
                const blob = new Blob([data], { type: 'application/json' });
                navigator.sendBeacon(`${API_BASE}/api/chats/save`, blob);
            }
            saveChats();
            saveGroups();
            saveSettings();
            saveCurrentChatId();
        }
    });
    } catch (e) {
        console.error('[init] listener registration error:', e);
    }
});
