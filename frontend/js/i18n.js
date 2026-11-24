// i18n: словари RU/EN для всего UI. Ключ = data-i18n.
// RU — родной (data-i18n-ru в DOM). EN — ниже.
const I18N = {
    ru: {},
    en: {
        // Sidebar / nav
        "ui_lang_label": "Lang",
        "nav_home": "Home", "nav_chat": "Chat", "nav_settings": "Settings", "nav_docs": "Docs", "nav_storage": "Storage", "nav_logs": "Logs",
        "new_chat": "+ New chat", "add_group": "Group", "status_ready": "Ready",
        // Home
        "home_start": "Where to begin?",
        "home_sub": "Create a chat — plain, or with a personality: agent, orchestrator, skills, system prompt. All details can be set right here.",
        "chat_config": "Chat setup", "reset": "Reset", "chat_type": "Chat type",
        "plain": "No persona", "personality": "With persona", "custom": "Custom prompt",
        "settings_title": "Settings", "save_all": "Save all settings",
        // Settings subnav
        "s_connect": "Connection", "s_model": "Model", "s_net": "Network",
        "s_agents": "Agents/Skills", "s_keys": "Keys", "s_tools": "Tools",
        "s_media": "Media keys", "s_projects": "Projects", "s_orch": "Orchestrator", "s_memory": "Memory",
        "s_personality": "Personality", "s_docs": "Docs", "s_themes": "Themes & configs",
        "docs_title": "Docs", "docs_about": "About app", "docs_ext": "Extensions", "docs_author": "How to build", "docs_updates": "Updates",
        // Settings block titles
        "b_connect": "Connection", "b_connect_desc": "API address and key. Check available models.",
        "b_model": "Model", "b_net": "Network", "b_tools": "Safe tools",
        "b_memory": "AI memory", "b_personality": "Personality", "b_orch": "Orchestrator (AI controller)",
        "b_media_keys": "Per-function keys", "b_docs": "Docs — examples & reference", "b_themes": "Themes & configs",
        // Storage
        "storage_title": "Storage",
        "storage_desc": "Everything you added: chats, agents, skills, keys, sessions, files, memory. Browse, copy, manage.",
        "storage_refresh": "Refresh", "storage_export": "Export all"
    }
};

// Применить язык: (1) [data-i18n] подстановкой из словаря; (2) по селекторам из SELECTOR_I18N.
const SELECTOR_I18N = {
    // настройки: заголовки блоков
    "#sec-connect .settings-block h3": "Connection",
    "#sec-model .settings-block h3": "Model & parameters",
    "#sec-net .settings-block h3": "Network & proxy",
    "#sec-tools .settings-block:first-child h3": "Safe tools",
    "#sec-media .settings-block h3": "Per-function keys",
    "#sec-memory .settings-block h3": "AI memory",
    "#sec-personality .settings-block h3": "Personality",
    "#sec-orch .settings-block h3": "Orchestrator (AI controller)",
    "#sec-docs .settings-block h3": "Docs — examples & reference",
    "#sec-themes .settings-block h3": "Themes & configs",
    // storage / generation
    "#storagePage .storage-header h2": "Storage",
    ".gen-subnav .gen-tab[data-gen-tab='files']": "Files",
    ".gen-subnav .gen-tab[data-gen-tab='photo']": "Photo",
    ".gen-subnav .gen-tab[data-gen-tab='video']": "Video",
    ".gen-subnav .gen-tab[data-gen-tab='voice']": "Voice",
    ".sidebar-footer .status-text": "Ready"
};

function applyI18n(lang) {
    const dict = I18N[lang] || I18N.en;
    document.documentElement.lang = lang;
    // (1) Текст элемента: data-i18n (ключ) или data-i18n-en (инлайн)
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        let val = dict[key];
        if (val == null) {
            if (lang === "ru") { val = el.getAttribute("data-i18n-ru"); }
            else if (el.getAttribute("data-i18n-en") != null) { val = el.getAttribute("data-i18n-en"); }
        }
        if (val != null) el.textContent = val;
    });
    // (2) Атрибуты: placeholder (data-i18n-en-ph) и title (data-i18n-en-title)
    //     Только en — применяем; ru — возвращаем родной текст из data-orig.
    const isEn = (lang === "en");
    document.querySelectorAll("[data-i18n-en-ph]").forEach(el => {
        const v = el.getAttribute("data-i18n-en-ph");
        if (v == null) return;
        if (isEn) el.setAttribute("placeholder", v);
        else if (el.dataset.origPh != null) el.setAttribute("placeholder", el.dataset.origPh);
        else el.dataset.origPh = el.getAttribute("placeholder") || "";
    });
    document.querySelectorAll("[data-i18n-en-title]").forEach(el => {
        const v = el.getAttribute("data-i18n-en-title");
        if (v == null) return;
        if (isEn) el.setAttribute("title", v);
        else if (el.dataset.origTitle != null) el.setAttribute("title", el.dataset.origTitle);
        else el.dataset.origTitle = el.getAttribute("title") || "";
    });
    // option и элементы с инлайн data-i18n-en (без data-i18n): textContent
    document.querySelectorAll("[data-i18n-en]").forEach(el => {
        if (el.hasAttribute("data-i18n")) return; // такие обрабатываются в п. (1)
        const v = el.getAttribute("data-i18n-en");
        if (v == null) return;
        if (isEn) el.textContent = v;
        else if (el.dataset.origText != null) el.textContent = el.dataset.origText;
        else el.dataset.origText = el.textContent;
    });
    // По селекторам: только элементы БЕЗ дочерних тегов (чистый текст), чтобы не сломать иконки.
    for (const [sel, enText] of Object.entries(SELECTOR_I18N)) {
        const el = document.querySelector(sel);
        if (!el || el.childElementCount > 0) continue; // пропускаем h3 с SVG-иконкой и т.п.
        if (lang === "en") {
            el.textContent = enText;
        } else {
            if (el.dataset.ruText != null) el.textContent = el.dataset.ruText;
            else { el.dataset.ruText = el.textContent; }
        }
    }
}
