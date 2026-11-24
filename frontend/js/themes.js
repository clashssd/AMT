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
    function applyThemeVars(t) {
        const r = document.documentElement.style;
        const bg = t.bg || ["#05050a", "#11131a", "#0b0f14"];
        r.setProperty("--bg-grad-1", bg[0]); r.setProperty("--bg-grad-2", bg[1]); r.setProperty("--bg-grad-3", bg[2] || bg[1]);
        r.setProperty("--glass-bg", t.glass || "rgba(255,255,255,0.02)");
        r.setProperty("--glass-bg-2", t.glass2 || "rgba(255,255,255,0.04)");
        r.setProperty("--glass-border", t.border || "rgba(255,255,255,0.06)");
        r.setProperty("--accent", t.accent || "#8b86c9");
        r.setProperty("--accent-2", t.accent2 || "#aba5c9");
        r.setProperty("--text", t.text || "#d0d0d0");
        r.setProperty("--text-dim", t.textDim || "#8a8a9a");
        document.documentElement.setAttribute("data-theme", t.id || "ocean");
    }
    function applyFont(f) {
        const p = FONTS.find(x => x.id === f) || FONTS[0];
        document.documentElement.style.setProperty("--font-family", p.family);
        document.body.style.fontFamily = p.family;
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
        if (fp) { fp.innerHTML = FONTS.map(f => `<option value="${f.id}">${esc(f.label)}</option>`).join(""); fp.value = current.font; }
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
            c.style.background = `linear-gradient(135deg, ${t.bg ? t.bg[0] : "#0a0f1a"} 0%, ${t.bg ? t.bg[1] : "#1a2340"} 50%, ${t.bg ? (t.bg[2] || t.bg[1]) : "#0a1420"} 100%)`;
            c.onclick = () => {
                current.theme = id;
                applyThemeVars(all[id]);
                renderAll();
                persist();
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
        // кастомные темы из localStorage
        try { customThemes = JSON.parse(localStorage.getItem("amt_custom_themes") || "{}"); } catch { customThemes = {}; }

        // события: язык (в настройках → темы и конфиги)
        const lp = document.getElementById("langSelect");
        if (lp) lp.onchange = () => { current.lang = lp.value; setLang(lp.value); persist(); };

        // страница "Темы и конфиги"
        const tp = document.getElementById("themePick");
        if (tp) tp.onchange = () => { current.theme = tp.value; applyThemeVars({ ...customThemes, ...themes }[current.theme]); renderAll(); persist(); };
        const preview = document.getElementById("themePreviewBtn");
        if (preview) preview.onclick = () => { const t = ({ ...customThemes, ...themes })[tp.value]; if (t) applyThemeVars(t); };
        const fp = document.getElementById("fontPick");
        if (fp) fp.onchange = () => { current.font = fp.value; applyFont(current.font); persist(); };
        const ctBtn = document.getElementById("ctCreateBtn");
        if (ctBtn) ctBtn.onclick = () => {
            const name = (document.getElementById("ctName").value.trim() || "custom-" + Date.now().toString(36));
            const id = "custom_" + name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 24);
            customThemes[id] = { id, label: name, bg: [document.getElementById("ctBg1").value, document.getElementById("ctBg2").value, document.getElementById("ctBg3").value],
                accent: document.getElementById("ctAccent").value, accent2: document.getElementById("ctAccent2").value,
                glass: "rgba(0,0,0,0.15)", border: "rgba(255,255,255,0.08)", text: "#e0e0e0", textDim: "#8a8a9a", font: current.font };
            localStorage.setItem("amt_custom_themes", JSON.stringify(customThemes));
            current.theme = id; applyThemeVars(customThemes[id]); renderAll(); persist();
        };
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
        applyFont(current.font); applyBg(document.getElementById("bgDim")?.value);
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
        localStorage.setItem("amt_ui_state", JSON.stringify({
            theme: current.theme, font: current.font, bg: current.bg, lang: current.lang,
            anim: anim ? anim.checked : true,
            focus: focus ? focus.checked : true,
            sidebar: sb ? sb.checked : false,
            density: den ? parseInt(den.value, 10) : 1,
        }));
    }

    // Публичное API для main.js (если нужен)
    window.AMTThemes = { init, setLang, applyTheme: (id) => { current.theme = id; applyThemeVars({ ...customThemes, ...themes }[id]); renderAll(); persist(); }, current: () => current };
    if (document.readyState !== "loading") init(); else document.addEventListener("DOMContentLoaded", init);
})();
