// темы / шрифты / фон / конфиги / i18n — модуль, подключаемый после main.js
(function () {
    const API_BASE = location.origin;
    const THEMES_URL = "./themes.json";

    const FONTS = [
        { id: "system",   label: "Системный (Segoe UI)", family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" },
        { id: "inter",    label: "Inter",                 family: "'Inter', -apple-system, 'Segoe UI', sans-serif" },
        { id: "georgia",  label: "Georgia (display serif)",family: "Georgia, 'Times New Roman', serif" },
        { id: "mono",     label: "Моноширинный (code)",   family: "'Cascadia Code', 'Fira Code', Consolas, monospace" },
        { id: "rounded",  label: "Скруглённый (sans)",    family: "'Trebuchet MS', 'Comic Sans MS', sans-serif" },
    ];

    let themes = {};      // {id: {label, bg[3], accent, accent2, ...}}
    let customThemes = {}; // {id: {...}}
    let current = { theme: "ocean", font: "system", bg: "", lang: "ru" };

    function esc(s){ return String(s||'').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

    // === Применение темы: задаём CSS-переменные на :root ===
    // v2: через theme-schema.js — normalize (v1/v2) + toCssVars (60+ vars).
    // Совместимо с плоскими v1 темами (bg[], glass, accent, ...) — normalizeTheme их поднимает.
    function applyThemeVars(t) {
        const r = document.documentElement.style;
        const theme = (typeof window.AMTThemeSchema !== "undefined")
            ? window.AMTThemeSchema.normalizeTheme(t, (t && t.id) || "ocean")
            : t; // fallback если схема не загрузилась
        if (typeof window.AMTThemeSchema !== "undefined") {
            const vars = window.AMTThemeSchema.toCssVars(theme);
            for (const k in vars) r.setProperty(k, vars[k]);
        } else {
            // legacy fallback — старое поведение
            const bg = t.bg || ["#05050a", "#11131a", "#0b0f14"];
            r.setProperty("--bg-grad-1", bg[0]); r.setProperty("--bg-grad-2", bg[1]); r.setProperty("--bg-grad-3", bg[2] || bg[1]);
            r.setProperty("--glass-bg", t.glass || "rgba(255,255,255,0.02)");
            r.setProperty("--glass-bg-2", t.glass2 || "rgba(255,255,255,0.04)");
            r.setProperty("--glass-border", t.border || "rgba(255,255,255,0.06)");
            r.setProperty("--accent", t.accent || "#8b86c9");
            r.setProperty("--accent-2", t.accent2 || "#aba5c9");
            r.setProperty("--text", t.text || "#d0d0d0");
            r.setProperty("--text-dim", t.textDim || "#8a8a9a");
        }
        document.documentElement.setAttribute("data-theme", (t && t.id) || "ocean");
        document.documentElement.setAttribute("data-appearance", theme.appearance || "dark");
    }
    function applyFont(f, fontFamily) {
        // f: font id from FONTS array, or "custom" (use fontFamily string)
        const p = FONTS.find(x => x.id === f);
        let family;
        if (f === "custom" && fontFamily) {
            family = fontFamily;
        } else if (p) {
            family = p.family;
        } else {
            family = FONTS[0].family;
        }
        document.documentElement.style.setProperty("--font-family", family);
        document.body.style.fontFamily = family;
    }
    function applyBg(dim) {
        const m = document.getElementById("bgMedia");
        if (!m) return;
        m.innerHTML = "";
        if (current.bg) {
            const isVid = /\.(mp4|webm|mov|m4v)/i.test(current.bg);
            const src = current.bg.startsWith("http") ? current.bg : API_BASE + current.bg;
            const el = document.createElement(isVid ? "video" : "img");
            if (isVid) { el.src = src; el.muted = true; el.loop = true; el.autoplay = true; el.playsInline = true; el.play().catch(()=>{}); }
            else { el.src = src; el.alt = ""; }
            el.style.opacity = ((100 - (parseInt(dim || "55", 10))) / 100 * 0.9 + 0.05);
            m.appendChild(el);
        }
    }

    // === i18n ===
    function setLang(lang) {
        current.lang = lang;
        if (typeof applyI18n === "function") applyI18n(lang);
        const sel = document.getElementById("langSelect");
        if (sel) sel.value = lang;
    }

    // === Конфиги (backend /api/configs) ===
    function api(p, o, m) {
        return fetch(API_BASE + p, { method: m || "GET",
            headers: { "Content-Type": "application/json" },
            body: m && m !== "GET" ? JSON.stringify(o) : undefined,
        }).then(r => r.json());
    }
    function currentConfig() {
        return { theme: current.theme, font: current.font, bg: current.bg, lang: current.lang,
            mediaKeys: (typeof buildSettingsFromInputs === "function" ? buildSettingsFromInputs() : {}) };
    }
    function applyConfig(c) {
        if (!c) return;
        current.theme = c.theme || "ocean"; current.font = c.font || "system"; current.bg = c.bg || ""; current.lang = c.lang || "ru";
        const known = { ...themes, ...customThemes };
        applyThemeVars(known[current.theme] || themes[current.theme] || Object.values(themes)[0]);
        applyFont(current.font); applyBg(); setLang(current.lang);
        if (c.mediaKeys && typeof loadSettings === "function") { /* ключи сохраняются через обычный save */ }
        renderAll();
    }
    async function listConfigs() {
        const el = document.getElementById("cfgList"); if (!el) return;
        try {
            const d = await api("/api/configs");
            const items = d.configs || [];
            el.innerHTML = items.length ? "" : '<span class="docs-note">Конфиги ещё нет. Сохраните текущий.</span>';
            items.forEach(c => {
                const row = document.createElement("div"); row.className = "storage-item";
                row.innerHTML = `<div class="si-main"><div class="si-name">${esc(c.name)}</div>
                    <div class="si-meta">тема: ${esc(c.theme||'ocean')} · шрифт: ${esc(c.font||'system')} · язык: ${esc(c.lang||'ru')}</div></div>
                    <div class="si-actions">
                        <button class="test-btn" data-act="apply">Применить</button>
                        <button class="test-btn danger" data-act="del">Удалить</button>
                    </div>`;
                row.querySelector('[data-act="apply"]').onclick = () => { api("/api/configs/" + encodeURIComponent(c.name) + "/apply", {}, "POST").then(x => { if (x.config) applyConfig(x.config); }); };
                row.querySelector('[data-act="del"]').onclick = () => { api("/api/configs/" + encodeURIComponent(c.name), {}, "DELETE").then(() => listConfigs()); };
                el.appendChild(row);
            });
        } catch { el.innerHTML = '<span class="docs-note">Не удалось загрузить конфиги.</span>'; }
    }

    function renderAll() {
        const tp = document.getElementById("themePick");
        if (tp) {
            const all = { ...themes, ...customThemes };
            tp.innerHTML = Object.entries(all).map(([id, t]) => `<option value="${id}">${esc(t.label||id)}</option>`).join("");
            tp.value = current.theme;
        }
        // Свотчи тем
        renderSwatches();
        const fp = document.getElementById("fontPick");
        if (fp) {
            fp.innerHTML = FONTS.map(f => `<option value="${f.id}">${esc(f.label)}</option>`).join("") + '<option value="custom">Свой…</option>';
            fp.value = current.font;
            // Show/hide custom font input
            const cf = document.getElementById("fontCustom");
            if (cf) cf.style.display = fp.value === "custom" ? "block" : "none";
            if (!fp.__amtCustomFontListener) {
                fp.__amtCustomFontListener = true;
                fp.addEventListener("change", () => {
                    const cf2 = document.getElementById("fontCustom");
                    if (cf2) cf2.style.display = fp.value === "custom" ? "block" : "none";
                });
            }
        }
        const dim = document.getElementById("bgDim"); if (dim) dim.oninput = () => { document.getElementById("bgDimVal").textContent = dim.value + "%"; applyBg(dim.value); };
    }

    function renderSwatches() {
        const el = document.getElementById("themeSwatches");
        if (!el) return;
        el.innerHTML = "";
        const all = { ...themes, ...customThemes };
        for (const [id, t] of Object.entries(all)) {
            const c = document.createElement("div");
            c.className = "theme-swatch" + (id === current.theme ? " active" : "");
            c.title = t.label || id;
            const bg = (t.colors && t.colors.bg) ? t.colors.bg : (t.bg || ["#0a0f1a", "#1a2340", "#0a1420"]);
            c.style.background = `linear-gradient(135deg, ${bg[0]} 0%, ${bg[1]} 50%, ${bg[2] || bg[1]} 100%)`;
            c.onclick = () => {
                current.theme = id;
                applyThemeVars(all[id]);
                renderAll();
                persist();
                // Синхронизация: обновляем редактор тем (тема-editor.js)
                if (window.AMTThemeEditor && window.AMTThemeEditor.onThemeChange) {
                    window.AMTThemeEditor.onThemeChange(id, all[id]);
                }
            };
            el.appendChild(c);
        }
    }

    function applyDensity() {
        const sl = document.getElementById("densitySlider");
        if (!sl) return;
        const v = parseInt(sl.value, 10);
        document.body.classList.remove("density-compact", "density-standard", "density-spacious");
        document.body.classList.add(["density-compact","density-standard","density-spacious"][v] || "density-standard");
        persist();
    }

    function applyToggles() {
        const anim = document.getElementById("tAnim");
        if (anim) document.body.classList.toggle("no-anim", !anim.checked);
        const focus = document.getElementById("tFocus");
        if (focus) document.body.classList.toggle("no-focus", !focus.checked);
        const sb = document.getElementById("tSidebar");
        if (sb) document.body.classList.toggle("compact-sidebar", sb.checked);
        persist();
    }

    // ===== Инициализация =====
    // btoa-в-чанках: String.fromCharCode(...) падает при arg > 65535,
    // поэтому режем Uint8Array на куски по 0x8000 (32768).
    function chunkedB64(u8) {
        const CHUNK = 0x8000;
        let bin = '';
        for (let i = 0; i < u8.length; i += CHUNK) {
            bin += String.fromCharCode.apply(null, u8.subarray(i, i + CHUNK));
        }
        return btoa(bin);
    }

    async function init() {
        try { themes = await fetch(THEMES_URL).then(r => r.json()); } catch { themes = { ocean: { label: "Океан (дефолт)" } }; }
        // кастомные темы: v2 (amt_custom_themes_v2) + миграция из v1 (amt_custom_themes)
        let v2 = {};
        try { v2 = JSON.parse(localStorage.getItem("amt_custom_themes_v2") || "{}"); } catch { v2 = {}; }
        let v1 = {};
        try { v1 = JSON.parse(localStorage.getItem("amt_custom_themes") || "{}"); } catch { v1 = {}; }
        // Migrate v1 → v2 if v2 empty or missing entries
        for (const id of Object.keys(v1)) {
            if (!v2[id]) {
                v2[id] = (typeof window.AMTThemeSchema !== "undefined")
                    ? window.AMTThemeSchema.normalizeTheme(v1[id], id)
                    : v1[id];
            }
        }
        if (Object.keys(v1).length > 0) {
            localStorage.setItem("amt_custom_themes_v2", JSON.stringify(v2));
            // Не удаляем v1 — оставляем на случай отката. Миграция идемпо��ентна.
        }
        customThemes = v2;

        // события: язык (в настройках → темы и конфиги)
        const lp = document.getElementById("langSelect");
        if (lp) lp.onchange = () => { current.lang = lp.value; setLang(lp.value); persist(); };

        // страница "Темы и конфиги"
        const tp = document.getElementById("themePick");
        if (tp) tp.onchange = () => { current.theme = tp.value; applyThemeVars({ ...customThemes, ...themes }[current.theme]); renderAll(); persist(); if (window.AMTThemeEditor && window.AMTThemeEditor.onThemeChange) window.AMTThemeEditor.onThemeChange(tp.value, ({ ...customThemes, ...themes })[tp.value]); };
        const preview = document.getElementById("themePreviewBtn");
        if (preview) preview.onclick = () => { const t = ({ ...customThemes, ...themes })[tp.value]; if (t) applyThemeVars(t); };
        const fp = document.getElementById("fontPick");
        if (fp) {
            fp.onchange = () => {
                current.font = fp.value;
                const cf = document.getElementById("fontCustom");
                const ff = cf && cf.value ? cf.value.trim() : undefined;
                applyFont(current.font, ff);
                persist();
            };
            // Also re-apply when the custom font input changes
            const cfIn = document.getElementById("fontCustom");
            if (cfIn) {
                let _cfTimer;
                cfIn.addEventListener("input", () => {
                    clearTimeout(_cfTimer);
                    _cfTimer = setTimeout(() => {
                        const v = cfIn.value.trim();
                        if (current.font === "custom") { applyFont("custom", v || undefined); persist(); }
                    }, 300);
                });
            }
        }
        // ct* контролы удалены — их заменил v2 редактор (te* в theme-editor.js)
        // фон
        const bgFile = document.getElementById("bgFile");
        if (bgFile) bgFile.onchange = () => {
            const f = bgFile.files[0]; if (!f) return;
            const isVid = f.type.startsWith("video");
            const reader = new FileReader();
            reader.onload = () => {
                // сохраняем в бэкенд (базовое имя + лимит), получаем URL
                const buf = new Uint8Array(reader.result);
                // btoa не может обработать большие массивы одной строкой — режём на чанки
                const b64 = chunkedB64(buf);
                fetch(API_BASE + "/api/backgrounds", { method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: f.name, mime: f.type, b64: b64 }),
                }).then(r => r.json()).then(d => {
                    if (d.ok) { current.bg = d.url; applyBg(document.getElementById("bgDim")?.value); persist(); }
                });
            };
            reader.readAsArrayBuffer(f);
        };
        const bgClear = document.getElementById("bgClearBtn");
        if (bgClear) bgClear.onclick = () => { current.bg = ""; applyBg(); persist(); };
        // конфиги
        const cfgSave = document.getElementById("cfgSaveBtn");
        if (cfgSave) cfgSave.onclick = () => {
            const name = document.getElementById("cfgName").value.trim();
            api("/api/configs", { name: name || ("config-" + Date.now().toString(36)), config: currentConfig() }, "POST").then(listConfigs);
        };
        const cfgExport = document.getElementById("cfgExportBtn");
        if (cfgExport) cfgExport.onclick = () => {
            const blob = new Blob([JSON.stringify(currentConfig(), null, 2)], { type: "application/json" });
            const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "amt-config-" + Date.now().toString(36) + ".json"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 30000);
        };
        const cfgImportBtn = document.getElementById("cfgImportBtn");
        const cfgImportFile = document.getElementById("cfgImportFile");
        if (cfgImportBtn && cfgImportFile) {
            cfgImportBtn.onclick = () => cfgImportFile.click();
            cfgImportFile.onchange = () => { const f = cfgImportFile.files[0]; if (!f) return; const r = new FileReader(); r.onload = () => { try { applyConfig(JSON.parse(r.result)); api("/api/configs", { name: f.name.replace(/\.[^.]+$/, ""), config: currentConfig() }, "POST").then(listConfigs); } catch (e) { alert("Неверный JSON конфига: " + e.message); } }; r.readAsText(f); };
        }
        const cfgImportPaste = document.getElementById("cfgImportPaste");
        if (cfgImportPaste) cfgImportPaste.onclick = () => {
            const txt = document.getElementById("cfgImportTextarea").value.trim(); if (!txt) return;
            try { const c = JSON.parse(txt); applyConfig(c); api("/api/configs", { name: "imported-" + Date.now().toString(36), config: c }, "POST").then(listConfigs); }
            catch (e) { alert("Неверный JSON: " + e.message); }
        };

        // Переключатели
        const tAnim = document.getElementById("tAnim");
        if (tAnim) tAnim.onchange = applyToggles;
        const tFocus = document.getElementById("tFocus");
        if (tFocus) tFocus.onchange = applyToggles;
        const tSidebar = document.getElementById("tSidebar");
        if (tSidebar) tSidebar.onchange = applyToggles;
        // Плотность
        const densitySlider = document.getElementById("densitySlider");
        if (densitySlider) densitySlider.oninput = applyDensity;

        // scroll-reveal для карточек
        const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) e.target.classList.add("revealed"); }), { threshold: 0.08 });
        document.querySelectorAll(".home-card, .settings-block, .storage-glass").forEach(el => { el.classList.add("reveal"); io.observe(el); });

        // восстановление сохранённого состояния
        const saved = JSON.parse(localStorage.getItem("amt_ui_state") || "{}");
        current.theme = saved.theme || "ocean"; current.font = saved.font || "system"; current.bg = saved.bg || ""; current.lang = saved.lang || "ru";
        applyThemeVars({ ...customThemes, ...themes }[current.theme] || Object.values(themes)[0]);
        applyFont(current.font, current.font === "custom" ? saved.fontFamily : undefined);
        // Restore custom font input value
        const cfRest = document.getElementById("fontCustom");
        if (cfRest && current.font === "custom") { cfRest.value = saved.fontFamily || ""; cfRest.style.display = "block"; }
        applyBg(document.getElementById("bgDim")?.value);
        setLang(current.lang); renderAll(); listConfigs();
        // Восстановить тумблеры и плотность
        if (typeof tAnim !== 'undefined' && tAnim) {
            tAnim.checked = saved.anim !== false;
            tFocus.checked = saved.focus !== false;
            tSidebar.checked = !!saved.sidebar;
        }
        if (densitySlider) {
            densitySlider.value = saved.density != null ? saved.density : 1;
            applyDensity();
        }
        applyToggles();
    }
    function persist() {
        const anim = document.getElementById("tAnim");
        const focus = document.getElementById("tFocus");
        const sb = document.getElementById("tSidebar");
        const den = document.getElementById("densitySlider");
        const cf = document.getElementById("fontCustom");
        localStorage.setItem("amt_ui_state", JSON.stringify({
            theme: current.theme, font: current.font, fontFamily: cf && current.font === "custom" ? cf.value.trim() : undefined,
            bg: current.bg, lang: current.lang,
            anim: anim ? anim.checked : true,
            focus: focus ? focus.checked : true,
            sidebar: sb ? sb.checked : false,
            density: den ? parseInt(den.value, 10) : 1,
        }));
    }

    // Публичное API для main.js (если нужен)
    window.AMTThemes = {
        init,
        setLang,
        applyTheme: (id) => { current.theme = id; const t = ({ ...customThemes, ...themes }[id]); if (t) applyThemeVars(t); renderAll(); persist(); },
        current: () => current,
        // theme-editor.js: перезагрузить в-память customThemes из localStorage
        refreshCustomThemes() {
            try { customThemes = JSON.parse(localStorage.getItem("amt_custom_themes_v2") || "{}"); } catch { customThemes = {}; }
        },
        // theme-editor.js: установить current.theme + перерисовать пикер, БЕЗ повторного применения хранящихся CSS-переменных
        setThemeId(id) {
            current.theme = id;
            renderAll();
        },
    };
    // Для theme-editor.js: публикуем встроенные темы и их id (чтобы редактор знал, что кастомная, что нет)
    Object.defineProperty(window.AMTThemes, "builtinThemes", { get: () => themes, configurable: true });
    Object.defineProperty(window.AMTThemes, "customThemes", { get: () => customThemes, configurable: true });
    Object.defineProperty(window.AMTThemes, "fonts", { get: () => FONTS, configurable: true });
    Object.defineProperty(window, "__AMT_BUILTIN_THEMES__", { get: () => themes, configurable: true });
    Object.defineProperty(window, "__AMT_BUILTIN_IDS__", { get: () => Object.keys(themes), configurable: true });
    Object.defineProperty(window, "__AMT_CUSTOM_IDS__", { get: () => Object.keys(customThemes), configurable: true });
    if (document.readyState !== "loading") init(); else document.addEventListener("DOMContentLoaded", init);
})();
